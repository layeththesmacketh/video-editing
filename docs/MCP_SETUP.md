# MCP setup — staying inside DaVinci Resolve

This repo's pipeline runs through two MCP servers that Claude Code talks to:

| MCP | What it does |
|---|---|
| `lattimore` | This repo's own server (`server/index.js`). Transcribe / analyze / paper-edit / compose OTIO / export. Wraps ButterCut for ingest. |
| `davinci-resolve` | Direct control of DaVinci Resolve Studio — read timeline state, make blade cuts, delete ranges, move clips, add markers. |

With both wired up, Claude can transcribe an interview, decide what to cut, and apply those cuts on the Resolve timeline **without exporting an XML round-trip**.

## Requirements

- macOS on Apple Silicon (ButterCut requirement)
- **DaVinci Resolve Studio** — the free edition has no scripting API, so the Resolve MCP cannot connect to it.
- Homebrew, Node ≥ 20, Python ≥ 3.10, ffmpeg, Claude Code CLI
- `ANTHROPIC_API_KEY` exported in your shell (needed for ButterCut's vision-analysis on B-roll)

## Resolve Studio prep (one-time)

1. Open Resolve Studio.
2. Preferences → General → **External scripting using** = **Local**.
3. Leave Resolve open during install — the resolve-mcp installer probes the running Resolve.

## One-shot install

```bash
bash scripts/install-macos.sh
```

The script:

1. Verifies prereqs.
2. `git submodule update --init --recursive` — pulls ButterCut + cutlass.
3. `npm install` — Node deps for the lattimore MCP.
4. `pip install -e '.[dev,ingest]'` — lattimore package + WhisperX + Anthropic SDK.
5. `npx davinci-resolve-mcp setup` — installs the Resolve MCP and registers it with Claude Code automatically.
6. `claude mcp add lattimore --scope user -- node <repo>/server/index.js`.

## Verify

```bash
claude mcp list
```

Expected:

```
davinci-resolve   <command>   ✓
lattimore         node ...    ✓
```

Then in Claude Code, with an interview open in Resolve:

> "Read the active timeline from Resolve and tell me how many clips are on V1."

If Claude responds with a real number, both MCPs are talking.

## End-to-end: remove silences without exporting

With the interview clip on V1 of an open Resolve timeline, paste into Claude Code:

> "Read the active timeline from Resolve. Transcribe the V1 clip with `lattimore.transcribe_video`. From the word-level timestamps, find every gap > 0.4 seconds. Make blade cuts at each gap boundary on V1 and delete the gaps in place. Respect the Lattimore taste doc: do not cut reactions or beats that are doing editorial work — when in doubt, leave the gap."

What happens under the hood:

1. Resolve MCP returns the active timeline + V1 clip path.
2. Lattimore MCP runs WhisperX → returns word-level timestamps.
3. Claude identifies gaps using a configurable threshold (0.4s is a starting point — tighten for a more kinetic feel, loosen to preserve breath).
4. Claude reads `prompts/lattimore_taste.md` and the `interview-paper-edit` skill to flag protected ranges (hooks, reactions, beats).
5. Claude calls the Resolve MCP's `SplitClip` + `DeleteClips` (or equivalent range-delete) for each non-protected gap.

No FCPXML, no XML, no Recut, no buttercut.io round-trip. Everything stays in the active Resolve project.

## Alternative: use Resolve's native transcription

Resolve Studio ≥ 18.5 has built-in Speech-to-Text. If you'd rather skip the WhisperX install:

1. Right-click the interview clip in the media pool → **Audio Transcription**.
2. Edit menu → **Text-based Editing**.
3. Select silent/non-talking spans in the transcript and delete.

That's the manual version — no MCPs needed — but it loses the taste-layer step (everything cuts on silence threshold, no awareness of hooks/reactions). The MCP path uses the same data with editorial protection on top.

## Troubleshooting

**`claude mcp list` doesn't show davinci-resolve** — re-run `npx davinci-resolve-mcp setup`. The installer prints which client configs it touched.

**Resolve MCP errors with "scripting not enabled"** — Preferences → General → External scripting using = Local. Restart Resolve after toggling.

**WhisperX install hangs on first run** — it's downloading the model (~500 MB for `small.en`). Let it finish.

**`pip install` fails on `torch`** — WhisperX pulls a heavy torch dependency. On Apple Silicon, `pip install torch torchaudio` first, then re-run.

**ButterCut step errors with "Apple Silicon required"** — confirmed; ButterCut is M-series only. If you're on Intel, transcription still works (via WhisperX directly through `lattimore.cli`), but the ButterCut `analyze_video`/`summarize_video` paths will fail.
