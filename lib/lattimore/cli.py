"""Tiny CLI used by the MCP server to build and export timelines.

Usage:
    python -m lattimore.cli build  <schema.json> <out.otio> [--name NAME]
    python -m lattimore.cli export <in.otio> <out.path> [--fmt fcpxml|xml|edl|otio]
    python -m lattimore.cli ingest <interview> <broll_dir> <out_dir>
                                   [--whisper-model small.en] [--vision-model ...]
    python -m lattimore.cli cutdown <interview> <out_dir>
                                   [--speakers andrei,tawny] [--target-min 15] [--target-max 120]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import opentimelineio as otio

from .timeline import build_cutdown_timeline, build_timeline, export_timeline


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

    c = sub.add_parser("cutdown",
                       help="transcribe + find soundbites + emit FCPXML "
                            "(V1=full master, V2=soundbites lifted)")
    c.add_argument("interview")
    c.add_argument("out_dir")
    c.add_argument("--whisper-model", default="small.en")
    c.add_argument("--soundbite-model", default=None,
                   help="Anthropic model id (default: claude-sonnet-4-6)")
    c.add_argument("--speakers", default="andrei,tawny",
                   help="comma-separated speaker labels for the splitter to use")
    c.add_argument("--target-min", type=float, default=15.0)
    c.add_argument("--target-max", type=float, default=120.0)
    c.set_defaults(func=_cutdown)

    args = ap.parse_args(argv)
    return args.func(args)


def _cutdown(args: argparse.Namespace) -> int:
    """Single-command workflow: interview .mov → FCPXML with soundbites lifted to V2.

    Steps:
      1. Transcribe with whisperx (word-level timestamps).
      2. Send transcript to Claude; get soundbite ranges.
      3. Validate (word boundaries, duration, no overlaps).
      4. Build a cutdown OTIO timeline (V1+A1 = full, V2+A2 = soundbites).
      5. Export FCPXML + OTIO.
    """
    from .ingest import transcribe_interview
    from .soundbites import find_soundbites, validate_soundbites, DEFAULT_MODEL

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    interview = Path(args.interview).resolve()
    if not interview.exists():
        print(json.dumps({"ok": False, "error": f"file not found: {interview}"}))
        return 2

    print(f"[cutdown] transcribing {interview.name} (this is the slow step) ...",
          file=sys.stderr)
    transcript = transcribe_interview(interview, model=args.whisper_model)
    transcript_path = out_dir / "transcript.json"
    transcript_path.write_text(json.dumps(transcript, indent=2))

    duration = max(
        (float(s["end"]) for s in transcript.get("segments", [])),
        default=0.0,
    )
    if duration <= 0:
        print(json.dumps({"ok": False, "error": "transcript empty — no speech detected"}))
        return 3

    speakers = [s.strip().lower() for s in args.speakers.split(",") if s.strip()]
    print(f"[cutdown] finding soundbites (speakers={speakers}, model={args.soundbite_model or DEFAULT_MODEL}) ...",
          file=sys.stderr)
    soundbites = find_soundbites(
        transcript,
        speakers=speakers,
        target_min=args.target_min,
        target_max=args.target_max,
        model=args.soundbite_model or DEFAULT_MODEL,
    )
    soundbites_path = out_dir / "soundbites.json"
    soundbites_path.write_text(json.dumps(soundbites, indent=2))

    val = validate_soundbites(soundbites, transcript,
                              min_dur=args.target_min, max_dur=args.target_max)
    if not val["ok"]:
        print(f"[cutdown] WARNING — validator flagged issues:", file=sys.stderr)
        for e in val["errors"]:
            print(f"           {e}", file=sys.stderr)
        print("[cutdown] (proceeding anyway — open the FCPXML and QC visually)",
              file=sys.stderr)

    print(f"[cutdown] building timeline ({len(soundbites)} soundbites) ...",
          file=sys.stderr)
    tl = build_cutdown_timeline(interview, duration, soundbites, name=interview.stem)
    otio_path = out_dir / f"{interview.stem}_cutdown.otio"
    fcpxml_path = out_dir / f"{interview.stem}_cutdown.fcpxml"
    otio.adapters.write_to_file(tl, str(otio_path), adapter_name="otio_json")
    export_timeline(tl, fcpxml_path, fmt="fcpxml")

    summary = {
        "ok": True,
        "interview": str(interview),
        "duration": duration,
        "soundbite_count": len(soundbites),
        "validator": val,
        "transcript": str(transcript_path),
        "soundbites": str(soundbites_path),
        "otio": str(otio_path),
        "fcpxml": str(fcpxml_path),
    }
    print(json.dumps(summary, indent=2))
    return 0


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
