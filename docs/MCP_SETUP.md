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
- `HF_TOKEN` exported in your shell (needed for speaker diarization via pyannote — see below)

### HuggingFace token (one-time, for diarization)

Speaker diarization uses pyannote's models, which are gated behind HuggingFace terms acceptance.

1. Create a read token at <https://huggingface.co/settings/tokens>.
2. Accept the terms at <https://hf.co/pyannote/speaker-diarization-3.1>.
3. Accept the terms at <https://hf.co/pyannote/segmentation-3.0>.
4. Add to `~/.zshrc`:

   ```bash
   export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

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

## End-to-end: speaker-aware cut, no exports

This is the primary use case: an interview with multiple speakers (interviewer + one or more interviewees), and you want to keep only the interviewee(s) and silences while cutting out the interviewer's voice. The lattimore MCP exposes two tools for this:

| Tool | What it does |
|---|---|
| `diarize_interview` | Transcribes + speaker-diarizes a video with WhisperX + pyannote. Writes `diarized.json` (word-level transcript with speaker labels) and `speaker_report.json` (per-speaker stats + sample quotes). |
| `plan_speaker_cuts` | Takes a `diarized.json` plus a list of speaker labels to KEEP. Returns a cut plan — the timeline ranges to DELETE. Silences (no one talking) and the kept-speaker ranges are preserved. |

### The workflow

With the interview on V1 of an open Resolve timeline, paste into Claude Code:

> "Read the active Resolve timeline. Diarize the V1 clip via `lattimore.diarize_interview` into `./work/`. Show me `speaker_report.json` so I can identify each speaker. Then call `plan_speaker_cuts` with the speakers I tell you to keep. Apply each cut range to V1 in Resolve via the davinci-resolve MCP (`SplitClip` + delete the segment between cut points). Preserve all silences."

Under the hood:

1. **Resolve MCP** returns the V1 clip path from the active timeline.
2. **Lattimore MCP / `diarize_interview`** runs WhisperX (transcription + forced alignment) and pyannote (speaker ranges), assigns a speaker label to every word, and writes:
   - `diarized.json` — WhisperX-shaped, plus `speaker` on every word and a `diarization` list of speaker ranges.
   - `speaker_report.json` — per-speaker total talk time, share of speech, share of total, first/last appearance, 3 sample quotes per speaker.
3. **You pick** which speaker label(s) correspond to the interviewee(s) — the sample quotes make this obvious.
4. **Lattimore MCP / `plan_speaker_cuts`** computes the cut plan:
   - A range is cut iff *someone is talking* AND *no kept speaker is talking in that range*.
   - Silences are preserved (per the editorial constraint — held beats and reactions matter).
   - Adjacent cuts within `merge_gap` seconds are merged into one cut.
   - Cuts shorter than `min_cut_duration` are dropped (noise floor).
5. **Resolve MCP** applies each cut: `SplitClip` at the cut's start TC, `SplitClip` at the cut's end TC, then delete the middle segment.

No FCPXML round-trip. Everything stays in the active Resolve project.

### Tunables on `plan_speaker_cuts`

| Param | Default | What it does |
|---|---|---|
| `keep` | required | Speaker labels to KEEP (e.g. `["SPEAKER_00", "SPEAKER_02"]`). |
| `merge_gap` | 0.3 | Cuts separated by ≤ this many seconds merge into one. |
| `pad_start`, `pad_end` | 0.0 | Inward trim on each cut so the kept speaker's adjacent breath isn't clipped. Try 0.05 if you hear clipping. |
| `min_cut_duration` | 0.1 | Drop micro-cuts shorter than this — usually noise/mis-attribution. |

### CLI equivalents (useful for one-off runs without the MCP)

```bash
# 1. Diarize.
python -m lattimore.cli diarize ./interview.mov ./work/

# 2. Look at ./work/speaker_report.json, identify your speakers.

# 3. Plan the cut (e.g. keep only SPEAKER_00).
python -m lattimore.cli speaker-cut ./work/diarized.json \
    --keep SPEAKER_00 \
    --out ./work/cuts.json

# 4. ./work/cuts.json now contains the ranges to delete from the timeline.
```

## Bonus: pure silence removal (no diarization needed)

If your interview is a single speaker and you just want silences cut:

With the interview clip on V1 of an open Resolve timeline:

> "Read the active timeline from Resolve. Transcribe the V1 clip with `lattimore.transcribe_video`. From the word-level timestamps, find every gap > 0.4 seconds. Make blade cuts at each gap boundary on V1 and delete the gaps in place. Respect the Lattimore taste doc: do not cut reactions or beats that are doing editorial work — when in doubt, leave the gap."

This is the simpler path — no HF_TOKEN, no diarization, just gaps-between-words.

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
