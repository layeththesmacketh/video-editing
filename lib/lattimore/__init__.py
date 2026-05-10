"""Lattimore editorial composition library.

Multi-track timeline build (V1 A-roll, V2 B-roll, A1 dialog, A2 music) on top of
OpenTimelineIO, plus paper-edit and B-roll-matching helpers.
"""

from .timeline import (
    build_timeline,
    build_cutdown_timeline,
    export_timeline,
    parse_timecode,
    timecode,
)
from .paper_edit import filter_candidates, validate_paper_edit, ROLES
from .broll_matcher import find_footage_url, validate_broll, place_broll

__all__ = [
    "build_timeline",
    "build_cutdown_timeline",
    "export_timeline",
    "parse_timecode",
    "timecode",
    "filter_candidates",
    "validate_paper_edit",
    "ROLES",
    "find_footage_url",
    "validate_broll",
    "place_broll",
]
