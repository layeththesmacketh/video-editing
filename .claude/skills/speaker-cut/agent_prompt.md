# speaker-cut — operating procedure

## Step 1 — Read the active timeline

Call the davinci-resolve MCP to get the active project + timeline + the V1 clip path. If V1 has more than one clip, ask the editor which one is the interview (don't guess).

## Step 2 — Diarize

Call `lattimore.diarize_interview`:

```
{
  "video_path": "<absolute path from Step 1>",
  "out_dir": "<project work dir, e.g. ./work>",
  "whisper_model": "small.en",
  // optional hints from the editor:
  "num_speakers": 2,        // if known
  "min_speakers": 2,
  "max_speakers": 5
}
```

This returns a `jobId`. Poll `job_status` until done, then `job_result` for the paths to `diarized.json` and `speaker_report.json`.

This step is slow on first run (WhisperX downloads ~500MB models). Tell the editor it'll take several minutes for a 30-minute interview on CPU.

## Step 3 — Identify speakers with the editor

Read `speaker_report.json`. For each speaker label, surface to the editor:

- The label (e.g. `SPEAKER_00`).
- Total seconds, share of speech, share of total runtime.
- 3 sample quotes (these make voice ID obvious).

Ask the editor which label(s) are the interviewee(s) to keep. **Do not assume.** Even when one speaker dominates by talk time, the dominant speaker isn't always the interviewee — some interviewers talk a lot.

## Step 4 — Plan the cuts

Call `lattimore.plan_speaker_cuts`:

```
{
  "diarized_path": "<from Step 2>",
  "keep": ["<labels from Step 3>"],
  "merge_gap": 0.3,
  "pad_start": 0.05,
  "pad_end": 0.05,
  "min_cut_duration": 0.1,
  "out_path": "<work_dir>/cuts.json"
}
```

The defaults are sane for a typical interview. If the editor reports clipping (kept speaker's first/last word getting trimmed) after a test run, bump `pad_start` / `pad_end` to 0.1.

Surface the summary to the editor before applying: original duration, cut duration, kept duration, cut count. If `cut_duration` is over 50% of `original_duration`, double-check with the editor before applying — that's a sign the kept speaker assignment may be wrong.

## Step 5 — Apply cuts to Resolve

Read `cuts.json` — it's a list of `{start, end, speakers}` ranges.

**Sort cuts by `start` DESCENDING.** Apply each cut in reverse timeline order:

1. `SplitClip` at `end` (the cut's later TC).
2. `SplitClip` at `start` (the cut's earlier TC).
3. Delete the middle segment between the two splits.

This ordering keeps every remaining cut's TCs valid. Front-to-back ordering shifts everything downstream after each delete and the cuts drift.

Confirm with the editor before applying — show them how many splits/deletes you're about to make.

## Step 6 — Report

Tell the editor:

- How many ranges were cut.
- New runtime of the timeline.
- Where `cuts.json` and `diarized.json` are saved (so they can audit, or re-plan with different parameters).

## Failure modes

- **HF_TOKEN missing** → Step 2 will fail. Stop and ask the editor to set it; point them at `docs/MCP_SETUP.md`.
- **Free Resolve, not Studio** → Step 5 will fail (no scripting API). Stop and report — they'll need to upgrade to Studio or fall back to the FCPXML export path.
- **Diarization finds 1 speaker** → there isn't actually anyone else on the recording, or the interviewer is whispering/very quiet. Report and ask the editor what to do.
- **Diarization finds many speakers** (5+) when only 2 are expected → background voices, music with vocals, or cross-talk. Re-run with `num_speakers: 2` (or whatever the editor specifies) to force the model to find exactly that many.
