"""Paper-edit and B-roll matcher tests."""

from __future__ import annotations

import pytest

from lattimore.paper_edit import filter_candidates, validate_paper_edit
from lattimore.broll_matcher import find_footage_url, validate_broll


# ---------------------------------------------------------------------------
# filter_candidates
# ---------------------------------------------------------------------------

def _transcript():
    return {
        "clip": "INT_001.mov",
        "segments": [
            {
                "start": 0.10, "end": 0.40, "text": "um",
                "words": [{"word": "um", "start": 0.10, "end": 0.40}],
            },
            {
                "start": 1.00, "end": 5.00, "text": "The thing nobody tells you is —",
                "words": [
                    {"word": "The", "start": 1.00, "end": 1.20},
                    {"word": "thing", "start": 1.20, "end": 1.55},
                    {"word": "nobody", "start": 1.55, "end": 2.00},
                    {"word": "tells", "start": 2.00, "end": 2.40},
                    {"word": "you", "start": 2.40, "end": 2.65},
                    {"word": "is", "start": 2.65, "end": 5.00},
                ],
            },
            {
                "start": 6.00, "end": 6.30, "text": "uh",
                "words": [{"word": "uh", "start": 6.00, "end": 6.30}],
            },
        ],
    }


def test_filter_drops_fillers_and_short():
    cands = filter_candidates(_transcript())
    assert len(cands) == 1
    assert cands[0]["text"].startswith("The thing")
    assert cands[0]["clip"] == "INT_001.mov"


def test_filter_keeps_fillers_when_disabled():
    cands = filter_candidates(_transcript(), drop_fillers=False, min_duration=0.1)
    assert len(cands) == 3


# ---------------------------------------------------------------------------
# validate_paper_edit
# ---------------------------------------------------------------------------

def _good_select(role, in_, out_, words=None):
    return {"clip": "X.mov", "in": in_, "out": out_, "role": role, "words": words or []}


def test_validate_runtime_within_tolerance():
    selects = [
        _good_select("hook", 0.0, 4.0),
        _good_select("premise", 0.0, 6.0),
        _good_select("resolve", 0.0, 5.0),
    ]
    res = validate_paper_edit(selects, target_runtime=15.0)
    assert res["ok"], res["errors"]


def test_validate_runtime_outside_tolerance():
    res = validate_paper_edit(
        [_good_select("hook", 0.0, 5.0)], target_runtime=15.0
    )
    assert not res["ok"]
    assert any("off target" in e for e in res["errors"])


def test_validate_role_must_be_known():
    res = validate_paper_edit(
        [_good_select("xxx", 0.0, 5.0)], target_runtime=5.0
    )
    assert not res["ok"]
    assert any("role" in e for e in res["errors"])


