"""Timeline tests: timecode parsing, track structure, OTIO round-trip, EDL header."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lattimore.timeline import (
    DEFAULT_RATE,
    build_timeline,
    export_timeline,
    parse_timecode,
    timecode,
)


def test_timecode_round_trip():
    s = 12.5
    tc = timecode(s, rate=24.0)
    assert tc == "00:00:12:12"
    back = parse_timecode(tc, rate=24.0)
    assert back == pytest.approx(s, abs=1 / 24.0)


def test_parse_timecode_decimal_seconds():
    assert parse_timecode("00:00:12.500") == pytest.approx(12.5)


def test_parse_timecode_invalid():
    with pytest.raises(ValueError):
        parse_timecode("12s")


def _fake_schema():
    return {
        "aroll": [
            {"clip": "/tmp/INT_001.mov", "in": 10.0, "out": 14.0},
            {"clip": "/tmp/INT_001.mov", "in": 20.0, "out": 22.0},
        ],
        "broll": [
            {"clip": "/tmp/BR_walk.mov", "in": 0.0, "out": 1.5,
             "over_aroll_at": 5.0, "audio": False},
        ],
        "music": [
            {"clip": "/tmp/MUS.wav", "in": 0.0, "duration": 6.0},
        ],
    }


def test_build_timeline_track_structure():
    tl = build_timeline(_fake_schema())
    names = [t.name for t in tl.tracks]
    assert names == ["V1_AROLL", "V2_BROLL", "A1_DIALOG", "A2_MUSIC"]
    kinds = [t.kind for t in tl.tracks]
    # Two video, two audio
    assert kinds.count("Video") == 2
    assert kinds.count("Audio") == 2
    assert tl.metadata["lattimore"]["total_runtime"] == pytest.approx(6.0)


def test_otio_round_trip(tmp_path: Path):
    tl = build_timeline(_fake_schema())
    out = export_timeline(tl, tmp_path / "rc.otio")
    assert out.exists()
    data = json.loads(out.read_text())
    # OTIO json carries tracks; cheap structural sanity check.
    assert "OTIO_SCHEMA" in data
    assert data.get("name") == "lattimore_roughcut"


def test_edl_export_has_header(tmp_path: Path):
    tl = build_timeline({
        "aroll": [{"clip": "/tmp/INT_001.mov", "in": 0.0, "out": 4.0}],
        "broll": [],
        "music": [],
    })
    out = export_timeline(tl, tmp_path / "rc.edl")
    text = out.read_text()
    # CMX 3600 EDLs begin with TITLE and FCM lines.
    assert text.startswith("TITLE:")
    assert "FCM:" in text


def test_build_timeline_rejects_overlap_v2():
    schema = {
        "aroll": [{"clip": "/tmp/A.mov", "in": 0.0, "out": 10.0}],
        "broll": [
            {"clip": "/tmp/B1.mov", "in": 0.0, "out": 2.0, "over_aroll_at": 1.0, "audio": False},
            {"clip": "/tmp/B2.mov", "in": 0.0, "out": 2.0, "over_aroll_at": 2.5, "audio": False},
        ],
        "music": [],
    }
    with pytest.raises(ValueError, match="overlap"):
        build_timeline(schema)


def test_default_rate_is_24():
    assert DEFAULT_RATE == 24.0
