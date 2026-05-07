"""Local ingest: transcribe interview audio + analyze B-roll into a footage map.

Independent of ButterCut — uses `whisperx` for transcription and the Anthropic
SDK for per-clip vision analysis. Both are optional deps (`pip install -e '.[ingest]'`).

Outputs two JSON files into the work dir:

    transcripts.json
        {"<clip-path>": {"clip": "...", "segments": [{"start","end","text","words":[...]}, ...]}, ...}

    footage_map.json
        {"<key>": "<absolute-clip-path>", ...}
        where each key is "<filename> :: <description> :: <kw1>, <kw2>, ..." so the
        existing case-insensitive substring matcher (`find_footage_url`) gets a
        rich surface to match against.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable

VIDEO_EXTS = {".mov", ".mp4", ".mxf", ".m4v", ".avi", ".mkv"}
DEFAULT_VISION_MODEL = "claude-haiku-4-5-20251001"  # cheap + fast for shot description


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe_interview(
    video_path: str | Path,
    *,
    model: str = "small.en",
    device: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Transcribe a video with whisperx; return the WhisperX-shaped dict.

    Requires the `[ingest]` extra. Word-level timestamps are produced via
    whisperx's forced alignment pass, which is what `interview-paper-edit`
    needs to enforce the no-mid-word-cut rule.
    """
    try:
        import whisperx  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "whisperx not installed. Install ingest extras: "
            "pip install -e '.[ingest]'"
        ) from e

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    device = device or ("cuda" if _cuda_available() else "cpu")
    compute_type = "float16" if device == "cuda" else "int8"

    asr = whisperx.load_model(model, device, compute_type=compute_type, language=language)
    audio = whisperx.load_audio(str(video_path))
    result = asr.transcribe(audio, batch_size=8 if device == "cuda" else 4)

    # Forced alignment for word-level timestamps.
    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    aligned = whisperx.align(
        result["segments"], align_model, metadata, audio, device,
        return_char_alignments=False,
    )

    return {
        "clip": str(video_path),
        "language": language,
        "segments": aligned["segments"],
    }


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# B-roll vision analysis
# ---------------------------------------------------------------------------

def extract_frames(video_path: str | Path, n: int = 3) -> list[Path]:
    """Extract `n` evenly-spaced frames via ffmpeg into a temp dir.

    Returns a list of paths the caller is responsible for cleaning up
    (or just letting tempdir cleanup handle).
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not on PATH — install ffmpeg to use vision analysis")

    video_path = Path(video_path)
    duration = _probe_duration(video_path)
    if duration <= 0:
        raise RuntimeError(f"could not probe duration of {video_path}")

    out_dir = Path(tempfile.mkdtemp(prefix="lattimore_frames_"))
    paths: list[Path] = []
    # Sample at 10%, 50%, 90% (or evenly for n != 3).
    if n == 1:
        offsets = [duration / 2]
    else:
        offsets = [duration * (i + 1) / (n + 1) for i in range(n)]
    for i, t in enumerate(offsets):
        out = out_dir / f"frame_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", str(out)],
            check=True, capture_output=True,
        )
        paths.append(out)
    return paths


def _probe_duration(video_path: Path) -> float:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not on PATH")
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    return float(res.stdout.strip())


def describe_clip(
    frames: Iterable[Path],
    *,
    client: Any = None,
    model: str = DEFAULT_VISION_MODEL,
) -> dict[str, Any]:
    """Call Claude vision on the sampled frames; return {description, keywords}."""
    if client is None:
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "anthropic SDK not installed. Install ingest extras: "
                "pip install -e '.[ingest]'"
            ) from e
        client = Anthropic()

    content: list[dict[str, Any]] = []
    for fp in frames:
        b64 = base64.standard_b64encode(Path(fp).read_bytes()).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    content.append({
        "type": "text",
        "text": (
            "These frames are sampled from a single B-roll clip for an interview-led edit. "
            "Return strict JSON: {\"description\": \"<one sentence, max 20 words, concrete and visual>\", "
            "\"keywords\": [\"<3-8 lowercase keywords useful for substring matching: subjects, actions, "
            "settings, emotional register>\"]}. No prose outside the JSON."
        ),
    })

    msg = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    return _parse_vision_json(text)


def _parse_vision_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Tolerate ```json fences.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    desc = str(data.get("description", "")).strip()
    kws = [str(k).strip().lower() for k in (data.get("keywords") or []) if k]
    return {"description": desc, "keywords": kws}


def build_footage_map(
    broll_dir: str | Path,
    *,
    client: Any = None,
    model: str = DEFAULT_VISION_MODEL,
    progress: Callable[[str], None] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Walk `broll_dir`, analyze each clip, return (search_index, raw_annotations).

    `search_index` is the flat `{key -> path}` dict the runtime matcher uses;
    each key is "<filename> :: <description> :: <kw1, kw2, ...>" so substring
    lookups against any of those tokens hit. `raw_annotations` is the
    per-clip detail (path, description, keywords) for review or sidecar use.
    """
    broll_dir = Path(broll_dir)
    clips = sorted(p for p in broll_dir.rglob("*") if p.suffix.lower() in VIDEO_EXTS)
    index: dict[str, str] = {}
    raw: dict[str, dict[str, Any]] = {}
    for clip in clips:
        if progress:
            progress(f"analyze {clip.name}")
        try:
            frames = extract_frames(clip, n=3)
            ann = describe_clip(frames, client=client, model=model)
        except Exception as e:
            ann = {"description": "", "keywords": [], "error": str(e)}
        key = _index_key(clip, ann)
        index[key] = str(clip.resolve())
        raw[str(clip.resolve())] = {
            "filename": clip.name,
            "description": ann.get("description", ""),
            "keywords": ann.get("keywords", []),
            **({"error": ann["error"]} if "error" in ann else {}),
        }
    return index, raw


def _index_key(clip: Path, ann: dict[str, Any]) -> str:
    desc = ann.get("description", "")
    kws = ", ".join(ann.get("keywords", []))
    return f"{clip.name} :: {desc} :: {kws}".strip(" :")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def ingest_library(
    interview: str | Path,
    broll_dir: str | Path,
    out_dir: str | Path,
    *,
    whisper_model: str = "small.en",
    vision_model: str = DEFAULT_VISION_MODEL,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run full ingest: transcribe the interview, analyze B-roll, write artifacts."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress(f"transcribe {Path(interview).name}")
    transcript = transcribe_interview(interview, model=whisper_model)
    transcripts_path = out_dir / "transcripts.json"
    transcripts_path.write_text(json.dumps({str(interview): transcript}, indent=2))

    index, raw = build_footage_map(broll_dir, model=vision_model, progress=progress)
    footage_path = out_dir / "footage_map.json"
    footage_path.write_text(json.dumps(index, indent=2))
    annotations_path = out_dir / "footage_annotations.json"
    annotations_path.write_text(json.dumps(raw, indent=2))

    return {
        "ok": True,
        "transcripts": str(transcripts_path),
        "footage_map": str(footage_path),
        "footage_annotations": str(annotations_path),
        "clip_count": len(index),
    }
