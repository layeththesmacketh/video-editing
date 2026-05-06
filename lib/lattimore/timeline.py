"""Multi-track OTIO timeline construction and export.

Schema:

    {
        "aroll": [{"clip": str, "in": float, "out": float}],
        "broll": [{"clip": str, "in": float, "out": float,
                   "over_aroll_at": float, "audio": bool}],
        "music": [{"clip": str, "in": float, "duration": float}],
    }

Tracks built:
    V1 — A-roll (interview)              kind=Video
    V2 — B-roll lay-overs                kind=Video
    A1 — interview dialog (sync to V1)   kind=Audio
    A2 — music bed                       kind=Audio
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import opentimelineio as otio


DEFAULT_RATE = 24.0


def parse_timecode(tc: str, rate: float = DEFAULT_RATE) -> float:
    """Parse 'HH:MM:SS:FF' (or 'HH:MM:SS.sss') into seconds."""
    if ":" in tc and tc.count(":") == 3:
        hh, mm, ss, ff = tc.split(":")
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ff) / rate
    if tc.count(":") == 2:
        hh, mm, rest = tc.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(rest)
    raise ValueError(f"unrecognized timecode: {tc!r}")


def timecode(seconds: float, rate: float = DEFAULT_RATE) -> str:
    """Format seconds as 'HH:MM:SS:FF' at the given frame rate."""
    if seconds < 0:
        raise ValueError("negative seconds")
    total_frames = round(seconds * rate)
    frames = int(total_frames % rate)
    total_seconds = total_frames // rate
    ss = int(total_seconds % 60)
    mm = int((total_seconds // 60) % 60)
    hh = int(total_seconds // 3600)
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{frames:02d}"


def _rt(seconds: float, rate: float) -> otio.opentime.RationalTime:
    return otio.opentime.RationalTime(round(seconds * rate), rate)


def _range(start: float, duration: float, rate: float) -> otio.opentime.TimeRange:
    return otio.opentime.TimeRange(start_time=_rt(start, rate), duration=_rt(duration, rate))


def _media_ref(clip_path: str) -> otio.schema.ExternalReference:
    return otio.schema.ExternalReference(target_url=Path(clip_path).as_uri() if not clip_path.startswith("file://") else clip_path)


def build_timeline(
    schema: dict[str, list[dict[str, Any]]],
    name: str = "lattimore_roughcut",
    rate: float = DEFAULT_RATE,
) -> otio.schema.Timeline:
    """Build an OTIO Timeline from the multi-track schema."""
    aroll = schema.get("aroll", []) or []
    broll = schema.get("broll", []) or []
    music = schema.get("music", []) or []

    tl = otio.schema.Timeline(name=name)
    tl.global_start_time = _rt(0.0, rate)

    v1 = otio.schema.Track(name="V1_AROLL", kind=otio.schema.TrackKind.Video)
    v2 = otio.schema.Track(name="V2_BROLL", kind=otio.schema.TrackKind.Video)
    a1 = otio.schema.Track(name="A1_DIALOG", kind=otio.schema.TrackKind.Audio)
    a2 = otio.schema.Track(name="A2_MUSIC", kind=otio.schema.TrackKind.Audio)

    # V1 A-roll + A1 dialog (mirrored).
    timeline_t = 0.0
    aroll_landings: list[tuple[float, float]] = []  # (timeline_start, duration)
    for sel in aroll:
        src_in = float(sel["in"])
        src_out = float(sel["out"])
        dur = src_out - src_in
        if dur <= 0:
            raise ValueError(f"non-positive A-roll duration: {sel}")
        clip_v = otio.schema.Clip(
            name=Path(sel["clip"]).stem,
            media_reference=_media_ref(sel["clip"]),
            source_range=_range(src_in, dur, rate),
        )
        clip_a = otio.schema.Clip(
            name=Path(sel["clip"]).stem + "_dialog",
            media_reference=_media_ref(sel["clip"]),
            source_range=_range(src_in, dur, rate),
        )
        v1.append(clip_v)
        a1.append(clip_a)
        aroll_landings.append((timeline_t, dur))
        timeline_t += dur

    total_runtime = timeline_t

    # V2 B-roll lay-overs.  Place by `over_aroll_at` (timeline-second).
    v2_cursor = 0.0
    sorted_broll = sorted(broll, key=lambda b: float(b["over_aroll_at"]))
    for lay in sorted_broll:
        src_in = float(lay["in"])
        src_out = float(lay["out"])
        dur = src_out - src_in
        if dur <= 0:
            raise ValueError(f"non-positive B-roll duration: {lay}")
        place_at = float(lay["over_aroll_at"])
        if place_at < v2_cursor:
            raise ValueError(f"B-roll overlap on V2 at t={place_at} (cursor={v2_cursor})")
        gap = place_at - v2_cursor
        if gap > 1e-6:
            v2.append(otio.schema.Gap(source_range=_range(0.0, gap, rate)))
        v2.append(
            otio.schema.Clip(
                name=Path(lay["clip"]).stem,
                media_reference=_media_ref(lay["clip"]),
                source_range=_range(src_in, dur, rate),
                metadata={"lattimore": {"audio": bool(lay.get("audio", False))}},
            )
        )
        v2_cursor = place_at + dur

    # A2 music bed.
    a2_cursor = 0.0
    for m in music:
        start = float(m.get("in", a2_cursor))
        dur = float(m["duration"])
        if start < a2_cursor:
            raise ValueError(f"music overlap on A2 at t={start}")
        gap = start - a2_cursor
        if gap > 1e-6:
            a2.append(otio.schema.Gap(source_range=_range(0.0, gap, rate)))
        a2.append(
            otio.schema.Clip(
                name=Path(m["clip"]).stem,
                media_reference=_media_ref(m["clip"]),
                source_range=_range(0.0, dur, rate),
            )
        )
        a2_cursor = start + dur

    tl.tracks.append(v1)
    tl.tracks.append(v2)
    tl.tracks.append(a1)
    tl.tracks.append(a2)

    tl.metadata["lattimore"] = {
        "rate": rate,
        "total_runtime": total_runtime,
        "track_layout": ["V1_AROLL", "V2_BROLL", "A1_DIALOG", "A2_MUSIC"],
    }
    return tl


# Adapter names. FCPX (Final Cut Pro X) is shipped by the third-party
# `otio-fcpx-xml-lite-adapter` package as `otio_fcpx_xml_lite_adapter`.
# Premiere uses the FCP7-style `fcp_xml` adapter. EDL is `cmx_3600`.
_ADAPTERS = {
    "fcpxml": "otio_fcpx_xml_lite_adapter",
    "fcpx": "otio_fcpx_xml_lite_adapter",
    "xml": "fcp_xml",
    "premiere": "fcp_xml",
    "edl": "cmx_3600",
    "cmx": "cmx_3600",
    "otio": "otio_json",
    "json": "otio_json",
}


def export_timeline(
    tl: otio.schema.Timeline,
    out_path: str | Path,
    fmt: str | None = None,
) -> Path:
    """Export an OTIO timeline via the named adapter.

    `fmt` is one of: fcpxml, xml (Premiere), edl, otio. Inferred from extension if omitted.
    """
    out_path = Path(out_path)
    key = (fmt or out_path.suffix.lstrip(".")).lower()
    adapter = _ADAPTERS.get(key)
    if adapter is None:
        raise ValueError(f"unsupported export format: {key}")
    otio.adapters.write_to_file(tl, str(out_path), adapter_name=adapter)
    return out_path
