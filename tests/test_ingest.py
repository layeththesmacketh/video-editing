"""Ingest tests. We mock whisperx + the Anthropic vision call so the suite
runs offline with no models or API keys."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lattimore import ingest


def test_index_key_format():
    key = ingest._index_key(
        Path("/x/runway_walk.mov"),
        {"description": "Backstage hands holding a clutch", "keywords": ["hands", "clutch"]},
    )
    assert "runway_walk.mov" in key
    assert "Backstage hands" in key
    assert "hands" in key and "clutch" in key


def test_parse_vision_json_strict():
    out = ingest._parse_vision_json('{"description": "x", "keywords": ["a","B"]}')
    assert out == {"description": "x", "keywords": ["a", "b"]}


def test_parse_vision_json_with_fence():
    out = ingest._parse_vision_json('```json\n{"description":"x","keywords":[]}\n```')
    assert out["description"] == "x"


def test_parse_vision_json_rejects_non_json():
    with pytest.raises(json.JSONDecodeError):
        ingest._parse_vision_json("not json")


def test_describe_clip_uses_client(tmp_path: Path):
    # Two fake frames on disk.
    f1 = tmp_path / "f1.jpg"; f1.write_bytes(b"\xff\xd8\xff\xd9")
    f2 = tmp_path / "f2.jpg"; f2.write_bytes(b"\xff\xd8\xff\xd9")

    fake_block = MagicMock(type="text", text='{"description":"hands on lapel","keywords":["hands","lapel"]}')
    fake_msg = MagicMock(content=[fake_block])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_msg

    out = ingest.describe_clip([f1, f2], client=fake_client, model="m")
    assert out == {"description": "hands on lapel", "keywords": ["hands", "lapel"]}

    # Verify the vision call shape.
    call = fake_client.messages.create.call_args.kwargs
    assert call["model"] == "m"
    msgs = call["messages"]
    assert msgs[0]["role"] == "user"
    types = [c["type"] for c in msgs[0]["content"]]
    assert types.count("image") == 2
    assert types[-1] == "text"


def test_build_footage_map_iterates_videos(tmp_path: Path):
    # Make a fake B-roll dir with two videos and one non-video.
    (tmp_path / "BR_walk.mov").write_bytes(b"")
    (tmp_path / "BR_hands.mp4").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("ignore me")

    fake_client = MagicMock()
    # Iteration is sorted: BR_hands.mp4 first, then BR_walk.mov.
    seq = iter([
        {"description": "hands on a clutch", "keywords": ["hands", "clutch"]},
        {"description": "model walking out", "keywords": ["walk", "runway"]},
    ])
    with patch.object(ingest, "extract_frames", return_value=[]) as ef, \
         patch.object(ingest, "describe_clip", side_effect=lambda *_a, **_k: next(seq)) as dc:
        index, raw = ingest.build_footage_map(tmp_path, client=fake_client)

    assert ef.call_count == 2
    assert dc.call_count == 2
    assert len(index) == 2
    # Index keys carry filename + description + keywords for substring lookup.
    assert any("walk" in k.lower() and "BR_walk.mov" in k for k in index)
    assert any("clutch" in k.lower() and "BR_hands.mp4" in k for k in index)
    # Raw annotations indexed by absolute path.
    assert all(Path(p).is_absolute() for p in raw)


def test_build_footage_map_records_errors(tmp_path: Path):
    (tmp_path / "BR_one.mov").write_bytes(b"")
    with patch.object(ingest, "extract_frames", side_effect=RuntimeError("ffmpeg missing")):
        index, raw = ingest.build_footage_map(tmp_path, client=MagicMock())
    [(_, path)] = index.items()
    ann = raw[path]
    assert ann["error"] == "ffmpeg missing"
    assert ann["description"] == ""


def test_ingest_library_writes_artifacts(tmp_path: Path):
    interview = tmp_path / "INT.mov"
    interview.write_bytes(b"")
    broll = tmp_path / "broll"
    broll.mkdir()
    (broll / "BR_walk.mov").write_bytes(b"")
    out = tmp_path / "work"

    fake_transcript = {
        "clip": str(interview),
        "language": "en",
        "segments": [{"start": 0.0, "end": 1.0, "text": "hi", "words": []}],
    }
    with patch.object(ingest, "transcribe_interview", return_value=fake_transcript), \
         patch.object(ingest, "extract_frames", return_value=[]), \
         patch.object(ingest, "describe_clip", return_value={"description": "x", "keywords": ["y"]}):
        res = ingest.ingest_library(interview, broll, out)

    assert res["ok"] is True
    assert res["clip_count"] == 1
    transcripts = json.loads(Path(res["transcripts"]).read_text())
    assert str(interview) in transcripts
    fmap = json.loads(Path(res["footage_map"]).read_text())
    assert len(fmap) == 1
    [(key, path)] = fmap.items()
    assert "BR_walk.mov" in key
    assert path.endswith("BR_walk.mov")


def test_video_exts_set():
    assert ".mov" in ingest.VIDEO_EXTS
    assert ".txt" not in ingest.VIDEO_EXTS
