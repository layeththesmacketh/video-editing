"""Soundbite splitter: find cohesive standalone statements in an interview.

Different operation from `interview-paper-edit`. That picks one cut sequenced
for arc (hook → premise → ... → resolve). This finds N independent soundbites
suitable for social posts (Reels, TikTok). Each soundbite must:

  - be a complete cohesive thought, comprehensible without prior context
  - sit between 15s and 120s (longer up to ~180s only when cohesion demands it)
  - never start or end mid-word — boundaries snap to WhisperX word edges
  - skip filler, restarts, false starts, off-topic chatter
  - carry a `speaker` label inferred from transcript context
"""

from __future__ import annotations

import json
from typing import Any, Iterable

DEFAULT_MODEL = "claude-sonnet-4-6"
MIN_DURATION = 15.0
MAX_DURATION = 180.0
TARGET_TYPICAL = (20.0, 60.0)

SYSTEM_PROMPT = """\
You are a video editor finding standalone soundbites in an interview transcript
for use as Instagram Reels and TikTok posts.

Rules — these are non-negotiable:

1. Each soundbite must be a COMPLETE cohesive thought. A viewer with zero
   context must understand it. If the speaker references "that" or "it" with
   no antecedent in the soundbite, do not include it.
2. Duration: 15–120 seconds is the sweet spot. Up to ~180s only when
   cohesion truly requires it. Lean shorter when the material allows.
3. NEVER cut mid-word. The `in` and `out` you return MUST coincide exactly
   with word boundary timestamps from the transcript's `words` array.
4. Skip filler ("um", "you know"), restarts, false starts, ramble.
5. If two soundbites would overlap, choose the stronger one. No overlaps.
6. Quality over quantity. Better to return 4 strong soundbites than 12
   mediocre ones.
7. Identify the speaker per soundbite using context (questions vs. answers,
   names, gender pronouns). Use the labels you're given.

Return JSON only — a list of objects. No prose, no markdown fences.

Schema:
[
  {
    "in":  <float, seconds, must equal a word.start in the transcript>,
    "out": <float, seconds, must equal a word.end in the transcript>,
    "speaker": "<one of the speaker labels you were given>",
    "headline": "<≤8 words, what this soundbite is about>",
    "why": "<one short sentence — why this stands alone>"
  }
]
"""


def find_soundbites(
    transcript: dict[str, Any],
    *,
    speakers: list[str],
    target_min: float = MIN_DURATION,
    target_max: float = 120.0,
    model: str = DEFAULT_MODEL,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Call Claude to extract soundbite ranges from a WhisperX transcript.

    `speakers` is the labels you want Claude to use (e.g. ["andrei", "tawny", "both"]).
    """
    if client is None:
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "anthropic SDK not installed. Install ingest extras: "
                "pip install -e '.[ingest]'"
            ) from e
        client = Anthropic()

    user_block = {
        "speakers": speakers,
        "target_duration_range_seconds": [target_min, target_max],
        "transcript": _compact_transcript(transcript),
    }

    msg = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Find soundbites in the following interview. Return JSON only.\n\n"
                + json.dumps(user_block)
            ),
        }],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _parse_response(text)


def _compact_transcript(transcript: dict[str, Any]) -> dict[str, Any]:
    """Trim the transcript to what the model needs: per-segment text plus
    the word array (for boundary snapping)."""
    out_segments: list[dict[str, Any]] = []
    for seg in transcript.get("segments", []):
        words = [
            {"w": w.get("word", ""),
             "s": round(float(w["start"]), 3),
             "e": round(float(w["end"]), 3)}
            for w in (seg.get("words") or [])
            if "start" in w and "end" in w
        ]
        out_segments.append({
            "start": round(float(seg["start"]), 3),
            "end": round(float(seg["end"]), 3),
            "text": (seg.get("text") or "").strip(),
            "words": words,
        })
    return {
        "language": transcript.get("language", "en"),
        "segments": out_segments,
    }


def _parse_response(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"expected JSON list, got {type(data).__name__}")
    out: list[dict[str, Any]] = []
    for s in data:
        out.append({
            "in": float(s["in"]),
            "out": float(s["out"]),
            "speaker": str(s.get("speaker", "")).lower(),
            "headline": str(s.get("headline", "")).strip(),
            "why": str(s.get("why", "")).strip(),
        })
    return out


def validate_soundbites(
    soundbites: Iterable[dict[str, Any]],
    transcript: dict[str, Any],
    *,
    min_dur: float = MIN_DURATION,
    max_dur: float = MAX_DURATION,
) -> dict[str, Any]:
    """Enforce the hard rules. Returns {ok, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    edges: set[float] = set()
    for seg in transcript.get("segments", []):
        for w in (seg.get("words") or []):
            if "start" in w:
                edges.add(round(float(w["start"]), 3))
            if "end" in w:
                edges.add(round(float(w["end"]), 3))

    soundbites = sorted(soundbites, key=lambda s: float(s["in"]))
    prev_end: float | None = None
    for i, s in enumerate(soundbites):
        in_t = float(s["in"]); out_t = float(s["out"])
        dur = out_t - in_t
        if dur < min_dur - 1e-3:
            errors.append(f"soundbite #{i}: duration {dur:.2f}s < min {min_dur}s")
        if dur > max_dur + 1e-3:
            errors.append(f"soundbite #{i}: duration {dur:.2f}s > max {max_dur}s")
        if edges:
            if round(in_t, 3) not in edges:
                errors.append(f"soundbite #{i}: in {in_t} is not a word boundary")
            if round(out_t, 3) not in edges:
                errors.append(f"soundbite #{i}: out {out_t} is not a word boundary")
        if prev_end is not None and in_t < prev_end - 1e-3:
            errors.append(
                f"soundbite #{i} starts at {in_t:.2f} but prior ended at {prev_end:.2f} (overlap)"
            )
        prev_end = out_t

    if not list(soundbites):
        warnings.append("no soundbites returned — the model found no usable cohesive segments")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "count": len(list(soundbites))}
