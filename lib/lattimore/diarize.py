"""Speaker diarization + speaker-aware cut planning.

Layered on top of WhisperX (already used for transcription). Diarization is
handled by pyannote, which whisperx wraps via `DiarizationPipeline`. Requires
a HuggingFace token (`HF_TOKEN`) and the user must have accepted the model
terms at:

  - https://hf.co/pyannote/speaker-diarization-3.1
  - https://hf.co/pyannote/segmentation-3.0

Three responsibilities:

  1. `diarize_interview()`  — transcribe + diarize + assign speaker per word.
  2. `speaker_breakdown()`  — per-speaker stats + sample quotes for review.
  3. `plan_speaker_cuts()`  — given which speakers to KEEP, return the list
                              of timeline ranges to DELETE. Silences (no one
                              talking) are preserved.

The cut planner is pure logic over the diarization ranges — no whisperx
required to test it. Keep it that way.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Diarization (WhisperX + pyannote)
# ---------------------------------------------------------------------------

def diarize_interview(
    video_path: str | Path,
    *,
    hf_token: str | None = None,
    whisper_model: str = "small.en",
    device: str | None = None,
    language: str = "en",
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    num_speakers: int | None = None,
) -> dict[str, Any]:
    """Transcribe + diarize a video. Returns a WhisperX-shaped transcript with
    a `speaker` label on every word, plus a `diarization` list of speaker
    ranges and the sorted set of `speakers`.

    `hf_token` defaults to `os.environ["HF_TOKEN"]`. If neither is set, raises.
    """
    try:
        import whisperx  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "whisperx not installed. Install ingest extras: "
            "pip install -e '.[ingest]'"
        ) from e

    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN not set — pyannote diarization needs a HuggingFace token. "
            "Get one at https://huggingface.co/settings/tokens and accept the "
            "model terms at https://hf.co/pyannote/speaker-diarization-3.1 and "
            "https://hf.co/pyannote/segmentation-3.0."
        )

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    # Lazy import — keeps tests of plan_speaker_cuts() pure.
    from .ingest import _cuda_available
    device = device or ("cuda" if _cuda_available() else "cpu")
    compute_type = "float16" if device == "cuda" else "int8"

    asr = whisperx.load_model(whisper_model, device, compute_type=compute_type, language=language)
    audio = whisperx.load_audio(str(video_path))
    result = asr.transcribe(audio, batch_size=8 if device == "cuda" else 4)

    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    aligned = whisperx.align(
        result["segments"], align_model, metadata, audio, device,
        return_char_alignments=False,
    )

    diarize_pipeline = whisperx.DiarizationPipeline(use_auth_token=token, device=device)
    diarize_kwargs: dict[str, Any] = {}
    if num_speakers is not None:
        diarize_kwargs["num_speakers"] = num_speakers
    else:
        if min_speakers is not None:
            diarize_kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            diarize_kwargs["max_speakers"] = max_speakers
    diarize_df = diarize_pipeline(audio, **diarize_kwargs)

    tagged = whisperx.assign_word_speakers(diarize_df, aligned)

    diarization = _df_to_ranges(diarize_df)
    speakers = sorted({r["speaker"] for r in diarization})
    duration = _duration_from_segments(tagged.get("segments", []))

    return {
        "clip": str(video_path),
        "language": language,
        "duration": duration,
        "speakers": speakers,
        "diarization": diarization,
        "segments": _tag_segment_speakers(tagged.get("segments", [])),
    }


def _df_to_ranges(df: Any) -> list[dict[str, Any]]:
    """Normalize pyannote's diarization DataFrame into a sorted list of dicts."""
    ranges: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ranges.append({
            "start": float(row["start"]),
            "end": float(row["end"]),
            "speaker": str(row["speaker"]),
        })
    ranges.sort(key=lambda r: (r["start"], r["end"]))
    return ranges


def _duration_from_segments(segments: list[dict[str, Any]]) -> float:
    return max((float(s.get("end", 0.0)) for s in segments), default=0.0)


