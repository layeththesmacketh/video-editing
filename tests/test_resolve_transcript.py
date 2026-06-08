"""Tests for the Resolve transcription .txt parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from lattimore.resolve_transcript import parse_resolve_transcript


def write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "transcript.txt"
    p.write_text(body)
    return p


def test_basic_two_speakers(tmp_path: Path):
    src = write(tmp_path, """[00:00:00:00 - 00:00:04:00]
Speaker 1
 Hello world.

[00:00:05:00 - 00:00:08:00]
Speaker 2
 Reply text.
""")
    d = parse_resolve_transcript(src, rate=24.0)
    assert d["duration"] == 8.0
    assert d["speakers"] == ["Speaker 1", "Speaker 2"]
    assert len(d["diarization"]) == 2
    assert d["diarization"][0] == {"start": 0.0, "end": 4.0, "speaker": "Speaker 1"}
    assert d["diarization"][1] == {"start": 5.0, "end": 8.0, "speaker": "Speaker 2"}


def test_non_speech_blocks_skipped_for_diarization(tmp_path: Path):
    """Bracketed events like (Claps), (Laughing) have no Speaker line — they
    contribute to duration but not to the speaker diarization."""
    src = write(tmp_path, """[00:00:00:00 - 00:00:02:00]
Speaker 1
 Talking.

[00:00:02:00 - 00:00:03:00]
 (Claps)

[00:00:03:00 - 00:00:05:00]
Speaker 1
 More talking.
""")
    d = parse_resolve_transcript(src, rate=24.0)
    assert len(d["diarization"]) == 2
    assert d["diarization"][0]["speaker"] == "Speaker 1"
    assert d["diarization"][1]["start"] == 3.0
    assert len(d["segments"]) == 3
    assert d["segments"][1]["speaker"] is None
    assert "(Claps)" in d["segments"][1]["text"]


def test_frame_timecode_at_24fps(tmp_path: Path):
    src = write(tmp_path, """[00:00:00:12 - 00:00:01:12]
Speaker 1
 Half-frame test.
""")
    d = parse_resolve_transcript(src, rate=24.0)
    # 00:00:00:12 at 24fps = 0.5s; 00:00:01:12 = 1.5s
    assert d["diarization"][0]["start"] == pytest.approx(0.5)
    assert d["diarization"][0]["end"] == pytest.approx(1.5)


def test_multi_line_speaker_text_is_joined(tmp_path: Path):
    src = write(tmp_path, """[00:00:00:00 - 00:00:05:00]
Speaker 1
 First line
 second line
 third line.
""")
    d = parse_resolve_transcript(src, rate=24.0)
    assert d["segments"][0]["text"] == "First line second line third line."


def test_segment_speaker_label_carries_through(tmp_path: Path):
    """speaker_breakdown() looks at segment['speaker']; verify we set it."""
    src = write(tmp_path, """[00:00:00:00 - 00:00:01:00]
Speaker 2
 Hi.
""")
    d = parse_resolve_transcript(src, rate=24.0)
    assert d["segments"][0]["speaker"] == "Speaker 2"


def test_speakers_listed_sorted(tmp_path: Path):
    src = write(tmp_path, """[00:00:00:00 - 00:00:01:00]
Speaker 3
 third.

[00:00:01:00 - 00:00:02:00]
Speaker 1
 first.

[00:00:02:00 - 00:00:03:00]
Speaker 2
 second.
""")
    d = parse_resolve_transcript(src, rate=24.0)
    assert d["speakers"] == ["Speaker 1", "Speaker 2", "Speaker 3"]


def test_malformed_block_skipped(tmp_path: Path):
    """A block missing the [start - end] header is ignored, not crashed on."""
    src = write(tmp_path, """garbage line

[00:00:00:00 - 00:00:01:00]
Speaker 1
 Real content.

more garbage
""")
    d = parse_resolve_transcript(src, rate=24.0)
    assert len(d["diarization"]) == 1
    assert d["diarization"][0]["speaker"] == "Speaker 1"
