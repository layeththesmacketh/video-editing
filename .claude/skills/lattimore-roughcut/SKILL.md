---
name: lattimore-roughcut
description: Top-level orchestrator for a Lattimore interview rough cut. Use when the user wants a full pass from raw footage to an editable timeline (FCPXML / Premiere XML / EDL). Drives ingest → paper edit → B-roll overlay → compose → export.
---

# lattimore-roughcut

You are the orchestrator for a full Lattimore rough cut. Before anything else, **read `prompts/lattimore_taste.md`**. That is the editorial brain. Re-read it any time you're uncertain.

## When to use

The user has an interview library and wants a rough cut suitable for hand-off to Final Cut, Premiere, or Resolve. They will not be using ButterCut's roughcut skill — we replace it.

## Pipeline

1. **Confirm the brief.** Target runtime. Angle. Any must-includes. Client (if `im8`, the IM8 filename convention applies — invoke skill `im8-naming` at export time).
2. **Ingest** (only if not already done):
   - `transcribe_video` on each interview clip (async — poll `job_status`).
   - `analyze_video` and `summarize_video` on each B-roll clip.
3. **Paper edit.** Invoke skill `interview-paper-edit` with the transcripts and target runtime. Do not skip the taste doc read.
4. **Hook check.** Pass the paper-edit's `hook` and any alternate hook candidates through `score_hooks`. If the dominant hook is weak (total < 18), surface alternatives before continuing.
5. **B-roll overlay.** Invoke skill `broll-overlay` with the paper edit and the footage map. Validate the four hard rules (never over hook/reaction, ≤ 60% coverage, ≥ 0.5s gaps, lay-over ≤ underlying).
6. **Compose.** Call `compose_timeline` with the multi-track schema:
   ```
   {"aroll": [...], "broll": [...], "music": [...]}
   ```
7. **Export.** `export_timeline` to `.fcpxml` (default) and `.otio` (always, for round-trip). Add `.xml` (Premiere) or `.edl` if the user asked.
8. **Hand-off note.** Summarize: total runtime, B-roll coverage %, hook score, files written, and any taste flags ("dwell on the resolve a beat longer in finishing", etc).

## What you do NOT do

- Do not invoke ButterCut's `roughcut` skill.
- Do not write FCPXML by hand. Always go through OTIO.
- Do not skip the pre-flight checklist in `lattimore_taste.md`.
- Do not move forward if the hook is weak — flag it.

## When to defer to humans

- If the talent's best material clusters in one block and the arc won't sequence cleanly, say so. Don't fake an arc.
- If the footage map can't cover the spine without breaking the ≤ 60% rule, return a partial cut and a coverage gap report rather than padding.
