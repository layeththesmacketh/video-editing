"""B-roll matching and lay-over validation.

`find_footage_url` ports the IM8 bot's `findFootageUrl` from claude.js:
case-insensitive partial match between a keyword and a footage map's keys.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def find_footage_url(keyword: str, footage_map: Mapping[str, str]) -> str | None:
    """Case-insensitive partial match.

    A keyword "vera wang runway" matches any key containing those characters
    in order... actually, mirroring the JS port: the keyword is a substring
    match against each key (lowercased), and the first match wins.

    The port also tries the reverse: each key as a substring of the keyword.
    """
    if not keyword:
        return None
    kw = keyword.lower().strip()
    for key, url in footage_map.items():
        k = key.lower()
        if kw in k or k in kw:
            return url
    return None


def validate_broll(
    broll: Iterable[dict[str, Any]],
    aroll: Iterable[dict[str, Any]],
    *,
    max_coverage: float = 0.60,
    min_gap: float = 0.5,
) -> dict[str, Any]:
    """Validate B-roll lay-overs against Lattimore's hard rules.

    A-roll selects map to timeline-seconds in placement order. Each select
    spans `[timeline_t, timeline_t + (out - in))`. A `role: hook` select
    cannot host any lay-over. A select annotated with `reaction: true`
    cannot host any lay-over.

    Lay-overs come in with `over_aroll_at` (timeline-second) and `in/out`
    (source-clip seconds). Their on-timeline duration is `out - in`.
    """
    errors: list[str] = []
    warnings: list[str] = []
    aroll = list(aroll)
    broll = sorted(broll, key=lambda b: float(b["over_aroll_at"]))

    # Build untouchable spans on the timeline.
    untouchable: list[tuple[float, float, str]] = []
    timeline_t = 0.0
    spans: list[tuple[float, float, dict[str, Any]]] = []
    for s in aroll:
        dur = float(s["out"]) - float(s["in"])
        spans.append((timeline_t, timeline_t + dur, s))
        if s.get("role") == "hook":
            untouchable.append((timeline_t, timeline_t + dur, "hook"))
        if s.get("reaction"):
            untouchable.append((timeline_t, timeline_t + dur, "reaction"))
        timeline_t += dur

    total_runtime = timeline_t
    if total_runtime <= 0:
        return {"ok": False, "errors": ["empty A-roll"], "warnings": [], "coverage": 0.0}

    coverage_sum = 0.0
    prev_end: float | None = None

    for i, b in enumerate(broll):
        t = float(b["over_aroll_at"])
        dur = float(b["out"]) - float(b["in"])
        if dur <= 0:
            errors.append(f"broll #{i}: non-positive duration {dur}")
            continue
        end = t + dur
        coverage_sum += dur

        # Untouchable check.
        for u_start, u_end, kind in untouchable:
            if t < u_end and end > u_start:
                errors.append(
                    f"broll #{i} at t={t:.2f} overlaps {kind} A-roll "
                    f"({u_start:.2f}–{u_end:.2f})"
                )

        # Underlying-clip duration: lay-over must not exceed the underlying A-roll select.
        host = next(((s_start, s_end) for s_start, s_end, _ in spans if s_start <= t < s_end), None)
        if host is None:
            errors.append(f"broll #{i} at t={t:.2f} sits past A-roll end ({total_runtime:.2f})")
        else:
            host_start, host_end = host
            if end > host_end + 1e-6:
                host_dur = host_end - host_start
                errors.append(
                    f"broll #{i} duration {dur:.2f}s exceeds underlying A-roll "
                    f"({host_dur:.2f}s, host {host_start:.2f}–{host_end:.2f})"
                )

        # Adjacency gap.
        if prev_end is not None:
            gap = t - prev_end
            if gap < min_gap - 1e-6:
                errors.append(
                    f"broll #{i} starts {gap:.3f}s after prior lay-over end (need ≥ {min_gap}s)"
                )
        prev_end = end

    coverage = coverage_sum / total_runtime
    if coverage > max_coverage + 1e-6:
        errors.append(
            f"B-roll coverage {coverage*100:.1f}% exceeds max {max_coverage*100:.0f}%"
        )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "coverage": coverage,
        "runtime": total_runtime,
    }


def place_broll(
    keyword: str,
    over_aroll_at: float,
    duration: float,
    footage_map: Mapping[str, str],
    *,
    audio: bool = False,
    src_in: float = 0.0,
) -> dict[str, Any] | None:
    """Compose a single lay-over entry from a keyword + footage map. Returns None if no match."""
    url = find_footage_url(keyword, footage_map)
    if url is None:
        return None
    return {
        "clip": url,
        "in": src_in,
        "out": src_in + duration,
        "over_aroll_at": over_aroll_at,
        "audio": audio,
    }
