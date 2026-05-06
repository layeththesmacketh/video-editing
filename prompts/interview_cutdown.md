# Interview Cutdown

You are picking A-roll selects for a Lattimore interview cutdown. Read `lattimore_taste.md` first.

## Inputs

- **Transcript** with word-level timestamps from WhisperX.
- **Target runtime** in seconds (e.g. 90).
- **Brief** — what the piece is about, the angle, any must-includes.
- **Optional** — talent dossier (`talent_dossier`).

## Output schema

A JSON array of A-roll selects:

```json
[
  {
    "clip": "INT_002.mov",
    "in":  12.480,
    "out": 18.920,
    "role": "hook",
    "transcript": "The thing nobody tells you is —",
    "why": "lands cold, no setup, immediate stakes"
  }
]
```

`role` ∈ `{hook, premise, texture, turn, resolve}`.

## Hard rules

1. **Never cut mid-word.** `in` and `out` are word-boundary timestamps from the WhisperX `words` array. If a word straddles your intended boundary, snap to the nearest word edge that preserves meaning.
2. **Total runtime within ±10% of target.** Sum of `out - in` across selects. If you overshoot, cut the weakest *texture* line. Never cut hook or resolve to hit time.
3. **Sequence for arc.** The output is ordered:
   - `hook` (1, sometimes 2) — cold open, immediate stakes.
   - `premise` (1–2) — what this is actually about.
   - `texture` (2–6) — color, specifics, the human stuff.
   - `turn` (1) — the pivot, the unexpected admission, the reframe.
   - `resolve` (1) — landing line. Quiet, earned.
4. **One thought per select.** Don't staple two ideas together with an awkward bridge.
5. **Keep ums and breaths when they're texture, drop them when they're noise.** Lattimore likes the human seams; he doesn't like dead weight.

## How to choose

- Read the whole transcript before picking anything.
- Mark every line that *could* be a hook. Pick the coldest, most concrete one.
- For the turn: find the moment the talent surprises themselves. That's it.
- For the resolve: short. Earned. Not a thesis statement.
- If two lines say the same thing, keep the one with better delivery, not the one with cleaner words.

## Anti-patterns

- Picking selects in transcript order without re-sequencing.
- Filling all five roles when the material only supports four.
- Cutting on the period instead of after the breath.
- Quoting the brief back at us instead of letting the talent talk.
