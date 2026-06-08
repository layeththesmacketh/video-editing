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

import re
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


def _media_ref(
    clip_path: str,
    src_out: float,
    rate: float,
    *,
    headroom: float = 60.0,
) -> otio.schema.ExternalReference:
    """ExternalReference with a populated `available_range`.

    The FCP7 / Premiere XML adapter requires `available_range` on every
    media reference. We don't know the actual source duration here, so we
    declare a range from 0 to `src_out + headroom` — enough to cover the
    span we're using plus slack for trim handles in the NLE.

    Accepts either an absolute path (`/Volumes/X/clip.mov`), a file:// URI,
    or a bare filename (`clip.mov`). For bare filenames the URI is built
    as `file:///<name>` so the FCPXML imports as an offline clip that the
    editor can relink in Resolve.
    """
    if clip_path.startswith("file://"):
        url = clip_path
    else:
        p = Path(clip_path)
        if p.is_absolute():
            url = p.as_uri()
        else:
            # Placeholder absolute path so Resolve has a directory hint to
            # mark "offline at this location" — user clicks Relink and
            # points at the real folder. Matches the FCPXML emitter.
            url = f"file:///Volumes/RELINK/{p.name}"
    available = _range(0.0, max(src_out + headroom, headroom), rate)
    return otio.schema.ExternalReference(target_url=url, available_range=available)


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
            media_reference=_media_ref(sel["clip"], src_out, rate),
            source_range=_range(src_in, dur, rate),
        )
        clip_a = otio.schema.Clip(
            name=Path(sel["clip"]).stem + "_dialog",
            media_reference=_media_ref(sel["clip"], src_out, rate),
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
                media_reference=_media_ref(lay["clip"], src_out, rate),
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
                media_reference=_media_ref(m["clip"], dur, rate),
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

    `fmt` is one of: fcpxml, xml (Premiere/FCP7), edl, otio. Inferred from
    extension if omitted.

    Both the fcpxml-lite and fcp_xml adapters need light post-processing for
    DaVinci Resolve import compatibility — applied automatically here.
    """
    out_path = Path(out_path)
    key = (fmt or out_path.suffix.lstrip(".")).lower()
    adapter = _ADAPTERS.get(key)
    if adapter is None:
        raise ValueError(f"unsupported export format: {key}")
    otio.adapters.write_to_file(tl, str(out_path), adapter_name=adapter)
    if key == "fcpxml":
        _fix_fcpxml_for_resolve(out_path, tl)
    elif key == "xml":
        _fix_fcp7_xml_for_resolve(out_path, tl)
    return out_path


def _fix_fcpxml_for_resolve(out_path: Path, tl: otio.schema.Timeline) -> None:
    """Patch the otio-fcpx-xml-lite-adapter's output for Resolve import:

    1. Set hasAudio="1" on assets when the timeline has an audio track.
    2. Downgrade the fcpxml version from 1.13 to 1.10 — Resolve 18.x rejects
       versions newer than 1.10/1.11 ("Unable to find inherited value for key
       'library'" is the symptom Resolve gives on a too-new file).
    3. Wrap <project> inside <library><event>...</event></library>. Versions
       >= 1.5 of the FCPXML spec require this container; the lite adapter
       skips it, which is the OTHER source of the 'library' error.
    """
    text = out_path.read_text()

    has_audio_track = any(
        t.kind == otio.schema.TrackKind.Audio and len(list(t)) > 0
        for t in tl.tracks
    )
    if has_audio_track and 'hasAudio="0"' in text:
        text = text.replace('hasAudio="0"', 'hasAudio="1"')

    text = re.sub(
        r'<fcpxml version="[\d.]+">',
        '<fcpxml version="1.10">',
        text,
    )

    if "<library>" not in text:
        text = re.sub(
            r'(<project\b[^>]*>)',
            r'<library><event name="lattimore">\1',
            text,
            count=1,
        )
        text = re.sub(
            r'(</project>)',
            r'\1</event></library>',
            text,
            count=1,
        )

    out_path.write_text(text)


def _fix_fcp7_xml_for_resolve(out_path: Path, tl: otio.schema.Timeline) -> None:
    """Patch the otio fcp_xml adapter's output for Resolve import:

    Audio clipitems need a <sourcetrack> element declaring mediatype=audio
    so Resolve knows to read from the source clip's audio track. The OTIO
    adapter doesn't emit this; Resolve will import the audio clipitems as
    silent without it.
    """
    import xml.etree.ElementTree as ET

    tree = ET.parse(out_path)
    root = tree.getroot()

    def _ensure_sourcetrack(clipitem: ET.Element, mediatype: str) -> None:
        if clipitem.find("sourcetrack") is not None:
            return
        st = ET.SubElement(clipitem, "sourcetrack")
        ET.SubElement(st, "mediatype").text = mediatype
        ET.SubElement(st, "trackindex").text = "1"

    for clipitem in root.findall(".//audio/track/clipitem"):
        _ensure_sourcetrack(clipitem, "audio")
    for clipitem in root.findall(".//video/track/clipitem"):
        _ensure_sourcetrack(clipitem, "video")

    for file_el in root.findall(".//file"):
        media = file_el.find("media")
        if media is None:
            continue
        audio = media.find("audio")
        if audio is None:
            continue
        if audio.find("samplecharacteristics") is None:
            sc = ET.SubElement(audio, "samplecharacteristics")
            ET.SubElement(sc, "depth").text = "16"
            ET.SubElement(sc, "samplerate").text = "48000"
        if audio.find("channelcount") is None:
            ET.SubElement(audio, "channelcount").text = "2"

    tree.write(out_path, encoding="UTF-8", xml_declaration=True)


def cuts_to_keeps(
    cuts: list[dict[str, Any]],
    duration: float,
    *,
    min_keep_duration: float = 0.0,
) -> list[dict[str, float]]:
    """Invert a cut plan to a keep plan.

    Given total `duration` and a sorted list of cuts (each with `start`/`end`),
    return the complement: the timeline ranges to KEEP. Used to drive the
    FCPXML-import workflow, where we rebuild the timeline from kept ranges
    rather than splitting + deleting in place (Resolve's API doesn't support
    blade-on-timeline).
    """
    if duration <= 0:
        return []
    sorted_cuts = sorted(
        ({"start": float(c["start"]), "end": float(c["end"])} for c in cuts),
        key=lambda c: c["start"],
    )
    keeps: list[dict[str, float]] = []
    cursor = 0.0
    for c in sorted_cuts:
        s = max(c["start"], cursor)
        e = min(c["end"], duration)
        if s > cursor:
            keeps.append({"start": cursor, "end": s})
        cursor = max(cursor, e)
    if cursor < duration:
        keeps.append({"start": cursor, "end": duration})
    if min_keep_duration > 0:
        keeps = [k for k in keeps if (k["end"] - k["start"]) >= min_keep_duration]
    return keeps


def build_keeps_timeline(
    source_clip: str | Path,
    source_duration: float,
    keeps: list[dict[str, float]],
    *,
    name: str = "keeps",
    rate: float = DEFAULT_RATE,
) -> otio.schema.Timeline:
    """Build an OTIO timeline where V1 (+ A1) is a sequence of `keeps` ranges
    from `source_clip` butted together with no gaps.

    Exported as FCPXML, this is what Resolve's `MediaPool.ImportTimelineFromFile`
    consumes to produce a new timeline of just the kept material — the
    documented workaround for the missing SplitClip API.
    """
    source = str(source_clip)
    tl = otio.schema.Timeline(name=name)
    tl.global_start_time = _rt(0.0, rate)

    v1 = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    a1 = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)

    total_kept = 0.0
    for k in keeps:
        k_in = float(k["start"])
        k_out = float(k["end"])
        k_dur = k_out - k_in
        if k_dur <= 0:
            raise ValueError(f"non-positive keep duration: {k}")
        if k_in < 0 or k_out > source_duration + 1e-6:
            raise ValueError(
                f"keep {k} outside source duration {source_duration}"
            )
        v1.append(otio.schema.Clip(
            name=Path(source).stem,
            media_reference=_media_ref(source, k_out, rate),
            source_range=_range(k_in, k_dur, rate),
        ))
        a1.append(otio.schema.Clip(
            name=Path(source).stem + "_audio",
            media_reference=_media_ref(source, k_out, rate),
            source_range=_range(k_in, k_dur, rate),
        ))
        total_kept += k_dur

    tl.tracks.append(v1)
    tl.tracks.append(a1)
    tl.metadata["lattimore"] = {
        "rate": rate,
        "kind": "keeps",
        "source_clip": source,
        "source_duration": source_duration,
        "keep_count": len(keeps),
        "total_kept": total_kept,
    }
    return tl


def build_cutdown_timeline(
    interview_path: str | Path,
    duration: float,
    soundbites: list[dict[str, Any]],
    *,
    name: str = "cutdown",
    rate: float = DEFAULT_RATE,
) -> otio.schema.Timeline:
    """Cutdown layout for the soundbite splitter.

    V1 + A1: the full interview, end to end (the spine you can scrub).
    V2 + A2: only the soundbite ranges, placed at their original timecodes,
             so it's obvious which segments survived the edit.

    `soundbites` is a list of {"in": float, "out": float, ...}. The full clip
    runs 0..duration; each soundbite is a sub-range of the same source.
    """
    interview_path = str(interview_path)
    tl = otio.schema.Timeline(name=name)
    tl.global_start_time = _rt(0.0, rate)

    v1 = otio.schema.Track(name="V1_MASTER", kind=otio.schema.TrackKind.Video)
    v2 = otio.schema.Track(name="V2_SOUNDBITES", kind=otio.schema.TrackKind.Video)
    a1 = otio.schema.Track(name="A1_MASTER", kind=otio.schema.TrackKind.Audio)
    a2 = otio.schema.Track(name="A2_SOUNDBITES", kind=otio.schema.TrackKind.Audio)

    v1.append(otio.schema.Clip(
        name=Path(interview_path).stem,
        media_reference=_media_ref(interview_path, duration, rate),
        source_range=_range(0.0, duration, rate),
    ))
    a1.append(otio.schema.Clip(
        name=Path(interview_path).stem + "_audio",
        media_reference=_media_ref(interview_path, duration, rate),
        source_range=_range(0.0, duration, rate),
    ))

    v2_cursor = 0.0
    a2_cursor = 0.0
    sorted_sb = sorted(soundbites, key=lambda s: float(s["in"]))
    for s in sorted_sb:
        sb_in = float(s["in"]); sb_out = float(s["out"])
        sb_dur = sb_out - sb_in
        if sb_dur <= 0:
            raise ValueError(f"non-positive soundbite duration: {s}")
        if sb_in < v2_cursor:
            raise ValueError(f"soundbite overlap on V2 at t={sb_in} (cursor={v2_cursor})")
        gap = sb_in - v2_cursor
        if gap > 1e-6:
            v2.append(otio.schema.Gap(source_range=_range(0.0, gap, rate)))
            a2.append(otio.schema.Gap(source_range=_range(0.0, gap, rate)))

        clip_name = (s.get("headline") or Path(interview_path).stem).strip()
        v2.append(otio.schema.Clip(
            name=clip_name,
            media_reference=_media_ref(interview_path, sb_out, rate),
            source_range=_range(sb_in, sb_dur, rate),
            metadata={"lattimore": {"speaker": s.get("speaker", ""), "why": s.get("why", "")}},
        ))
        a2.append(otio.schema.Clip(
            name=clip_name + "_audio",
            media_reference=_media_ref(interview_path, sb_out, rate),
            source_range=_range(sb_in, sb_dur, rate),
        ))
        v2_cursor = sb_out
        a2_cursor = sb_out

    tl.tracks.append(v1)
    tl.tracks.append(v2)
    tl.tracks.append(a1)
    tl.tracks.append(a2)

    tl.metadata["lattimore"] = {
        "rate": rate,
        "kind": "cutdown",
        "duration": duration,
        "soundbite_count": len(sorted_sb),
        "track_layout": ["V1_MASTER", "V2_SOUNDBITES", "A1_MASTER", "A2_SOUNDBITES"],
    }
    return tl
