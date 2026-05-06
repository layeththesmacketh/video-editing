"""Paper-edit helpers: filter WhisperX candidates and validate selects."""

from __future__ import annotations

from typing import Any, Iterable


ROLES = ("hook", "premise", "texture", "turn", "resolve")


def filter_candidates(
    transcript: dict[str, Any],
    *,
    min_duration: float = 1.5,
    max_duration: float = 12.0,
    drop_fillers: bool = True,
) -> list[dict[str, Any]]:
    """Filter WhisperX segments into plausible paper-edit candidates.

    `transcript` is a WhisperX-style dict: `{"segments": [{"start", "end", "text", "words": [...]}, ...]}`.
    Returns a list of `{clip, in, out, text, words}`. The `clip` key is taken from
    `transcript.get("clip")` if present, else "" (caller fills in).
    """
    clip = transcript.get("clip", "")
    out: list[dict[str, Any]] = []
    fillers = {"um", "uh", "you know", "like"}
    for seg in transcript.get("segments", []):
        words = seg.get("words") or []
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg["start"])
        end = float(seg["end"])
        dur = end - start
        if dur < min_duration or dur > max_duration:
            continue
        if drop_fillers and text.lower().strip(".,!?-—") in fillers:
            continue
        # Snap to word boundaries if available.
        if words:
            start = float(words[0].get("start", start))
            end = float(words[-1].get("end", end))
        out.append(
            {
                "clip": clip,
                "in": start,
                "out": end,
                "text": text,
                "words": words,
            }
        )
    return out


def validate_paper_edit(
    selects: Iterable[dict[str, Any]],
    *,
    target_runtime: float,
    tolerance: float = 0.10,
) -> dict[str, Any]:
    """Validate a paper edit against Lattimore's hard rules.

    Returns `{"ok": bool, "errors": [...], "warnings": [...], "runtime": float}`.
    Errors:
      - role not in ROLES
      - non-positive duration
      - mid-word cut (when `words` present and boundaries don't align)
      - runtime outside ±tolerance of target
    """
    errors: list[str] = []
    warnings: list[str] = []
    runtime = 0.0
    selects = list(selects)

    for i, s in enumerate(selects):
        role = s.get("role")
        if role not in ROLES:
            errors.append(f"select #{i}: role {role!r} not in {ROLES}")
        try:
            dur = float(s["out"]) - float(s["in"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"select #{i}: missing or non-numeric in/out")
            continue
        if dur <= 0:
            errors.append(f"select #{i}: non-positive duration {dur}")
            continue
        runtime += dur

        # Mid-word check: if a `words` array is present on the select, both
        # `in` and `out` must coincide with a word boundary.
        words = s.get("words") or []
        if words:
            edges = set()
            for w in words:
                if "start" in w:
                    edges.add(round(float(w["start"]), 3))
                if "end" in w:
                    edges.add(round(float(w["end"]), 3))
            if round(float(s["in"]), 3) not in edges:
                errors.append(f"select #{i}: in {s['in']} is not a word boundary (mid-word cut)")
            if round(float(s["out"]), 3) not in edges:
                errors.append(f"select #{i}: out {s['out']} is not a word boundary (mid-word cut)")

    if target_runtime > 0:
        drift = abs(runtime - target_runtime) / target_runtime
        if drift > tolerance:
            errors.append(
                f"runtime {runtime:.2f}s is {drift*100:.1f}% off target {target_runtime:.2f}s "
                f"(tolerance ±{tolerance*100:.0f}%)"
            )

    # Arc warnings (not errors — material may not support all roles).
    roles_present = [s.get("role") for s in selects]
    if "hook" not in roles_present:
        warnings.append("no hook select — first 3–7s won't carry weight")
    if "resolve" not in roles_present:
        warnings.append("no resolve select — piece will not land")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "runtime": runtime}
