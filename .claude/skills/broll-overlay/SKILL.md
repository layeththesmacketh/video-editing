---
name: broll-overlay
description: Place B-roll lay-overs on a paper-edited A-roll spine, respecting Lattimore's lay-over rules (never over hook/reaction, ≤60% coverage, ≥0.5s gaps, 1–3s after the line lands). Use after interview-paper-edit and before compose_timeline.
---

# broll-overlay

You are placing lay-overs over an existing A-roll spine.

## Required reads

1. `prompts/lattimore_taste.md`
2. `prompts/broll_matching.md`
3. `agent_prompt.md` in this skill

## Inputs

- The paper edit (A-roll select array from `interview-paper-edit`).
- A footage map of analyzed B-roll (clip → summary / shot list).
- Optional: music bed for tempo reference.

## Output

A JSON array of lay-over entries per the schema in `prompts/broll_matching.md`. Pass to `compose_timeline` as the `broll` track.

## Hard rules (enforced)

- Never over a `hook` line.
- Never over a reaction.
- ≤ 60% of total runtime under B-roll.
- ≥ 0.5s of bare A-roll between adjacent lay-overs.
- Lay-over duration ≤ underlying A-roll duration.
- Lay-overs land 1–3s **after** the line lands, never on the cut.
- `audio: false` by default.

## Footage matching

Use case-insensitive partial match (port of `findFootageUrl`). A keyword `"runway walk"` matches `BROLL_runway_walk_03.mov` and `Runway Walk Final.mov`.

## Failure modes

- If you can't cover the spine without breaking the 60% rule, return fewer lay-overs and flag the gap.
- If there's no footage that matches a key beat, say so explicitly — don't substitute generic.