def test_validate_mid_word_cut_detected():
    words = [
        {"word": "hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.5, "end": 1.0},
    ]
    s = _good_select("hook", 0.25, 1.0, words=words)
    res = validate_paper_edit([s], target_runtime=0.75)
    assert not res["ok"]
    assert any("mid-word" in e for e in res["errors"])


def test_validate_word_boundary_passes():
    words = [
        {"word": "hello", "start": 0.0, "end": 0.5},
        {"word": "world", "start": 0.5, "end": 1.0},
    ]
    s = _good_select("hook", 0.0, 1.0, words=words)
    res = validate_paper_edit([s], target_runtime=1.0)
    assert res["ok"], res["errors"]


# ---------------------------------------------------------------------------
# find_footage_url (case-insensitive partial match)
# ---------------------------------------------------------------------------

FOOTAGE = {
    "Vera Wang Runway 2024.mov": "/library/vw_runway_2024.mov",
    "Backstage Hands Closeup.mov": "/library/hands.mov",
    "Reebok_Court_Wide.mov": "/library/court.mov",
}


def test_footage_match_case_insensitive():
    assert find_footage_url("vera wang", FOOTAGE) == "/library/vw_runway_2024.mov"
    assert find_footage_url("VERA WANG", FOOTAGE) == "/library/vw_runway_2024.mov"


def test_footage_match_partial():
    assert find_footage_url("hands", FOOTAGE) == "/library/hands.mov"


def test_footage_no_match_returns_none():
    assert find_footage_url("zebra", FOOTAGE) is None


def test_footage_empty_keyword():
    assert find_footage_url("", FOOTAGE) is None


# ---------------------------------------------------------------------------
# validate_broll: skips hook lines, gap rule, coverage rule
# ---------------------------------------------------------------------------

def _aroll():
    return [
        {"clip": "A.mov", "in": 0.0, "out": 5.0, "role": "hook"},      # 0–5
        {"clip": "A.mov", "in": 0.0, "out": 10.0, "role": "premise"},  # 5–15
        {"clip": "A.mov", "in": 0.0, "out": 10.0, "role": "texture"},  # 15–25
        {"clip": "A.mov", "in": 0.0, "out": 5.0, "role": "resolve"},   # 25–30
    ]


def test_broll_cannot_overlap_hook():
    broll = [
        {"clip": "B.mov", "in": 0.0, "out": 2.0, "over_aroll_at": 2.0, "audio": False},
    ]
    res = validate_broll(broll, _aroll())
    assert not res["ok"]
    assert any("hook" in e for e in res["errors"])


def test_broll_cannot_overlap_reaction():
    aroll = [
        {"clip": "A.mov", "in": 0.0, "out": 5.0, "role": "hook"},
        {"clip": "A.mov", "in": 0.0, "out": 5.0, "role": "texture", "reaction": True},
    ]
    broll = [
        {"clip": "B.mov", "in": 0.0, "out": 2.0, "over_aroll_at": 6.0, "audio": False},
    ]
    res = validate_broll(broll, aroll)
    assert not res["ok"]
    assert any("reaction" in e for e in res["errors"])


def test_broll_min_gap_enforced():
    broll = [
        {"clip": "B.mov", "in": 0.0, "out": 1.0, "over_aroll_at": 6.0, "audio": False},
        {"clip": "B.mov", "in": 0.0, "out": 1.0, "over_aroll_at": 7.2, "audio": False},  # gap 0.2
    ]
    res = validate_broll(broll, _aroll())
    assert not res["ok"]
    assert any("0.5" in e or "gap" in e.lower() or "after prior" in e for e in res["errors"])


def test_broll_coverage_cap():
    # 30s timeline, place ~20s of B-roll outside the hook (5–25) → 66%, fails the 60% cap.
    broll = [
        {"clip": "B.mov", "in": 0.0, "out": 10.0, "over_aroll_at": 5.0, "audio": False},
        {"clip": "B.mov", "in": 0.0, "out": 10.0, "over_aroll_at": 15.5, "audio": False},
    ]
    res = validate_broll(broll, _aroll())
    assert not res["ok"]
    assert any("coverage" in e.lower() for e in res["errors"])


def test_broll_layover_must_not_exceed_underlying():
    # Place a 12s lay-over starting at t=6.0 — host A-roll spans 5–15, so 6+12=18 > 15.
    broll = [
        {"clip": "B.mov", "in": 0.0, "out": 12.0, "over_aroll_at": 6.0, "audio": False},
    ]
    res = validate_broll(broll, _aroll())
    assert not res["ok"]
    assert any("exceeds underlying" in e for e in res["errors"])


def test_broll_valid_passes():
    broll = [
        {"clip": "B.mov", "in": 0.0, "out": 2.0, "over_aroll_at": 7.0, "audio": False},
        {"clip": "B.mov", "in": 0.0, "out": 2.0, "over_aroll_at": 17.0, "audio": False},
    ]
    res = validate_broll(broll, _aroll())
    assert res["ok"], res["errors"]
    assert res["coverage"] < 0.60
