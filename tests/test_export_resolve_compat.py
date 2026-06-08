"""Tests for the FCPXML/FCP7-XML post-processors that fix Resolve import
compatibility.

These run against real OTIO timelines and verify the generated XML matches
the structure Resolve actually accepts.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from lattimore.timeline import build_keeps_timeline, export_timeline


@pytest.fixture
def sample_timeline():
    keeps = [
        {"start": 0.0, "end": 5.0},
        {"start": 10.0, "end": 20.0},
        {"start": 30.0, "end": 35.0},
    ]
    return build_keeps_timeline(
        "Interview.mov", 60.0, keeps, name="keeps_test", rate=24.0
    )


# ---- FCPXML ----------------------------------------------------------------

def test_fcpxml_version_downgraded_to_1_10(tmp_path: Path, sample_timeline):
    out = tmp_path / "out.fcpxml"
    export_timeline(sample_timeline, out, fmt="fcpxml")
    text = out.read_text()
    assert 'version="1.10"' in text
    assert 'version="1.13"' not in text


def test_fcpxml_wraps_project_in_library_event(tmp_path: Path, sample_timeline):
    """Resolve needs <library><event><project>...</project></event></library>.
    The lite adapter emits <project> at top level — we must wrap it."""
    out = tmp_path / "out.fcpxml"
    export_timeline(sample_timeline, out, fmt="fcpxml")
    tree = ET.parse(out)
    root = tree.getroot()
    lib = root.find("library")
    assert lib is not None, "missing <library> wrapper"
    evt = lib.find("event")
    assert evt is not None, "missing <event> inside <library>"
    prj = evt.find("project")
    assert prj is not None, "missing <project> inside <event>"
    assert root.find("project") is None, (
        "<project> must NOT be at the top level — Resolve rejects this"
    )


def test_fcpxml_asset_declares_has_audio(tmp_path: Path, sample_timeline):
    out = tmp_path / "out.fcpxml"
    export_timeline(sample_timeline, out, fmt="fcpxml")
    text = out.read_text()
    assert 'hasAudio="1"' in text
    assert 'hasAudio="0"' not in text


# ---- FCP7 XML --------------------------------------------------------------

def test_fcp7_xml_audio_clipitems_have_sourcetrack(tmp_path: Path, sample_timeline):
    """Without <sourcetrack mediatype=audio> on each audio clipitem, Resolve
    imports the audio track as silent."""
    out = tmp_path / "out.xml"
    export_timeline(sample_timeline, out, fmt="xml")
    tree = ET.parse(out)
    root = tree.getroot()
    audio_clips = root.findall(".//audio/track/clipitem")
    assert len(audio_clips) == 3
    for c in audio_clips:
        st = c.find("sourcetrack")
        assert st is not None, "audio clipitem missing <sourcetrack>"
        mt = st.find("mediatype")
        assert mt is not None and mt.text == "audio"


def test_fcp7_xml_video_clipitems_have_sourcetrack(tmp_path: Path, sample_timeline):
    out = tmp_path / "out.xml"
    export_timeline(sample_timeline, out, fmt="xml")
    tree = ET.parse(out)
    root = tree.getroot()
    video_clips = root.findall(".//video/track/clipitem")
    assert len(video_clips) == 3
    for c in video_clips:
        st = c.find("sourcetrack")
        assert st is not None and st.find("mediatype").text == "video"


def test_fcp7_xml_file_media_audio_has_characteristics(tmp_path: Path, sample_timeline):
    """The <file>'s <media><audio> needs samplerate + channelcount for Resolve
    to know how to handle the audio."""
    out = tmp_path / "out.xml"
    export_timeline(sample_timeline, out, fmt="xml")
    tree = ET.parse(out)
    root = tree.getroot()
    audio_media = root.find(".//file/media/audio")
    assert audio_media is not None
    sc = audio_media.find("samplecharacteristics")
    assert sc is not None
    assert sc.find("samplerate").text == "48000"
    cc = audio_media.find("channelcount")
    assert cc is not None and cc.text == "2"


def test_fcp7_xml_clip_count_matches_keeps(tmp_path: Path, sample_timeline):
    out = tmp_path / "out.xml"
    export_timeline(sample_timeline, out, fmt="xml")
    tree = ET.parse(out)
    root = tree.getroot()
    assert len(root.findall(".//video/track/clipitem")) == 3
    assert len(root.findall(".//audio/track/clipitem")) == 3
