---
name: silence-cut
description: Cut dead air (gaps between spoken words) from a single-speaker interview directly on a DaVinci Resolve timeline. Lighter than speaker-cut — no diarization, no HF_TOKEN. Use for one-person talking-head footage where you want to tighten pacing without altering takes.
---

# silence-cut

You are tightening a single-speaker interview by removing inter-word silences directly on the active Resolve timeline. No diarization, no FCPXML round-trip.

## When to use this vs speaker-cut

- **silence-cut** — one speaker on the recording (or you don't care which speaker is which). Removes inter-word gaps longer than the threshold.
- **speaker-cut** — multiple speakers on the recording, you want to keep only specific ones. Use that skill instead.

## Required reads

1. `prompts/lattimore_taste.md` — sensibility. Reactions are HERO. A held beat that's doing editorial work is NOT a silence to cut.
2. `agent_prompt.md` (this skill) — the operating procedure.

## Required MCPs

- `lattimore` — `plan_silence_cuts`, `job_status`, `job_result`.
- `davinci-resolve` — read timeline + V1 clip path, `SplitClip`, delete range.

## Inputs

- A DaVinci Resolve project open with the interview on V1 of the active timeline.
- (Optional) Hints from the editor: gap threshold (`min_gap`), tighten/loosen pacing.

## Output

The active Resolve timeline, tightened in place. No XML export.

## Hard constraints

- **Padding is ON by default** (0.05s inward on each cut). Do not disable unless the editor asks — it's what keeps adjacent words from getting clipped. Padding can always be trimmed back manually; clipping is destructive.
- **Apply cuts in reverse timeline order** so each remaining cut's TCs stay valid.
- **Review for editorial beats before applying.** A 1-second silence after a punchline is doing work; cutting it kills the line. If you see a gap right after a strong word that lands, flag it to the editor instead of auto-cutting.
- **Default `min_gap` is 0.4s.** Tighten to 0.3 for kinetic pacing; loosen to 0.6 if the speaker has a deliberate cadence.
- **Never `delete-from-pool` or `unlink` the master clip.** Operate only on the timeline instance.
