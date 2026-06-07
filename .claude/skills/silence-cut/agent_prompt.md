# silence-cut — operating procedure

## Step 1 — Read the active timeline

Call the davinci-resolve MCP for the active project + timeline + V1 clip path. If V1 has more than one clip, ask the editor which is the interview.

## Step 2 — Plan the cuts

Call `lattimore.plan_silence_cuts`:

```
{
  "source": "<absolute V1 clip path from Step 1>",
  "out_path": "<project work dir>/silence_cuts.json",
  "transcript_out": "<project work dir>/transcript.json",
  "whisper_model": "small.en",
  "min_gap": 0.4,           // gaps shorter than this are KEPT (natural breath)
  // pad_start, pad_end, merge_gap, min_cut_duration — leave defaults unless asked
}
```

Returns a `jobId`. Poll `job_status` until done; `job_result` gives the cut plan summary + the saved `silence_cuts.json` path.

This call transcribes if `source` is a video. On first run WhisperX downloads ~500MB of model — tell the editor.

## Step 3 — Review with the editor

Read `silence_cuts.json`. Report to the editor:

- Total cuts proposed.
- Cut duration vs original duration (`summary.cut_duration` / `summary.original_duration`).
- New runtime (`summary.kept_duration`).

If `cut_duration / original_duration` > 30%, pause and confirm. That much silence is unusual for a normal interview and may indicate the gap threshold is too tight or the transcript missed words.

## Step 4 — Taste pass (editorial gate)

Read `prompts/lattimore_taste.md`. Reactions and beats are HERO. Before applying, scan the proposed cuts for:

- **Long held silences immediately after a strong line.** If the transcript shows a punchy line ending right before a cut > 1s, that silence is probably doing work. Flag to the editor; default to NOT cutting it.
- **Cuts at the very start of the clip.** A short pre-roll often establishes presence. Confirm before cutting.
- **Cuts between obvious thought-units.** A pause between two complete sentences can be a beat; a pause mid-clause is just dead air.

Surface the protected ranges to the editor. They approve the final cut list.

## Step 5 — Apply cuts to Resolve

Sort cuts by `start` DESCENDING. For each cut:

1. `SplitClip` at `end` (later TC).
2. `SplitClip` at `start` (earlier TC).
3. Delete the segment between the two splits.

Reverse-TC order is mandatory — front-to-back deletion shifts every downstream cut.

Confirm with the editor before applying. Show: "About to make N cuts removing M.MM seconds total."

## Step 6 — Report

Tell the editor:

- Number of cuts applied.
- Total time removed.
- New runtime.
- Where `silence_cuts.json` and `transcript.json` are saved (auditable, re-plannable).

## Failure modes

- **WhisperX model download hangs** → first-run only; let it finish. ~500MB.
- **Transcript looks empty / cut_count is 0** → check audio actually has speech. The transcribe step may have failed silently if the input is music or unintelligible.
- **Free Resolve, not Studio** → no scripting API. Stop and report; fall back to the FCPXML export path.
- **Cuts feel too aggressive** → bump `min_gap` to 0.5 or 0.6 and re-plan from the same transcript (cheap; skip re-transcription by passing the `transcript.json` as `source` instead of the video).

## Re-planning without re-transcription

Once you have `transcript.json`, you can re-plan with different parameters cheaply:

```
plan_silence_cuts({
  "source": "<transcript.json from previous run>",
  "out_path": "<new_cuts.json>",
  "min_gap": 0.6   // looser pacing
})
```

This is the fast iteration loop when the editor wants to try different gap thresholds.
