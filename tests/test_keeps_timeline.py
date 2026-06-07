"""Tests for cuts_to_keeps inversion and build_keeps_timeline."""

from __future__ import annotations

import pytest

from lattimore.timeline import build_keeps_timeline, cuts_to_keeps


# --- cuts_to_keeps ---------------------------------------------------------

def test_no_cuts_keeps_whole_duration():
    assert cuts_to_keeps([], 60.0) == [{"start": 0.0, "end": 60.0}]


def test_single_cut_in_middle_yields_two_keeps():
    cuts = [{"start": 10, "end": 15}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [{"start": 0.0, "end": 10}, {"start": 15, "end": 60.0}]


def test_leading_cut_drops_lead_in():
    cuts = [{"start": 0, "end": 5}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [{"start": 5, "end": 60.0}]


def test_trailing_cut_drops_lead_out():
    cuts = [{"start": 55, "end": 60}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [{"start": 0.0, "end": 55}]


def test_multiple_cuts_yields_alternating_keeps():
    cuts = [{"start": 10, "end": 12}, {"start": 25, "end": 27}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [
        {"start": 0.0, "end": 10},
        {"start": 12, "end": 25},
        {"start": 27, "end": 60.0},
    ]


def test_overlapping_cuts_merge_correctly():
    cuts = [{"start": 10, "end": 20}, {"start": 15, "end": 25}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [{"start": 0.0, "end": 10}, {"start": 25, "end": 60.0}]


def test_cuts_at_clip_boundary_are_clamped():
    cuts = [{"start": -5, "end": 10}, {"start": 50, "end": 100}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [{"start": 10, "end": 50}]


def test_cuts_unsorted_input_works():
    cuts = [{"start": 40, "end": 45}, {"start": 10, "end": 15}]
    keeps = cuts_to_keeps(cuts, 60.0)
    assert keeps == [
        {"start": 0.0, "end": 10},
        {"start": 15, "end": 40},
        {"start": 45, "end": 60.0},
    ]


def test_zero_duration_returns_empty():
    assert cuts_to_keeps([], 0.0) == []


def test_min_keep_duration_drops_short_keeps():
    cuts = [{"start": 10, "end": 12}, {"start": 13, "end": 30}]
    # Without min_keep_duration: keeps = [0-10, 12-13, 30-60]
    # With min_keep_duration=2: middle 12-13 (1s) drops.
    keeps = cuts_to_keeps(cuts, 60.0, min_keep_duration=2.0)
    assert keeps == [{"start": 0.0, "end": 10}, {"start": 30, "end": 60.0}]


# --- build_keeps_timeline --------------------------------------------------

def test_keeps_timeline_has_v1_and_a1_tracks():
    keeps = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
    tl = build_keeps_timeline("/path/to/src.mov", 60.0, keeps)
    track_names = [t.name for t in tl.tracks]
    assert "V1" in track_names
    assert "A1" in track_names


def test_keeps_timeline_clip_count_matches_keeps():
    keeps = [{"start": 0, "end": 10}, {"start": 20, "end": 30}, {"start": 40, "end": 60}]
    tl = build_keeps_timeline("/path/to/src.mov", 60.0, keeps)
    v1 = next(t for t in tl.tracks if t.name == "V1")
    a1 = next(t for t in tl.tracks if t.name == "A1")
    assert len(list(v1)) == 3
    assert len(list(a1)) == 3


def test_keeps_timeline_metadata():
    keeps = [{"start": 0, "end": 10}, {"start": 20, "end": 30}]
    tl = build_keeps_timeline("/path/to/src.mov", 60.0, keeps, name="my_keeps")
    assert tl.name == "my_keeps"
    meta = tl.metadata["lattimore"]
    assert meta["kind"] == "keeps"
    assert meta["keep_count"] == 2
    assert meta["total_kept"] == 20.0
    assert meta["source_duration"] == 60.0


def test_keeps_timeline_rejects_negative_duration():
    with pytest.raises(ValueError, match="non-positive"):
        build_keeps_timeline("/x.mov", 60.0, [{"start": 10, "end": 10}])


def test_keeps_timeline_rejects_out_of_bounds():
    with pytest.raises(ValueError, match="outside source"):
        build_keeps_timeline("/x.mov", 60.0, [{"start": 50, "end": 70}])


def test_keeps_butted_with_no_gaps():
    """Each kept range should land butted against the previous one on the
    timeline — no gaps. Verify by checking that the V1 track's total
    duration equals the sum of the keeps."""
    keeps = [{"start": 0, "end": 10}, {"start": 20, "end": 30}, {"start": 50, "end": 55}]
    tl = build_keeps_timeline("/x.mov", 60.0, keeps)
    v1 = next(t for t in tl.tracks if t.name == "V1")
    total = sum((c.duration().to_seconds() for c in v1), 0.0)
    assert total == pytest.approx(10 + 10 + 5)
