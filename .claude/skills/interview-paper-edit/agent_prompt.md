# Agent procedure: interview-paper-edit

## Step 1 — read

Read in order: `prompts/lattimore_taste.md`, `prompts/interview_cutdown.md`. Don't skip.

## Step 2 — full pass

Read every transcript end-to-end before picking anything. Note in working memory:

- Strongest **hook** candidates (cold, concrete, immediate stakes).
- Strongest **turn** candidate (the surprise admission).
- A handful of **resolve** candidates (short, earned).
- Texture clusters worth visiting.

Don't pick yet.

## Step 3 — score hooks

If the user wants, run candidate hook lines through `score_hooks` (Fear / Desire / Curiosity, 0–10 each). Pick the one with the strongest dominant driver, not the highest total — Lattimore work is rarely fear-led.

## Step 4 — sequence

Lay the arc out:

```
hook  →  premise  →  texture (×2–6)  →  turn  →  resolve
```

Order selects in this sequence. The transcript order does not matter.

## Step 5 — snap to word boundaries

For each select, set `in` and `out` to word-edge timestamps from WhisperX. **Verify** by checking that no word in the `words` array straddles either boundary.

## Step 6 — runtime check

```
total = sum(out - in for s in selects)
abs(total - target) / target <= 0.10
```

If you overshoot, drop the weakest **texture** select. Never cut hook or resolve to hit time.

## Step 7 — output

Emit the JSON array in the schema from `prompts/interview_cutdown.md`. Include a one-line `why` per select. Hand to the next stage.

## Common mistakes

- Picking selects in transcript order. Don't.
- Cutting on the period instead of after the breath.
- Picking a "good quote" that quotes the brief back. The talent's voice runs the piece.
- Filling all five roles when only four are real.
