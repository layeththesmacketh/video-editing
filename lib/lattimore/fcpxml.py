"""Direct FCPXML 1.10 emitter for DaVinci Resolve / Final Cut Pro X import.

We bypass the otio-fcpx-xml-lite-adapter for the keeps-timeline use case
because its output is structurally wrong for Resolve:

  - wraps everything in <gap name="Timeline Container"> instead of placing
    asset-clips directly in <spine>
  - puts asset-clips on lane="1" (secondary lane) instead of the primary
    lane, which Resolve interprets as picture-in-picture
  - omits <library>/<event> wrappers (required >= FCPXML 1.5)
  - declares fcpxml version 1.13 which Resolve 18.x rejects
  - omits uid/sig identifiers that Resolve uses for cross-machine relink
  - emits separate video and audio asset-clips when one asset-clip with
    audioRole="dialogue" carries both

This module produces XML modeled on a known-good Final Cut Pro export
(see vendor/cutlass/samples/simple_video1.fcpxml). Resolve handles this
format reliably for the offline-relink workflow.

Used by build_keeps_timeline's FCPXML export path (the keeps timeline is
a single source clip lifted into multiple sub-ranges, butted together on
V1 + A1 — exactly what this emitter is shaped for).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr


FCPXML_VERSION = "1.10"
DEFAULT_RATE = 24
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_AUDIO_RATE = 48000
DEFAULT_AUDIO_CHANNELS = 2


def build_keeps_fcpxml(
    source_clip: str | Path,
    source_duration: float,
    keeps: list[dict[str, float]],
    *,
    project_name: str = "lattimore_keeps",
    event_name: str = "lattimore",
    rate: int = DEFAULT_RATE,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    audio_rate: int = DEFAULT_AUDIO_RATE,
    audio_channels: int = DEFAULT_AUDIO_CHANNELS,
) -> str:
    """Build a Resolve-compatible FCPXML string for a sequence of `keeps`
    ranges lifted from a single source clip and butted together.

    Args:
        source_clip: absolute path to the source file, OR a bare filename.
                     If absolute, src URL preserves the path so Resolve can
                     relink in one click. If bare, the URL points to a
                     placeholder location and Resolve marks the clip
                     offline for manual relink.
        source_duration: total runtime of the source file in seconds.
        keeps: list of {"start": float, "end": float} ranges to keep
               (in source-clip time, in seconds).
        project_name, event_name: shown in Resolve's media pool.
        rate: timeline frame rate (integer; 24, 25, 30, 60 etc).
    """
    source_path = Path(str(source_clip))
    source_name = source_path.stem  # e.g. "Dejha_LoHi_Commissioner_Interview"
    source_filename = source_path.name  # e.g. "Dejha_LoHi_Commissioner_Interview.mov"

    if source_path.is_absolute():
        src_url = source_path.as_uri()
    else:
        # Placeholder absolute path so Resolve still has a directory hint
        # to mark the clip "offline at this location" — the user clicks
        # Relink Selected Clips and points at the real folder.
        src_url = f"file:///Volumes/RELINK/{source_filename}"

    source_uid = _stable_uid(source_filename)
    project_uid = _new_uid()
    event_uid = _new_uid()

    source_duration_frames = round(source_duration * rate)
    keep_clips_xml: list[str] = []
    timeline_offset = 0
    for keep in keeps:
        in_frames = round(float(keep["start"]) * rate)
        dur_frames = round((float(keep["end"]) - float(keep["start"])) * rate)
        if dur_frames <= 0:
            continue
        keep_clips_xml.append(
            f'                    <asset-clip ref="r2" '
            f'offset="{timeline_offset}/{rate}s" '
            f'name={quoteattr(source_name)} '
            f'duration="{dur_frames}/{rate}s" '
            f'start="{in_frames}/{rate}s" '
            f'tcFormat="NDF" '
            f'audioRole="dialogue"/>'
        )
        timeline_offset += dur_frames

    sequence_duration_frames = timeline_offset
    audio_rate_k = audio_rate // 1000

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>

<fcpxml version="{FCPXML_VERSION}">
    <resources>
        <format id="r1" name="FFVideoFormat{height}p{rate}" frameDuration="1/{rate}s" width="{width}" height="{height}" colorSpace="1-1-1 (Rec. 709)"/>
        <asset id="r2" name={quoteattr(source_name)} uid="{source_uid}" start="0s" duration="{source_duration_frames}/{rate}s" hasVideo="1" hasAudio="1" videoSources="1" audioSources="1" audioChannels="{audio_channels}" audioRate="{audio_rate}">
            <media-rep kind="original-media" sig="{source_uid}" src={quoteattr(src_url)}/>
        </asset>
    </resources>
    <library>
        <event name={quoteattr(event_name)} uid="{event_uid}">
            <project name={quoteattr(project_name)} uid="{project_uid}">
                <sequence format="r1" duration="{sequence_duration_frames}/{rate}s" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="{audio_rate_k}k">
                    <spine>
{chr(10).join(keep_clips_xml)}
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>
"""


def _stable_uid(seed: str) -> str:
    """Deterministic UUID-style hex from a seed. Stable across runs so the
    asset identity persists if the user re-exports."""
    return hashlib.md5(seed.encode("utf-8")).hexdigest().upper()


def _new_uid() -> str:
    """New uppercase UUID for event/project IDs."""
    return str(uuid.uuid4()).upper()
