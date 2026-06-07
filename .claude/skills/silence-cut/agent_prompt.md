# silence-cut — operating procedure

**Why this workflow.** Resolve's Python scripting API does not expose
SplitClip / blade / razor on a timeline. We build an FCPXML of just the
kept ranges and import it as a new timeline in the active project — the
original timeline is preserved for comparison.

## Step 1 — Read the active project + V1 source

Use the davinci-resolve MCP to get:

- The active project + a working directory.
- The V1 clip on the active timeline and the absolute source file path.
- The timeline frame rate.

If V1 has more than one clip, ask which is the interview.

## Step 2 — Plan the cuts

Call `lattimore.plan_silence_cuts`:

```
{
  "source": "<absolute V1 clip path from Step 1>",
  "out_path": "<work_dir>/silence_cuts.json",
  "transcript_out": "<work_dir>/transcript.json",
  "whisper_model": "small.en",
  "min_gap": 0.4
  // pad_start/pad_end default to 0.05 — keep defaults unless editor asks
}
```

Poll `job_status` / `job_result`. The first run transcribes (slow — WhisperX downloads ~500MB on first use). Subsequent runs that pass the cached `transcript.json` as `source` are instant.

## Step 3 — Review with the editor

Read `silence_cuts.json`. Report:

- Total cuts proposed.
- Cut duration vs original duration.
- New runtime (`summary.kept_duration`).

If `cut_duration / original_duration > 30%`, pause and confirm — that much silence is unusual.

## Step 4 — Taste pass (editorial gate)

Read `prompts/lattimore_taste.md`. Before building the FCPXML, scan the cuts for:

- **Long held silences after a strong line.** A punchy ending followed by >1s of dead air is doing editorial work. Default to NOT cutting.
- **Cuts at the very start.** A brief pre-roll establishes presence. Confirm.
- **Cuts mid-thought.** A pause between clauses is just dead air; a pause between two complete thoughts can be a beat.

If you flag any cuts as protected, re-call `plan_silence_cuts` with a higher `min_gap` (e.g. 0.6) or edit the `cuts.json` manually before Step 5.

## Step 5 — Build the kept-ranges FCPXML

Call `lattimore.build_cut_timeline`:

```
{
  "source_clip": "<source path from Step 1>",
  "cuts_path": "<silence_cuts.json from Step 2>",
  "out_path": "<work_dir>/<interview-name>_tightened.fcpxml",
  "rate": <timeline frame rate>,
  "fmt": "fcpxml",
  "name": "<interview-name>_tightened",
  "min_keep_duration": 0.2
}
```

Inverts the cuts to keeps and builds an OTIO timeline of V1 + A1 with the kept ranges butted together. Poll `job_status` / `job_result` for confirmation.

## Step 6 — Import into Resolve

Call the davinci-resolve MCP's `media_pool` tool with action `ImportTimelineFromFile`:

```
media_pool({
  "action": "ImportTimelineFromFile",
  "filePath": "<absolute path to tightened.fcpxml>",
  "importOptions": {
    "timelineName": "<interview-name>_tightened",
    "importSourceClips": false,
    "sourceClipsPath": "<dir containing source clip>"
  }
})
```

A new timeline appears in the active project. The original is untouched.

## Step 7 — Switch to the new timeline

Call the Resolve MCP to set the new timeline as current so the editor sees it.

## Step 8 — Report

Tell the editor:

- New timeline name (active in Resolve).
- Number of cuts in the new timeline (= keep ranges - 1).
- New runtime vs original.
- Paths to `transcript.json`, `silence_cuts.json`, `tightened.fcpxml`.

## Failure modes

- **Free Resolve** → no scripting API. Cannot proceed.
- **WhisperX model download hangs** → first run only; let it finish.
- **Transcript empty / cut_count is 0** → input may be music or unintelligible. Check audio.
- **ImportTimelineFromFile relink errors** → set `sourceClipsPath` to the actual source directory.

## Re-planning without re-transcribing

Once you have `transcript.json`, re-plan with new parameters cheaply:

```
plan_silence_cuts({
  "source": "<transcript.json>",  // not the video
  "out_path": "<new_cuts.json>",
  "min_gap": 0.6
})
```

Then re-run `build_cut_timeline` to a new FCPXML name and re-import. Each iteration creates a new timeline in Resolve so you can A/B them.
