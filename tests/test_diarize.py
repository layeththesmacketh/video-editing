"""Tests for diarize.py — focused on the pure cut-planning logic. WhisperX
itself is not exercised here; it's behind an import inside
`diarize_interview()` and gated on HF_TOKEN."""

from __future__ import annotations

import pytest

from lattimore.diarize import (
    plan_speaker_cuts,
    speaker_breakdown,
    _merge_overlapping,
    _subtract,
)


def diarized(ranges: list[tuple[float, float, str]], duration: float = 60.0) -> dict:
    return {
        "duration": duration,
        "diarization": [
            {"start": s, "end": e, "speaker": sp} for s, e, sp in ranges
        ],
        "segments": [],
    }


# --- _merge_overlapping ----------------------------------------------------

def test_merge_overlapping_combines_touching_spans():
    assert _merge_overlapping([(0, 1), (1, 2), (3, 4)]) == [(0, 2), (3, 4)]


def test_merge_overlapping_combines_overlapping_spans():
    assert _merge_overlapping([(0, 5), (3, 8), (10, 12)]) == [(0, 8), (10, 12)]


def test_merge_overlapping_handles_empty():
    assert _merge_overlapping([]) == []


# --- _subtract -------------------------------------------------------------

def test_subtract_no_hole():
    assert _subtract(0, 10, []) == [(0, 10)]


def test_subtract_hole_in_middle():
    assert _subtract(0, 10, [(3, 5)]) == [(0, 3), (5, 10)]


def test_subtract_hole_covers_all():
    assert _subtract(0, 10, [(0, 10)]) == []


def test_subtract_multiple_holes():
    assert _subtract(0, 20, [(2, 4), (8, 12), (15, 18)]) == [
        (0, 2), (4, 8), (12, 15), (18, 20),
    ]


# --- plan_speaker_cuts -----------------------------------------------------

def test_keeps_only_main_speaker():
    """Two speakers, interviewer talks at [10,15] and [40,45]. Keep SPEAKER_00.
    Both interviewer ranges should be cut."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 15, "SPEAKER_01"),
        (15, 40, "SPEAKER_00"),
        (40, 45, "SPEAKER_01"),
        (45, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"])
    assert plan["summary"]["cut_count"] == 2
    assert plan["cuts"][0]["start"] == 10
    assert plan["cuts"][0]["end"] == 15
    assert plan["cuts"][0]["speakers"] == ["SPEAKER_01"]
    assert plan["cuts"][1]["start"] == 40
    assert plan["cuts"][1]["end"] == 45


def test_preserves_silences():
    """Silence at [20,30] must NOT be cut. Only the interviewer range gets cut."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 15, "SPEAKER_01"),
        # silence [15, 30]
        (30, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"])
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 10
    assert plan["cuts"][0]["end"] == 15


def test_overlapping_kept_and_other_keeps_overlap_section():
    """If kept speaker talks over the interviewer, that section is NOT cut —
    we keep any region where ANY kept speaker is active."""
    d = diarized([
        (0, 20, "SPEAKER_01"),    # interviewer
        (10, 30, "SPEAKER_00"),   # interviewee overlaps from 10-20
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"])
    # Only [0, 10] is purely interviewer; [10, 20] is overlap (kept).
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 0
    assert plan["cuts"][0]["end"] == 10


def test_merge_gap_combines_close_cuts():
    """Two interviewer ranges separated by 0.2s should merge into one cut."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 15, "SPEAKER_01"),
        (15.2, 20, "SPEAKER_01"),
        (20, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], merge_gap=0.3)
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 10
    assert plan["cuts"][0]["end"] == 20


def test_merge_gap_off_keeps_cuts_separate():
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 15, "SPEAKER_01"),
        (15.2, 20, "SPEAKER_01"),
        (20, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], merge_gap=0.0)
    assert plan["summary"]["cut_count"] == 2


def test_multi_keep_speakers():
    """Two interviewees in conversation, one interviewer. Keep both interviewees."""
    d = diarized([
        (0, 10, "SPEAKER_00"),    # interviewee A
        (10, 12, "SPEAKER_01"),   # interviewer question
        (12, 25, "SPEAKER_02"),   # interviewee B
        (25, 27, "SPEAKER_01"),   # interviewer
        (27, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00", "SPEAKER_02"])
    assert plan["summary"]["cut_count"] == 2
    assert {(c["start"], c["end"]) for c in plan["cuts"]} == {(10.0, 12.0), (25.0, 27.0)}


def test_min_cut_duration_drops_tiny_cuts():
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 10.05, "SPEAKER_01"),   # 0.05s interviewer blip
        (10.05, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], min_cut_duration=0.1)
    assert plan["summary"]["cut_count"] == 0


def test_padding_trims_inward():
    """pad_start=0.1, pad_end=0.1 should shrink a [10,15] cut to [10.1, 14.9]."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 15, "SPEAKER_01"),
        (15, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], pad_start=0.1, pad_end=0.1)
    assert plan["summary"]["cut_count"] == 1
    c = plan["cuts"][0]
    assert c["start"] == pytest.approx(10.1)
    assert c["end"] == pytest.approx(14.9)


def test_summary_durations_balance():
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10, 20, "SPEAKER_01"),
        (20, 60, "SPEAKER_00"),
    ], duration=60)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"])
    summary = plan["summary"]
    assert summary["original_duration"] == 60
    assert summary["cut_duration"] == 10
    assert summary["kept_duration"] == 50


