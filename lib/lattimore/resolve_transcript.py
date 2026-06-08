"""Parser for DaVinci Resolve's transcription export (.txt format).

Format:
    [HH:MM:SS:FF - HH:MM:SS:FF]
    Speaker N
    text content

    [HH:MM:SS:FF - HH:MM:SS:FF]
    Speaker M
    text content

    [HH:MM:SS:FF - HH:MM:SS:FF]
     (Claps)             # bracketed non-speech, no speaker line

Notes:
  - Timecodes are HH:MM:SS:FF at the timeline frame rate (default 24).
  - Some blocks have no speaker line (non-speech events). We skip those for
    diarization purposes but keep them in the text record.
  - This format DOES carry speaker labels, unlike Resolve's SRT/TTML exports
    which strip them. Use this as the input to plan_speaker_cuts.

Produces a dict shaped like the output of diarize_interview() — same
`diarization` and `segments` fields — so plan_speaker_cuts and
speaker_breakdown work on it unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .timeline import parse_timecode


_HEADER_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2}:\d{2})\]\s*$"
)
_SPEAKER_RE = re.compile(r"^Speaker\s+(\S+)\s*$")


def parse_resolve_transcript(
    path: str | Path,
    *,
    rate: float = 24.0,
) -> dict[str, Any]:
    """Parse Resolve's transcription .txt export.

    Returns a dict in the same shape as diarize_interview()'s output, so
    speaker_breakdown() and plan_speaker_cuts() consume it directly.
    """
    text = Path(path).read_text()
    blocks = _split_blocks(text)

    segments: list[dict[str, Any]] = []
    diarization: list[dict[str, Any]] = []
    speakers: set[str] = set()
    duration = 0.0

    for block in blocks:
        if not block:
            continue
        start, end, speaker, content = _parse_block(block, rate=rate)
        if start is None:
            continue
        duration = max(duration, end)
        segments.append({
            "start": start,
            "end": end,
            "text": content,
            "speaker": speaker,
            "words": [],
        })
        if speaker:
            speakers.add(speaker)
            diarization.append({
                "start": start,
                "end": end,
                "speaker": speaker,
            })

    diarization.sort(key=lambda r: (r["start"], r["end"]))

    return {
        "clip": str(path),
        "language": "en",
        "duration": duration,
        "speakers": sorted(speakers),
        "diarization": diarization,
        "segments": segments,
    }


def _split_blocks(text: str) -> list[list[str]]:
    """Group consecutive non-blank lines into blocks separated by blank lines."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_block(
    lines: list[str], *, rate: float,
) -> tuple[float | None, float, str | None, str]:
    """Parse one block: header line, optional speaker line, content lines.

    Returns (start_seconds, end_seconds, speaker_label_or_None, text). If the
    header doesn't match, returns (None, 0.0, None, "") so the caller skips.
    """
    if not lines:
        return None, 0.0, None, ""

    m = _HEADER_RE.match(lines[0].strip())
    if not m:
        return None, 0.0, None, ""

    start = parse_timecode(m.group(1), rate=rate)
    end = parse_timecode(m.group(2), rate=rate)

    speaker: str | None = None
    body_lines = lines[1:]
    if body_lines:
        sm = _SPEAKER_RE.match(body_lines[0].strip())
        if sm:
            speaker = f"Speaker {sm.group(1)}"
            body_lines = body_lines[1:]

    text = " ".join(ln.strip() for ln in body_lines).strip()
    return start, end, speaker, text
