"""Tiny CLI used by the MCP server to build and export timelines.

Usage:
    python -m lattimore.cli build  <schema.json> <out.otio> [--name NAME]
    python -m lattimore.cli export <in.otio> <out.path> [--fmt fcpxml|xml|edl|otio]
    python -m lattimore.cli ingest <interview> <broll_dir> <out_dir>
                                   [--whisper-model small.en] [--vision-model ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import opentimelineio as otio

from .timeline import build_timeline, export_timeline


def _build(args: argparse.Namespace) -> int:
    schema = json.loads(Path(args.schema).read_text())
    tl = build_timeline(schema, name=args.name)
    out = Path(args.out)
    otio.adapters.write_to_file(tl, str(out), adapter_name="otio_json")
    print(json.dumps({"ok": True, "out": str(out), "runtime": tl.metadata["lattimore"]["total_runtime"]}))
    return 0


def _export(args: argparse.Namespace) -> int:
    tl = otio.adapters.read_from_file(args.src, adapter_name="otio_json")
    out = export_timeline(tl, args.out, fmt=args.fmt)
    print(json.dumps({"ok": True, "out": str(out)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lattimore.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("schema")
    b.add_argument("out")
    b.add_argument("--name", default="lattimore_roughcut")
    b.set_defaults(func=_build)

    e = sub.add_parser("export")
    e.add_argument("src")
    e.add_argument("out")
    e.add_argument("--fmt", default=None)
    e.set_defaults(func=_export)

    i = sub.add_parser("ingest")
    i.add_argument("interview")
    i.add_argument("broll_dir")
    i.add_argument("out_dir")
    i.add_argument("--whisper-model", default="small.en")
    i.add_argument("--vision-model", default=None)
    i.set_defaults(func=_ingest)

    args = ap.parse_args(argv)
    return args.func(args)


def _ingest(args: argparse.Namespace) -> int:
    from .ingest import ingest_library, DEFAULT_VISION_MODEL

    res = ingest_library(
        args.interview,
        args.broll_dir,
        args.out_dir,
        whisper_model=args.whisper_model,
        vision_model=args.vision_model or DEFAULT_VISION_MODEL,
        progress=lambda m: print(f"[ingest] {m}", file=sys.stderr),
    )
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
