"""Tests for the direct FCPXML emitter. Validates the structure matches
what known-good Final Cut Pro / Resolve FCPXML files use, in particular
matching the reference at vendor/cutlass/samples/simple_video1.fcpxml.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from lattimore.fcpxml import build_keeps_fcpxml


@pytest.fixture
def keeps_xml():
    keeps = [
        {"start": 0.0, "end": 5.0},
        {"start": 10.0, "end": 20.0},
        {"start": 30.0, "end": 35.0},
    ]
    return build_keeps_fcpxml(
        "/Volumes/Footage/Test_Interview.mov",
        60.0,
        keeps,
        project_name="TestProject",
        rate=24,
    )


def test_well_formed_xml(keeps_xml):
    ET.fromstring(keeps_xml)


def test_fcpxml_version_is_1_10(keeps_xml):
    root = ET.fromstring(keeps_xml)
    assert root.tag == "fcpxml"
    assert root.get("version") == "1.10"


def test_has_library_event_project_wrappers(keeps_xml):
    """Resolve requires <library><event><project>...</project></event></library>."""
    root = ET.fromstring(keeps_xml)
    lib = root.find("library")
    assert lib is not None
    evt = lib.find("event")
    assert evt is not None
    prj = evt.find("project")
    assert prj is not None
    assert prj.get("name") == "TestProject"


def test_asset_name_is_stem_without_extension(keeps_xml):
    """Final Cut convention: asset name = file stem, NOT the full filename
    with extension. The .mov extension only appears in the src URL."""
    root = ET.fromstring(keeps_xml)
    asset = root.find(".//asset")
    assert asset.get("name") == "Test_Interview"


def test_asset_has_uid_for_relink(keeps_xml):
    """Resolve uses uid/sig for stable asset identity across exports."""
    root = ET.fromstring(keeps_xml)
    asset = root.find(".//asset")
    assert asset.get("uid"), "asset must have uid"
    mr = asset.find("media-rep")
    assert mr.get("sig") == asset.get("uid"), "media-rep sig must match asset uid"


def test_media_rep_src_preserves_absolute_path(keeps_xml):
    """When given an absolute path, src URL must preserve it so Resolve
    can find/relink the actual file in one click."""
    root = ET.fromstring(keeps_xml)
    mr = root.find(".//media-rep")
    assert mr.get("src") == "file:///Volumes/Footage/Test_Interview.mov"


def test_bare_filename_gets_placeholder_path():
    """A bare filename (no path) becomes a placeholder so Resolve marks
    the clip offline but can still search for the filename on relink."""
    xml = build_keeps_fcpxml(
        "MyInterview.mov", 60.0, [{"start": 0, "end": 10}], rate=24
    )
    root = ET.fromstring(xml)
    mr = root.find(".//media-rep")
    assert "MyInterview.mov" in mr.get("src")
    assert mr.get("src").startswith("file://")


def test_asset_clip_name_matches_asset_name(keeps_xml):
    """Asset-clip name should match the asset name (both = stem). This is
    what Resolve shows on each timeline clip; matching the asset name
    makes the media pool / timeline visually consistent."""
    root = ET.fromstring(keeps_xml)
    asset = root.find(".//asset")
    clips = root.findall(".//asset-clip")
    for c in clips:
        assert c.get("name") == asset.get("name")


def test_asset_clips_on_primary_lane_not_secondary(keeps_xml):
    """The OTIO adapter incorrectly emits asset-clips on lane='1' (secondary
    PIP lane). They must be on the primary lane (no lane attribute, or 0)
    so Resolve plays them as the main video."""
    root = ET.fromstring(keeps_xml)
    for c in root.findall(".//asset-clip"):
        lane = c.get("lane")
        assert lane in (None, "0"), f"asset-clip on wrong lane: {lane}"


def test_asset_clips_directly_in_spine_not_in_gap(keeps_xml):
    """asset-clips must be direct children of <spine>, not wrapped in a
    <gap name='Timeline Container'> which is how the OTIO adapter does it."""
    root = ET.fromstring(keeps_xml)
    spine = root.find(".//spine")
    assert spine is not None
    direct_clips = spine.findall("asset-clip")
    assert len(direct_clips) == 3, "asset-clips must be direct children of <spine>"
    assert spine.find("gap") is None, "<gap> wrapper not allowed"


def test_asset_clips_have_audioRole(keeps_xml):
    """audioRole='dialogue' on each asset-clip means it plays BOTH video
    and audio from the source. Without this, audio doesn't import."""
    root = ET.fromstring(keeps_xml)
    for c in root.findall(".//asset-clip"):
        assert c.get("audioRole") == "dialogue"


def test_keep_ranges_butted_together(keeps_xml):
    """Each asset-clip's offset on the timeline = sum of previous clips'
    durations. No gaps between keeps on the new timeline."""
    root = ET.fromstring(keeps_xml)
    clips = root.findall(".//asset-clip")
    expected_offsets = ["0/24s", "120/24s", "360/24s"]  # 0, 5s*24, (5+10)s*24
    for c, expected in zip(clips, expected_offsets):
        assert c.get("offset") == expected


def test_keep_source_in_points_correct(keeps_xml):
    """Each asset-clip's start = the source-clip time of the kept range."""
    root = ET.fromstring(keeps_xml)
    clips = root.findall(".//asset-clip")
    # keeps: 0-5, 10-20, 30-35 → start frames: 0, 240, 720
    assert clips[0].get("start") == "0/24s"
    assert clips[1].get("start") == "240/24s"
    assert clips[2].get("start") == "720/24s"


def test_asset_declares_video_and_audio(keeps_xml):
    root = ET.fromstring(keeps_xml)
    asset = root.find(".//asset")
    assert asset.get("hasVideo") == "1"
    assert asset.get("hasAudio") == "1"
    assert asset.get("audioChannels") == "2"
    assert asset.get("audioRate") == "48000"


def test_sequence_duration_equals_sum_of_keeps(keeps_xml):
    """Sequence duration must equal the sum of kept durations (no gaps)."""
    root = ET.fromstring(keeps_xml)
    seq = root.find(".//sequence")
    # 5+10+5 = 20s = 480 frames at 24fps
    assert seq.get("duration") == "480/24s"


def test_event_and_project_have_uids(keeps_xml):
    root = ET.fromstring(keeps_xml)
    evt = root.find(".//event")
    prj = root.find(".//project")
    assert evt.get("uid")
    assert prj.get("uid")
    assert len(evt.get("uid")) >= 32
    assert len(prj.get("uid")) >= 32


def test_name_with_special_characters_is_escaped():
    """Names with quotes/ampersands must be properly XML-escaped."""
    xml = build_keeps_fcpxml(
        "Interview & Co \"Final\".mov",
        60.0,
        [{"start": 0, "end": 10}],
        rate=24,
    )
    ET.fromstring(xml)  # well-formed
    root = ET.fromstring(xml)
    asset = root.find(".//asset")
    assert "&" in asset.get("name") or "&amp;" not in asset.get("name")
