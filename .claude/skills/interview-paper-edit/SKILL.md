---
name: interview-paper-edit
description: Pick A-roll selects from a WhisperX interview transcript and sequence them for arc (hook → premise → texture → turn → resolve). Use when you have transcripts and a target runtime and need an editable A-roll spine.
---

# interview-paper-edit

You are picking the A-roll spine for a Lattimore cut.

## Required reads

1. `prompts/lattimore_taste.md` — sensibility.
2. `prompts/interview_cutdown.md` — the operating prompt.
3. `agent_prompt.md` (this skill) — the working procedure.

Then proceed.

## Inputs

- WhisperX transcript(s) with word-level timestamps.
- Target runtime in seconds.
- Brief.

## Output

A JSON array of A-roll selects per the schema in `prompts/interview_cutdown.md`. Hand it to `compose_timeline` (or to `broll-overlay` first if a B-roll pass is wanted).

## Hard constraints (enforced)

- Never cut mid-word. In/out come from the WhisperX `words` array.
- Total runtime within ±10% of target.
- `role` is one of `hook | premise | texture | turn | resolve`.
- Selects are ordered by intended timeline position, not transcript position.

## Failure modes

- If the material doesn't support all five roles, omit the missing one and flag it.
- If two selects cover the same idea, drop the weaker delivery.
- If the target runtime can't be hit without cutting hook or resolve, return short and explain.
