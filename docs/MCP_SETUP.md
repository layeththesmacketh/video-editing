# MCP setup — staying inside DaVinci Resolve

This repo's pipeline runs through two MCP servers that Claude Code talks to:

| MCP | What it does |
|---|---|
| `lattimore` | This repo's own server (`server/index.js`). Transcribe / diarize / paper-edit / compose OTIO / export FCPXML. |
| `davinci-resolve` | Direct control of DaVinci Resolve Studio — read timeline state, delete clips, append to timeline, import FCPXML, manage projects/media pool. |

Together they let Claude transcribe an interview, decide what to cut, and **produce a new tightened timeline inside the same Resolve project** by building an FCPXML of just the kept ranges and importing it via the Resolve MCP. The original timeline is left intact for comparison.

### A note on the workflow

Resolve's Python scripting API **does not support splitting / blading a clip on the timeline at an arbitrary timecode**. There is no `SplitClip` method. The documented workaround (used here) is:

1. Build a new timeline composed of the kept source ranges butted together.
2. Import that timeline via `MediaPool.ImportTimelineFromFile`.

This stays inside Resolve — you never leave the active project to use an external NLE — but it does generate an FCPXML in your work dir as the transport. If you want absolute purity (no XML artifact on disk), the alternative is `DeleteClips` + `AppendToTimeline` per keep range, which mutates the existing timeline in place. The current skills use the FCPXML-import path because it's non-destructive and the FCPXML is auditable.

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

## End-to-end: speaker-aware cut

This is the primary use case: an interview with multiple speakers (interviewer + one or more interviewees), and you want to keep only the interviewee(s) and silences while cutting out the interviewer's voice. The lattimore MCP exposes three tools that compose into the workflow:

| Tool | What it does |
|---|---|
| `diarize_interview` | Transcribes + speaker-diarizes a video with WhisperX + pyannote. Writes `diarized.json` and `speaker_report.json`. |
| `plan_speaker_cuts` | Takes a `diarized.json` plus speaker labels to KEEP. Returns the cut plan (ranges to DELETE). |
| `build_cut_timeline` | Takes a cuts plan + the source clip. Inverts the cuts to keeps and writes an FCPXML / XML / EDL / OTIO of the kept ranges butted together. Import into Resolve. |

### The workflow

With the interview on V1 of an open Resolve timeline, paste into Claude Code:

> "Run the `speaker-cut` skill on the V1 clip in the active Resolve timeline."

Under the hood:

1. **Resolve MCP** returns the V1 clip's absolute source path + timeline frame rate.
2. **Lattimore MCP / `diarize_interview`** runs WhisperX + pyannote and writes:
   - `diarized.json` — WhisperX-shaped transcript with per-word speaker labels + a `diarization` list of speaker ranges.
   - `speaker_report.json` — per-speaker total talk time, share of speech, first/last appearance, 3 sample quotes per speaker.
3. **You pick** which speaker label(s) are the interviewee(s) — the sample quotes make this obvious.
4. **Lattimore MCP / `plan_speaker_cuts`** computes the cut plan:
   - A range is cut iff *someone is talking* AND *no kept speaker is talking in that range*.
   - Silences are preserved (held beats and reactions matter).
   - Default padding (0.05s inward on each cut) protects the kept speaker's adjacent words from clipping.
5. **Lattimore MCP / `build_cut_timeline`** inverts the cuts to keeps and writes an FCPXML where V1+A1 are the kept ranges butted together.
6. **Resolve MCP / `media_pool` action `ImportTimelineFromFile`** imports the FCPXML as a new timeline in the active project. The original timeline is preserved alongside.

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

## Single-speaker case: silence removal (no diarization, no HF_TOKEN)

If your interview is one speaker and you just want dead air tightened, use the lighter `silence-cut` skill / `plan_silence_cuts` MCP tool.

With the interview on V1 of an open Resolve timeline, in Claude Code:

> "Run the `silence-cut` skill on the V1 clip in the active Resolve timeline."

The MCP tool:

| Tool | What it does |
|---|---|
| `plan_silence_cuts` | Takes a video (transcribes it) or an existing transcript.json. Finds gaps between words longer than `min_gap` (default 0.4s). Emits the same `cuts: [{start, end, reason}]` shape as `plan_speaker_cuts`. |

The workflow is identical to speaker-cut: plan cuts → `build_cut_timeline` to FCPXML → `media_pool.ImportTimelineFromFile` to bring it back as a new timeline.

### Padding is on by default

Both `plan_speaker_cuts` and `plan_silence_cuts` apply `pad_start = pad_end = 0.05` by default — each cut is trimmed 0.05s inward on both ends so the kept speaker's adjacent words don't get clipped. Padding can always be trimmed back manually in Resolve; clipping is destructive, so we default to the conservative side.

Disable with `pad_start=0`, `pad_end=0` if you want raw boundaries.

### Tunables on `plan_silence_cuts`

| Param | Default | What it does |
|---|---|---|
| `source` | required | Video path OR transcript.json. If video, transcribes via WhisperX first. |
| `min_gap` | 0.4 | Gaps shorter than this are KEPT (natural breath). Tighten to 0.3 for kinetic pacing; loosen to 0.6 for deliberate cadence. |
| `merge_gap` | 0.3 | Cuts within this distance merge into one. |
| `pad_start`, `pad_end` | 0.05 | Inward trim on each cut. |
| `cut_leading` | true | Cut silence before the first word. |
| `cut_trailing` | true | Cut silence after the last word. |
| `min_cut_duration` | 0.1 | Drop cuts shorter than this after padding/merging. |

### Fast re-planning without re-transcription

The transcribe step is the slow part. Pass a `transcript_out` path on the first call, then for subsequent runs use that transcript as `source`:

```python
# First run — transcribes (slow).
plan_silence_cuts({
  "source": "./interview.mov",
  "transcript_out": "./work/transcript.json",
  "out_path": "./work/cuts_v1.json",
  "min_gap": 0.4
})

# Re-plan with looser pacing — instant, reuses the transcript.
plan_silence_cuts({
  "source": "./work/transcript.json",
  "out_path": "./work/cuts_v2.json",
  "min_gap": 0.6
})
```

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
