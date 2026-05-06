# video-editing

Claude-driven video editing service for Nick Lattimore — an aggregator and editorial taste layer over [ButterCut](https://github.com/barefootford/buttercut), tuned for interview-led work (interview A-roll with B-roll lay-overs).

## What this is

This repo is **not** a video editor. It is:

1. A **taste layer** — skills under `.claude/skills/` that encode Lattimore's editorial sensibility (editorial-not-commercial, raw + premium, kinetic, reactions = HERO) and drive Claude through paper-edit, B-roll matching, hook scoring, and rough-cut orchestration.
2. An **aggregator MCP server** (`server/`) that wraps ButterCut's ingest skills (transcribe, analyze, summarize) plus our own composition tools (`compose_timeline`, `export_timeline`, `score_hooks`, `talent_dossier`).
3. A **multi-track timeline substrate** (`lib/lattimore/timeline.py`) built on [OpenTimelineIO](https://opentimeline.io/), exporting to FCPXML (Final Cut), XML (Premiere), CMX 3600 EDL, and OTIO JSON.

We do **not** ship a hand-rolled FCPXML emitter. We do **not** use ButterCut's roughcut skill or its FCPX writer. ButterCut is vendored solely for ingest.

## Workflow

```
RAW FOOTAGE ──► transcribe_video ──► analyze_video ──► summarize_video
                  (ButterCut)         (ButterCut)        (ButterCut)
                       │
                       ▼
                paper_edit_starter ◄── prompts/interview_cutdown.md
                       │                prompts/lattimore_taste.md
                       ▼
                broll_match_starter ◄── prompts/broll_matching.md
                       │
                       ▼
                compose_timeline ──► OTIO Timeline (V1 A-roll, V2 B-roll, A1 dialog, A2 music)
                       │
                       ▼
                export_timeline ──► .fcpxml / .xml / .edl / .otio
                       │
                       ▼
                Final Cut Pro / Premiere / Resolve  (human finishes)
```

The paper edit comes first (Claude proposes A-roll selects from the WhisperX transcript), then B-roll is layered on (Claude reads `prompts/broll_matching.md`, picks shots from the analyzed footage, and respects the lay-over rules below). Composition stitches the two passes into an OTIO timeline; export produces an editable project for Final Cut, Premiere, or Resolve.

## Multi-track schema

```python
{
  "aroll":  [{"clip": str, "in": float, "out": float}],
  "broll":  [{"clip": str, "in": float, "out": float,
              "over_aroll_at": float, "audio": bool}],
  "music":  [{"clip": str, "in": float, "duration": float}],
}
```

- **V1** — A-roll (interview)
- **V2** — B-roll lay-overs (`over_aroll_at` is a timeline-second on V1; `audio: false` is the default — natsound only when explicitly chosen)
- **A1** — interview dialog (sync-locked to V1)
- **A2** — music bed

## Editorial constraints (enforced by skills)

**Paper edit:**
- never cut mid-word — in/out come from word-level WhisperX timestamps
- total runtime within ±10% of target
- sequence for arc: `hook → premise → texture → turn → resolve` (`role` is one of these five)

**B-roll overlay:**
- never lay over hook lines or reactions
- ≤ 60% of runtime under B-roll
- ≥ 0.5s of bare A-roll between adjacent lay-overs
- lay-over duration ≤ underlying A-roll duration

## Skills

Top-level orchestrator: **`lattimore-roughcut`** — drives the full pipeline.

Mid-level (with `agent_prompt.md`):
- **`interview-paper-edit`** — picks A-roll selects from the transcript, sequences for arc.
- **`broll-overlay`** — chooses lay-overs, places them 1–3s after a line lands.

Reference-only (SKILL.md):
- **`hook-finder`** — Fear / Desire / Curiosity scoring (0–10 each).
- **`taste-research`** — talent dossier and reference reel building.
- **`im8-naming`** — IM8 filename convention.

## MCP server

Stdio MCP at `server/index.js`. Tools:

| Tool | Purpose |
|---|---|
| `create_library`, `list_libraries`, `library_status` | Library lifecycle |
| `transcribe_video`, `analyze_video`, `summarize_video` | ButterCut ingest |
| `paper_edit_starter`, `broll_match_starter` | Skill kickoff |
| `compose_timeline`, `export_timeline` | OTIO build + emit |
| `score_hooks`, `talent_dossier` | Editorial helpers |
| `job_status`, `job_result` | Async job polling |

Long-running ops (transcription, analysis) go through the in-memory job queue in `server/jobs.js`, which spawns child processes and streams stdout.

```bash
npm install
node server/index.js
```

## Submodules

```bash
git submodule update --init --recursive
```

- `vendor/buttercut` — ingest (transcribe, analyze, summarize) only.
- `vendor/cutlass` — Andrew Arrow's editorial reference / utilities.

## Python

```bash
pip install -e .
pytest
```

## Companion MCPs (recommended, independent installs)

These are **not** vendored. Install separately as needed:

- [**vfx-mcp**](https://github.com/) — visual effects helpers.
- [**davinci-resolve-mcp**](https://github.com/) — direct Resolve control for finishing.
- [**stockpile**](https://github.com/) — stock-footage search across providers.
- [**fast-whisper-mcp**](https://github.com/) — alternative WhisperX backend.

## License

MIT
