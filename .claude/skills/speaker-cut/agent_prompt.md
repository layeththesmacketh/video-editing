# speaker-cut — operating procedure

**Why this workflow.** Resolve's Python scripting API does not expose
SplitClip / blade / razor on a timeline. The only way to programmatically
trim a timeline to selected ranges is to delete the existing clip and
re-append the kept ranges, or to import a pre-built timeline from FCPXML.
We use the FCPXML-import path: it leaves the original timeline intact for
comparison and produces a clean new timeline you can finish from.

## Step 1 — Read the active project + V1 source

Use the davinci-resolve MCP (`media_pool` / `timeline` compound tools) to retrieve:

- The active project and its working directory (or pick a project work dir).
- The V1 clip on the active timeline.
- The V1 clip's source `MediaPoolItem` and the absolute file path of the source.
- The timeline frame rate (you'll need this for the FCPXML build).

If V1 has more than one clip, ask the editor which is the interview.

## Step 2 — Diarize

Call `lattimore.diarize_interview`:

```
{
  "video_path": "<absolute source path from Step 1>",
  "out_dir": "<project work dir>",
  "whisper_model": "small.en",
  // optional hints:
  "num_speakers": 2,
  "min_speakers": 2,
  "max_speakers": 5
}
```

Returns a `jobId`. Poll `job_status` / `job_result` for `diarized.json` and `speaker_report.json`.

Slow on first run — WhisperX downloads ~500MB. Tell the editor it'll take a few minutes for a 30-min interview on CPU.

## Step 3 — Identify speakers with the editor

Read `speaker_report.json`. For each speaker label, surface:

- The label (e.g. `SPEAKER_00`).
- Total seconds, share of speech, share of total runtime.
- 3 sample quotes (these make voice ID obvious).

Ask the editor which label(s) are the interviewee(s) to keep. **Do not assume.** Dominant talk time ≠ interviewee — some interviewers talk a lot.

## Step 4 — Plan the cuts

Call `lattimore.plan_speaker_cuts`:

```
{
  "diarized_path": "<from Step 2>",
  "keep": ["<labels from Step 3>"],
  "out_path": "<work_dir>/cuts.json"
  // merge_gap, pad_start (0.05 default), pad_end (0.05 default),
  // min_cut_duration — leave defaults unless asked
}
```

Defaults are sane. If the editor reports clipping after a test run, bump `pad_start` / `pad_end` to 0.1.

Surface the summary: original duration, cut duration, kept duration, cut count. If `cut_duration / original_duration > 50%`, double-check the kept-speaker assignment with the editor before proceeding.

## Step 5 — Build the kept-ranges FCPXML

Call `lattimore.build_cut_timeline`:

```
{
  "source_clip": "<source path from Step 1>",
  "cuts_path": "<from Step 4>",
  "out_path": "<work_dir>/<interview-name>_keeps.fcpxml",
  "rate": <timeline frame rate from Step 1>,
  "fmt": "fcpxml",
  "name": "<interview-name>_keeps",
  "min_keep_duration": 0.3
}
```

What this does: inverts the cuts to keeps (`cuts_to_keeps`), then builds an OTIO timeline where V1 + A1 are the source clip trimmed to each keep range, butted together with no gaps. `min_keep_duration` drops keep ranges shorter than 0.3s — those are usually noise leftover between two cuts.

Poll `job_status` / `job_result`. The result reports `keep_count` and `total_kept`. If `total_kept` is dramatically smaller than expected, stop and re-check with the editor.

## Step 6 — Import into Resolve

Call the davinci-resolve MCP's `media_pool` tool with action `ImportTimelineFromFile`, pointing at the FCPXML from Step 5:

```
media_pool({
  "action": "ImportTimelineFromFile",
  "filePath": "<absolute path to keeps.fcpxml>",
  "importOptions": {
    "timelineName": "<interview-name>_keeps",
    "importSourceClips": false,
    "sourceClipsPath": "<dir containing source clip>"
  }
})
```

Resolve creates a new timeline in the active project. The original timeline is untouched.

If `importSourceClips: false` produces a relink prompt, set `sourceClipsPath` to the directory that contains the source clip; Resolve will relink against the existing MediaPoolItem.

## Step 7 — Switch to the new timeline

Call the Resolve MCP's `project_manager` or `timeline` tool with action `SetCurrentTimeline` (or whatever the MCP names it for the active-timeline setter) to make the new timeline current, so the editor sees the result immediately.

## Step 8 — Report

Tell the editor:

- New timeline name (now active in Resolve).
- Number of keep ranges (= number of cuts in the new timeline minus 1).
- New runtime vs original.
- Paths to `diarized.json`, `cuts.json`, `keeps.fcpxml` (auditable, re-plannable).

## Failure modes

- **HF_TOKEN missing** → Step 2 fails. Point the editor at `docs/MCP_SETUP.md`.
- **Free Resolve, not Studio** → no scripting API. Stop and report; cannot proceed via MCP.
- **Diarization finds 1 speaker** → no second voice on the recording, or the interviewer is too quiet. Report.
- **Diarization finds many speakers** (5+) when 2 are expected → background voices, music, cross-talk. Re-run with `num_speakers: 2`.
- **`ImportTimelineFromFile` fails with relink errors** → the FCPXML references the source clip by path; if the path isn't accessible to Resolve (different volume, different mount point), pass the actual containing directory via `sourceClipsPath`.

## Re-planning without re-diarizing

Diarization is the slow step. To try different keep-speaker sets or cut parameters:

1. Re-call `plan_speaker_cuts` with the existing `diarized.json` (fast — no transcription).
2. Re-call `build_cut_timeline` on the new `cuts.json` to a new FCPXML name.
3. Re-import. Resolve will create another new timeline alongside the previous attempts.
