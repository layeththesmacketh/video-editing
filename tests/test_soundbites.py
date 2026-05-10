"""Soundbite splitter tests. Anthropic call is mocked."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lattimore import soundbites
from lattimore.timeline import build_cutdown_timeline, export_timeline


def _transcript():
    return {
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 5.0, "text": "Hello world.",
             "words": [
                 {"word": "Hello", "start": 0.0, "end": 0.5},
                 {"word": "world", "start": 0.5, "end": 5.0},
             ]},
            {"start": 20.0, "end": 50.0, "text": "Another segment goes here.",
             "words": [
                 {"word": "Another", "start": 20.0, "end": 21.0},
                 {"word": "segment", "start": 21.0, "end": 25.0},
                 {"word": "goes", "start": 25.0, "end": 30.0},
                 {"word": "here", "start": 30.0, "end": 50.0},
             ]},
        ],
    }


def test_compact_transcript_keeps_words():
    out = soundbites._compact_transcript(_transcript())
    assert len(out["segments"]) == 2
    assert out["segments"][0]["words"][0] == {"w": "Hello", "s": 0.0, "e": 0.5}


def test_parse_response_strict():
    text = json.dumps([{"in": 0.0, "out": 20.0, "speaker": "Andrei", "headline": "X", "why": "Y"}])
    out = soundbites._parse_response(text)
    assert out == [{"in": 0.0, "out": 20.0, "speaker": "andrei", "headline": "X", "why": "Y"}]


def test_parse_response_with_fence():
    raw = "```json\n" + json.dumps([{"in": 0.0, "out": 20.0}]) + "\n```"
    out = soundbites._parse_response(raw)
    assert out[0]["in"] == 0.0


def test_parse_response_rejects_non_list():
    with pytest.raises(ValueError):
        soundbites._parse_response('{"foo": 1}')


def test_find_soundbites_calls_anthropic():
    fake_text = json.dumps([
        {"in": 0.0, "out": 20.0, "speaker": "andrei", "headline": "h", "why": "w"},
    ])
    fake_block = MagicMock(type="text", text=fake_text)
    fake_msg = MagicMock(content=[fake_block])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    result = soundbites.find_soundbites(
        _transcript(),
        speakers=["andrei", "tawny"],
        client=fake_client,
        model="m",
    )
    assert result == [{"in": 0.0, "out": 20.0, "speaker": "andrei", "headline": "h", "why": "w"}]
    call = fake_client.messages.create.call_args.kwargs
    assert call["model"] == "m"
    # System prompt carries the rules; user message carries transcript + speakers.
    assert "soundbites" in call["system"].lower()


def test_validate_soundbites_word_boundary_required():
    sbs = [{"in": 0.0, "out": 19.99}]  # 19.99 is not a word edge
    res = soundbites.validate_soundbites(sbs, _transcript())
    assert not res["ok"]
    assert any("word boundary" in e for e in res["errors"])


def test_validate_soundbites_min_duration():
    sbs = [{"in": 0.0, "out": 5.0}]  # 5s < 15s min
    res = soundbites.validate_soundbites(sbs, _transcript())
    assert not res["ok"]
    assert any("< min" in e for e in res["errors"])


def test_validate_soundbites_overlap():
    sbs = [
        {"in": 0.0, "out": 50.0},     # 50s, valid
        {"in": 25.0, "out": 50.0},    # overlaps
    ]
    res = soundbites.validate_soundbites(sbs, _transcript())
    assert not res["ok"]
    assert any("overlap" in e for e in res["errors"])


def test_validate_soundbites_passes_clean():
    sbs = [{"in": 0.0, "out": 20.0}]  # 20s, both edges are word boundaries
    res = soundbites.validate_soundbites(sbs, _transcript())
    assert res["ok"], res["errors"]
    assert res["count"] == 1


def test_build_cutdown_timeline_track_layout():
    sbs = [
        {"in": 5.0, "out": 25.0, "speaker": "andrei", "headline": "first sb", "why": ""},
        {"in": 40.0, "out": 80.0, "speaker": "andrei", "headline": "second", "why": ""},
    ]
    tl = build_cutdown_timeline("/x/INT.mov", duration=120.0, soundbites=sbs)
    names = [t.name for t in tl.tracks]
    assert names == ["V1_MASTER", "V2_SOUNDBITES", "A1_MASTER", "A2_SOUNDBITES"]
    # V1 holds exactly one clip (the full master).
    v1_children = list(tl.tracks[0])
    assert len(v1_children) == 1
    # V2 holds gap, clip, gap, clip.
    v2_children = list(tl.tracks[1])
    assert len(v2_children) == 4
    # Soundbite names propagate.
    sb_clips = [c for c in v2_children if not isinstance(c, type(v2_children[0])) or hasattr(c, "media_reference")]
    assert any(getattr(c, "name", "") == "first sb" for c in v2_children)


def test_build_cutdown_timeline_rejects_overlap():
    sbs = [
        {"in": 0.0, "out": 30.0},
        {"in": 25.0, "out": 60.0},
    ]
    with pytest.raises(ValueError, match="overlap"):
        build_cutdown_timeline("/x/INT.mov", duration=120.0, soundbites=sbs)


def test_build_cutdown_timeline_round_trips_to_fcpxml(tmp_path: Path):
    sbs = [{"in": 0.0, "out": 20.0, "speaker": "a", "headline": "x", "why": ""}]
    tl = build_cutdown_timeline("/x/INT.mov", duration=60.0, soundbites=sbs)
    out = export_timeline(tl, tmp_path / "cd.fcpxml")
    text = out.read_text()
    assert text.startswith("<?xml")
    assert "<fcpxml" in text
    assert "INT" in text  # clip name appears