def _tag_segment_speakers(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each segment carries word-level speakers; surface the dominant one on the
    segment too so consumers don't have to derive it."""
    out: list[dict[str, Any]] = []
    for seg in segments:
        words = seg.get("words") or []
        counts: dict[str, float] = {}
        for w in words:
            sp = w.get("speaker")
            if not sp:
                continue
            counts[sp] = counts.get(sp, 0.0) + max(
                float(w.get("end", 0.0)) - float(w.get("start", 0.0)), 0.0
            )
        dominant = max(counts.items(), key=lambda kv: kv[1])[0] if counts else None
        out.append({**seg, "speaker": dominant})
    return out


# ---------------------------------------------------------------------------
# Speaker breakdown (review aid before picking who to keep)
# ---------------------------------------------------------------------------

def speaker_breakdown(
    diarized: dict[str, Any],
    *,
    samples_per_speaker: int = 3,
) -> dict[str, Any]:
    """Summarize a diarized transcript: per-speaker total time, share, and a
    few representative quotes so the editor can identify each speaker."""
    diarization: list[dict[str, Any]] = diarized.get("diarization", [])
    segments: list[dict[str, Any]] = diarized.get("segments", [])
    duration: float = float(diarized.get("duration", 0.0))

    totals: dict[str, float] = {}
    for r in diarization:
        sp = r["speaker"]
        totals[sp] = totals.get(sp, 0.0) + (r["end"] - r["start"])
    speech_total = sum(totals.values())

    samples: dict[str, list[dict[str, Any]]] = {sp: [] for sp in totals}
    for seg in segments:
        sp = seg.get("speaker")
        if not sp or sp not in samples:
            continue
        if len(samples[sp]) >= samples_per_speaker:
            continue
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        samples[sp].append({
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": text[:200],
        })

    rows = []
    for sp, total in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
        first = min((r["start"] for r in diarization if r["speaker"] == sp), default=0.0)
        last = max((r["end"] for r in diarization if r["speaker"] == sp), default=0.0)
        rows.append({
            "label": sp,
            "total_seconds": round(total, 2),
            "share_of_speech": round(total / speech_total, 3) if speech_total else 0.0,
            "share_of_total": round(total / duration, 3) if duration else 0.0,
            "first_appearance": round(first, 2),
            "last_appearance": round(last, 2),
            "sample_quotes": samples.get(sp, []),
        })

    return {
        "duration": round(duration, 2),
        "speech_duration": round(speech_total, 2),
        "silence_duration": round(max(duration - speech_total, 0.0), 2),
        "speakers": rows,
    }


# ---------------------------------------------------------------------------
# Cut planner — the editorial decision
# ---------------------------------------------------------------------------

def plan_speaker_cuts(
    diarized: dict[str, Any],
    keep_speakers: list[str],
    *,
    merge_gap: float = 0.3,
    pad_start: float = 0.0,
    pad_end: float = 0.0,
    min_cut_duration: float = 0.1,
    preserve_interjections: bool = True,
    max_interjection_duration: float = 1.0,
    interjection_window: float = 2.0,
) -> dict[str, Any]:
    """Given a diarized transcript and which speakers to KEEP, return the
    timeline ranges to DELETE.

    A range is cut iff somebody is talking AND no kept speaker is talking
    inside it. Silences (no speaker active anywhere) are PRESERVED.

    Args:
        diarized: output of `diarize_interview()` or `parse_resolve_transcript()`.
                  Only needs `diarization` and `duration`.
        keep_speakers: list of speaker labels. Anything not in this set becomes
                  a candidate for cutting.
        merge_gap: cuts separated by <= this many seconds are merged into one.
        pad_start, pad_end: inward trim on each cut, to avoid clipping the
                  kept speaker's adjacent breath or first/last phoneme.
        min_cut_duration: drop cuts shorter than this after padding/merging.
        preserve_interjections: if True, short non-kept speaker ranges that
                  land between two kept-speaker ranges are TREATED AS KEPT
                  (not cut). This handles "Mhm", "Yep" etc. interrupting the
                  main speaker without producing micro-cuts.
        max_interjection_duration: a non-kept range qualifies as an
                  interjection only if it is no longer than this many seconds.
        interjection_window: a non-kept range is "between kept" only if there
                  is a kept-speaker range within this window before AND after.
    """
    diarization: list[dict[str, Any]] = diarized.get("diarization", [])
    duration: float = float(diarized.get("duration", 0.0))
    keep_set = set(keep_speakers)

    keep_ranges = _merge_overlapping(
        [(r["start"], r["end"]) for r in diarization if r["speaker"] in keep_set]
    )

    other_diarization: list[dict[str, Any]] = [
        r for r in diarization if r["speaker"] not in keep_set
    ]
    preserved_interjections: list[dict[str, Any]] = []
    if preserve_interjections and max_interjection_duration > 0 and keep_ranges:
        filtered: list[dict[str, Any]] = []
        for r in other_diarization:
            dur = r["end"] - r["start"]
            if dur <= max_interjection_duration and _is_sandwiched_by_kept(
                r["start"], r["end"], keep_ranges, interjection_window
            ):
                preserved_interjections.append(r)
                continue
            filtered.append(r)
        other_diarization = filtered

    other_ranges_by_speaker: dict[str, list[tuple[float, float]]] = {}
    for r in other_diarization:
        other_ranges_by_speaker.setdefault(r["speaker"], []).append((r["start"], r["end"]))
    other_ranges = _merge_overlapping(
        [span for spans in other_ranges_by_speaker.values() for span in spans]
    )

    raw_cuts: list[tuple[float, float]] = []
    for start, end in other_ranges:
        for sub in _subtract(start, end, keep_ranges):
            raw_cuts.append(sub)

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

    cuts = []
    for s, e in merged:
        if e - s < min_cut_duration:
            continue
        speakers_in_cut = _speakers_in_range(s, e, diarization, exclude=keep_set)
        cuts.append({
            "start": round(s, 3),
            "end": round(e, 3),
            "speakers": sorted(speakers_in_cut),
        })

    cut_duration = sum(c["end"] - c["start"] for c in cuts)
    return {
        "keep_speakers": list(keep_speakers),
        "cuts": cuts,
        "preserved_interjections": [
            {
                "start": round(r["start"], 3),
                "end": round(r["end"], 3),
                "speaker": r["speaker"],
            }
            for r in preserved_interjections
        ],
        "summary": {
            "original_duration": round(duration, 2),
            "cut_duration": round(cut_duration, 2),
            "kept_duration": round(max(duration - cut_duration, 0.0), 2),
            "cut_count": len(cuts),
            "preserved_interjection_count": len(preserved_interjections),
        },
    }


def _merge_overlapping(spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not spans:
        return []
    spans = sorted(spans)
    out: list[tuple[float, float]] = [spans[0]]
    for s, e in spans[1:]:
        prev_s, prev_e = out[-1]
        if s <= prev_e:
            out[-1] = (prev_s, max(prev_e, e))
        else:
            out.append((s, e))
    return out


def _subtract(
    start: float, end: float, holes: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Return the portions of [start, end] not covered by any hole in `holes`."""
    pieces = [(start, end)]
    for h_s, h_e in holes:
        new_pieces: list[tuple[float, float]] = []
        for s, e in pieces:
            if h_e <= s or h_s >= e:
                new_pieces.append((s, e))
                continue
            if h_s > s:
                new_pieces.append((s, h_s))
            if h_e < e:
                new_pieces.append((h_e, e))
        pieces = new_pieces
        if not pieces:
            return []
    return pieces


def _is_sandwiched_by_kept(
    start: float,
    end: float,
    kept_ranges: list[tuple[float, float]],
    window: float,
) -> bool:
    """True if a kept-speaker range ends within `window` BEFORE `start` AND
    another kept-speaker range starts within `window` AFTER `end`."""
    has_before = any(
        k_end <= start and (start - k_end) <= window
        for _, k_end in kept_ranges
    )
    has_after = any(
        k_start >= end and (k_start - end) <= window
        for k_start, _ in kept_ranges
    )
    return has_before and has_after


def _speakers_in_range(
    start: float, end: float, diarization: list[dict[str, Any]], *, exclude: set[str]
) -> set[str]:
    found: set[str] = set()
    for r in diarization:
        if r["speaker"] in exclude:
            continue
        if r["end"] <= start or r["start"] >= end:
            continue
        found.add(r["speaker"])
    return found
