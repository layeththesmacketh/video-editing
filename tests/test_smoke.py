"""End-to-end smoke: drive `lattimore.cli` exactly the way the MCP server does.

If this passes, the composer/exporter pipeline is wired correctly and the
adapter shims (FCPX / Premiere XML / EDL / OTIO) are installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


FIXTURE = Path(__file__).parent / "fixtures" / "smoke_schema.json"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lattimore.cli", *args],
        cwd=REPO_ROOT,
        env={"PYTHONPATH": str(REPO_ROOT / "lib"), **__import__("os").environ},
        capture_output=True,
        text=True,
        check=False,
    )


def test_fixture_is_valid_json():
    schema = json.loads(FIXTURE.read_text())
    assert {"aroll", "broll", "music"} <= set(schema)


def test_smoke_build_then_export(tmp_path: Path):
    otio_path = tmp_path / "smoke.otio"
    fcpxml_path = tmp_path / "smoke.fcpxml"

    build = _run("build", str(FIXTURE), str(otio_path), "--name", "smoke")
    assert build.returncode == 0, build.stderr
    payload = json.loads(build.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["runtime"] == pytest.approx(10.0)
    assert otio_path.exists()

    # The .otio is OTIO JSON — round-trippable.
    otio_data = json.loads(otio_path.read_text())
    assert otio_data["name"] == "smoke"
    track_names = [t["name"] for t in otio_data["tracks"]["children"]]
    assert track_names == ["V1_AROLL", "V2_BROLL", "A1_DIALOG", "A2_MUSIC"]

    export = _run("export", str(otio_path), str(fcpxml_path), "--fmt", "fcpxml")
    assert export.returncode == 0, export.stderr
    assert fcpxml_path.exists()

    fcp = fcpxml_path.read_text()
    # Real FCPXML — declared doctype, version, our clip references.
    assert fcp.startswith("<?xml")
    assert "<fcpxml" in fcp
    assert "<!DOCTYPE fcpxml>" in fcp
    assert "INT_001" in fcp
    assert "BR_walk" in fcp


def test_smoke_export_to_premiere_xml(tmp_path: Path):
    otio_path = tmp_path / "smoke.otio"
    xml_path = tmp_path / "smoke.xml"

    assert _run("build", str(FIXTURE), str(otio_path)).returncode == 0
    res = _run("export", str(otio_path), str(xml_path), "--fmt", "xml")
    assert res.returncode == 0, res.stderr
    text = xml_path.read_text()
    # FCP7-style XML (Premiere) starts with the xmeml doctype.
    assert "<xmeml" in text


def test_smoke_export_to_edl(tmp_path: Path):
    """EDL is single-video-track. Build → flatten → export."""
    import opentimelineio as otio

    from lattimore.timeline import build_timeline, export_timeline

    schema = json.loads(FIXTURE.read_text())
    tl = build_timeline(schema, name="smoke_edl")
    # Strip empty / non-V1 tracks the way operators are told to in the README.
    tl.tracks[:] = [tl.tracks[0]]  # V1 only

    edl_path = tmp_path / "smoke.edl"
    export_timeline(tl, edl_path)
    text = edl_path.read_text()
    assert text.startswith("TITLE:")
    assert "smoke_edl" in text
