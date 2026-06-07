"""Silence-aware cut planning — the single-speaker counterpart to diarize.py.

Given a WhisperX transcript with word-level timestamps, produces a cut plan
(timeline ranges to DELETE) that removes silences longer than a threshold.
No diarization needed, so no HF_TOKEN — this is the lighter path for
interviews with a single speaker.

The output shape matches `plan_speaker_cuts()` so the same downstream
"apply cuts to Resolve in reverse-TC order" loop works for both.
"""

from __future__ import annotations

from typing import Any, Iterable


def plan_silence_cuts(
    transcript: dict[str, Any],
    *,
    min_gap: float = 0.4,
    merge_gap: float = 0.3,
    pad_start: float = 0.0,
    pad_end: float = 0.0,
    min_cut_duration: float = 0.1,
    cut_leading: bool = True,
    cut_trailing: bool = True,
    duration: float | None = None,
) -> dict[str, Any]:
    """Plan cuts at silences in a WhisperX-shaped transcript.

    A "silence" is any gap between consecutive words longer than `min_gap`,
    plus optionally the lead-in before the first word and the lead-out
    after the last word.

    Args:
        transcript: WhisperX-shaped dict with `segments[*].words[*]`.
        min_gap: gaps shorter than this are kept (natural breath).
        merge_gap: cuts within this distance of each other are merged.
        pad_start: inward trim from each cut's start (keep some pre-word breath).
        pad_end: inward trim from each cut's end (keep some pre-word breath).
        min_cut_duration: drop cuts shorter than this after padding/merging.
        cut_leading: emit a cut for silence before the first word.
        cut_trailing: emit a cut for silence after the last word (needs `duration`).
        duration: total clip duration; required if `cut_trailing` is True.

    Returns:
        Same shape as plan_speaker_cuts(): {"cuts": [...], "summary": {...}}.
    """
    words = list(_iter_words(transcript))
    words.sort(key=lambda w: w["start"])

    raw_cuts: list[tuple[float, float]] = []

    if cut_leading and words:
        first_start = words[0]["start"]
        if first_start > min_gap:
            raw_cuts.append((0.0, first_start))

    for prev, cur in zip(words, words[1:]):
        gap_start = prev["end"]
        gap_end = cur["start"]
        if gap_end - gap_start > min_gap:
            raw_cuts.append((gap_start, gap_end))

    if cut_trailing and words and duration is not None:
        last_end = words[-1]["end"]
        if duration - last_end > min_gap:
            raw_cuts.append((last_end, float(duration)))

    if pad_start or pad_end:
        raw_cuts = [(s + pad_start, e - pad_end) for s, e in raw_cuts]
        raw_cuts = [(s, e) for s, e in raw_cuts if e > s]

    raw_cuts.sort()
    merged: list[tuple[float, float]] = []
    for s, e in raw_cuts:
        if merged and s - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    cuts = [
        {"start": round(s, 3), "end": round(e, 3), "reason": "silence"}
        for s, e in merged
        if (e - s) >= min_cut_duration
    ]

    cut_duration = sum(c["end"] - c["start"] for c in cuts)
    original = float(duration) if duration is not None else (words[-1]["end"] if words else 0.0)
    return {
        "cuts": cuts,
        "summary": {
            "original_duration": round(original, 2),
            "cut_duration": round(cut_duration, 2),
            "kept_duration": round(max(original - cut_duration, 0.0), 2),
            "cut_count": len(cuts),
        },
    }


def _iter_words(transcript: dict[str, Any]) -> Iterable[dict[str, float]]:
    for seg in transcript.get("segments") or []:
        for w in seg.get("words") or []:
            try:
                start = float(w["start"])
                end = float(w["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if end <= start:
                continue
            yield {"start": start, "end": end}
