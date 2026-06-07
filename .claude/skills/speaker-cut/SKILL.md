---
name: speaker-cut
description: Diarize an interview and cut every range where a non-kept speaker is talking, directly on a DaVinci Resolve timeline. Silences and kept-speaker ranges are preserved. Use when the editor wants to keep only the interviewee(s) and remove the interviewer's voice from an interview clip.
---

# speaker-cut

You are removing non-main-speaker audio from an interview by driving Resolve directly via the davinci-resolve MCP. The user keeps the interviewee(s); you cut the interviewer.

## Required reads

1. `prompts/lattimore_taste.md` — editorial sensibility. Reactions are HERO; don't ever cut a beat that's doing work.
2. `agent_prompt.md` (this skill) — the operating procedure.

## Required MCPs

- `lattimore` — `diarize_interview`, `plan_speaker_cuts`, `job_status`, `job_result`.
- `davinci-resolve` — read timeline + clip paths, `SplitClip`, delete range.

## Inputs

- A DaVinci Resolve project open with the interview on V1 of the active timeline.
- (Optional) Hints from the editor: expected speaker count, who the interviewee is by voice (name, gender, age cue), or a fixed `--num-speakers`.

## Output

The active Resolve timeline, with all non-kept-speaker ranges removed in place. No FCPXML round-trip.

## Hard constraints

- **Silences are preserved.** A held beat after a line lands is editorial. Never cut a silence.
- **Always confirm speaker identity with the editor before applying cuts.** The diarization labels speakers as `SPEAKER_00`, `SPEAKER_01` etc. — they're arbitrary. Show the editor the `speaker_report.json` (per-speaker stats + sample quotes) and ask which label(s) to keep.
- **Apply cuts atomically, in reverse timeline order.** Splitting from the back means earlier cut TCs stay valid as you go. If you cut front-to-back, every split shifts everything downstream.
- **Never `delete-from-pool` or `unlink` the master clip.** Operate only on the timeline instance.
