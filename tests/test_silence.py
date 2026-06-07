"""Tests for silence.py cut planner — pure logic over a transcript."""

from __future__ import annotations

import pytest

from lattimore.silence import plan_silence_cuts


def transcript(word_spans: list[tuple[float, float]]) -> dict:
    """Build a minimal WhisperX-shaped transcript with one segment."""
    return {
        "segments": [
            {
                "start": word_spans[0][0] if word_spans else 0.0,
                "end": word_spans[-1][1] if word_spans else 0.0,
                "words": [{"word": "w", "start": s, "end": e} for s, e in word_spans],
            }
        ]
    }


def test_cuts_gap_between_words():
    t = transcript([(0, 1), (2, 3)])  # 1.0s gap
    plan = plan_silence_cuts(t, min_gap=0.4)
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 1
    assert plan["cuts"][0]["end"] == 2


def test_keeps_natural_breath():
    t = transcript([(0, 1), (1.2, 2)])  # 0.2s gap, below threshold
    plan = plan_silence_cuts(t, min_gap=0.4)
    assert plan["summary"]["cut_count"] == 0


def test_cuts_leading_silence():
    t = transcript([(2, 3), (4, 5)])  # 2s lead-in
    plan = plan_silence_cuts(t, min_gap=0.4, cut_leading=True)
    assert plan["summary"]["cut_count"] >= 1
    leading = next(c for c in plan["cuts"] if c["start"] == 0)
    assert leading["end"] == 2


def test_cut_leading_disabled():
    t = transcript([(2, 3), (4, 5)])
    plan = plan_silence_cuts(t, min_gap=0.4, cut_leading=False)
    starts = [c["start"] for c in plan["cuts"]]
    assert 0 not in starts


def test_cuts_trailing_silence():
    t = transcript([(0, 1), (2, 3)])
    plan = plan_silence_cuts(t, min_gap=0.4, cut_trailing=True, duration=10)
    trailing = next(c for c in plan["cuts"] if c["end"] == 10)
    assert trailing["start"] == 3


def test_trailing_needs_duration():
    """Without `duration`, trailing silence cannot be computed even with the flag."""
    t = transcript([(0, 1), (2, 3)])
    plan = plan_silence_cuts(t, min_gap=0.4, cut_trailing=True)
    starts = {c["start"] for c in plan["cuts"]}
    assert 3 not in starts


def test_padding_trims_inward():
    """Pad shrinks each cut inward so we don't clip the adjacent word."""
    t = transcript([(0, 1), (2, 3)])
    plan = plan_silence_cuts(t, min_gap=0.4, pad_start=0.05, pad_end=0.05,
                             cut_leading=False)
    c = plan["cuts"][0]
    assert c["start"] == pytest.approx(1.05)
    assert c["end"] == pytest.approx(1.95)


def test_merges_close_cuts():
    """Two gaps separated by a tiny word should merge with default merge_gap."""
    t = transcript([(0, 1), (2, 2.2), (3, 4)])  # gap1=[1,2], word=[2,2.2], gap2=[2.2,3]
    plan = plan_silence_cuts(t, min_gap=0.4, merge_gap=0.3, cut_leading=False)
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 1
    assert plan["cuts"][0]["end"] == 3


def test_min_cut_duration_drops_tiny_cuts():
    t = transcript([(0, 1), (1.42, 2)])  # 0.42s gap, just over min_gap
    plan = plan_silence_cuts(
        t, min_gap=0.4, pad_start=0.2, pad_end=0.2,
        min_cut_duration=0.1, cut_leading=False,
    )
    # After padding, the cut is 0.02s — should be dropped.
    assert plan["summary"]["cut_count"] == 0


def test_empty_transcript():
    plan = plan_silence_cuts({"segments": []}, min_gap=0.4, duration=10,
                             cut_leading=False, cut_trailing=False)
    assert plan["summary"]["cut_count"] == 0
    assert plan["summary"]["original_duration"] == 10


def test_multi_segment_transcript_flattens_words():
    t = {
        "segments": [
            {"start": 0, "end": 1, "words": [{"word": "a", "start": 0, "end": 1}]},
            {"start": 5, "end": 6, "words": [{"word": "b", "start": 5, "end": 6}]},
        ]
    }
    plan = plan_silence_cuts(t, min_gap=0.4, cut_leading=False)
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 1
    assert plan["cuts"][0]["end"] == 5


def test_summary_durations_balance():
    t = transcript([(0, 1), (2, 3)])
    plan = plan_silence_cuts(t, min_gap=0.4, duration=3, cut_leading=False,
                             cut_trailing=False)
    assert plan["summary"]["original_duration"] == 3
    assert plan["summary"]["cut_duration"] == 1
    assert plan["summary"]["kept_duration"] == 2


def test_handles_words_without_timestamps_gracefully():
    """Missing start/end on a word should be skipped, not crash."""
    t = {
        "segments": [
            {"words": [
                {"word": "a", "start": 0, "end": 1},
                {"word": "b"},  # missing timestamps
                {"word": "c", "start": 2, "end": 3},
            ]}
        ]
    }
    plan = plan_silence_cuts(t, min_gap=0.4, cut_leading=False)
    assert plan["summary"]["cut_count"] == 1
    assert plan["cuts"][0]["start"] == 1