def test_no_kept_speakers_cuts_everything_that_speaks():
    d = diarized([(0, 10, "SPEAKER_01"), (20, 30, "SPEAKER_02")], duration=60)
    plan = plan_speaker_cuts(d, [])
    assert plan["summary"]["cut_count"] == 2


# --- speaker_breakdown -----------------------------------------------------

def test_preserve_interjections_short_yep_between_kept_is_kept():
    """A short 'Yep' from a non-kept speaker landing between two Deja ranges
    should NOT be cut by default."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10.3, 10.8, "SPEAKER_01"),     # short interjection
        (11.0, 20, "SPEAKER_00"),
    ], duration=20)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"])
    assert plan["summary"]["cut_count"] == 0
    assert plan["summary"]["preserved_interjection_count"] == 1


def test_preserve_interjections_off_cuts_the_yep():
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10.3, 10.8, "SPEAKER_01"),
        (11.0, 20, "SPEAKER_00"),
    ], duration=20)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], preserve_interjections=False)
    assert plan["summary"]["cut_count"] == 1


def test_preserve_interjections_long_interruption_still_cut():
    """A 3-second non-kept range between Deja ranges is NOT an interjection;
    it still gets cut."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10.5, 13.5, "SPEAKER_01"),    # 3s — too long
        (14, 20, "SPEAKER_00"),
    ], duration=20)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], max_interjection_duration=1.0)
    assert plan["summary"]["cut_count"] == 1


def test_preserve_interjections_not_sandwiched_still_cut():
    """A short non-kept range NOT sandwiched between kept ranges is cut."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        (10.1, 10.6, "SPEAKER_01"),    # short
        # no SPEAKER_00 after — this is not an interjection
        (11, 20, "SPEAKER_01"),        # long SPEAKER_01 follows
    ], duration=20)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"])
    # The 0.5s "Mhm" is not sandwiched; it should be cut as part of the
    # surrounding SPEAKER_01 block.
    assert plan["summary"]["cut_count"] >= 1


def test_preserve_interjections_window_too_far_still_cut():
    """If the gap before/after exceeds the window, the short range is not
    treated as an interjection."""
    d = diarized([
        (0, 10, "SPEAKER_00"),
        # 5s gap of silence here
        (15, 15.5, "SPEAKER_01"),
        # 5s gap of silence here
        (20.5, 30, "SPEAKER_00"),
    ], duration=30)
    plan = plan_speaker_cuts(d, ["SPEAKER_00"], interjection_window=2.0)
    assert plan["summary"]["cut_count"] == 1


def test_speaker_breakdown_ranks_by_talk_time():
    d = {
        "duration": 100.0,
        "diarization": [
            {"start": 0, "end": 60, "speaker": "SPEAKER_00"},
            {"start": 60, "end": 80, "speaker": "SPEAKER_01"},
        ],
        "segments": [
            {"start": 0, "end": 60, "text": "Long thoughtful answer.", "speaker": "SPEAKER_00", "words": []},
            {"start": 60, "end": 80, "text": "Quick question?", "speaker": "SPEAKER_01", "words": []},
        ],
    }
    report = speaker_breakdown(d)
    assert report["speakers"][0]["label"] == "SPEAKER_00"
    assert report["speakers"][0]["total_seconds"] == 60.0
    assert report["speakers"][0]["share_of_speech"] == pytest.approx(60 / 80, abs=0.001)
    assert report["speakers"][1]["label"] == "SPEAKER_01"
    assert report["silence_duration"] == 20.0


def test_speaker_breakdown_samples_quotes():
    d = {
        "duration": 100.0,
        "diarization": [{"start": 0, "end": 100, "speaker": "SPEAKER_00"}],
        "segments": [
            {"start": 0, "end": 5, "text": "First", "speaker": "SPEAKER_00", "words": []},
            {"start": 5, "end": 10, "text": "Second", "speaker": "SPEAKER_00", "words": []},
            {"start": 10, "end": 15, "text": "Third", "speaker": "SPEAKER_00", "words": []},
            {"start": 15, "end": 20, "text": "Fourth", "speaker": "SPEAKER_00", "words": []},
        ],
    }
    report = speaker_breakdown(d, samples_per_speaker=3)
    quotes = report["speakers"][0]["sample_quotes"]
    assert len(quotes) == 3
    assert [q["text"] for q in quotes] == ["First", "Second", "Third"]
