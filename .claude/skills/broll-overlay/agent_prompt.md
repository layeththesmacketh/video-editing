# Agent procedure: broll-overlay

## Step 1 — read

`prompts/lattimore_taste.md`, then `prompts/broll_matching.md`.

## Step 2 — mark untouchables

Walk the paper edit and mark which selects are **off limits** for lay-over:

- every `role: hook` select
- every reaction beat (annotated in the brief or noted in `interview-paper-edit`'s `why`)

These play clean.

## Step 3 — start with turn and resolve

Pick lay-overs for the `turn` and `resolve` first. These need the strongest visual anchors. If you don't have visual that earns them, leave them clean — better than wallpaper.

## Step 4 — fill texture

For each `texture` select, ask: does this line need a visual to land, or is the talent's face enough? Only cover when covering helps. Match energy, not subject.

## Step 5 — place precisely

For each lay-over:

```
land_t       = the timeline-second where the line resolves
over_aroll_at = land_t + (1.0 to 3.0)   # 1–3s AFTER the land
duration      = chosen lay-over length
```

Verify: `over_aroll_at + duration ≤ end of underlying A-roll select`.

## Step 6 — global check

Compute:

```
coverage = sum(b.out - b.in for b in broll) / total_runtime
```

If `coverage > 0.60`, drop the weakest lay-over (least specific, most generic) and re-check.

For every adjacent pair `(b_i, b_{i+1})` in timeline order, check:

```
(b_{i+1}.over_aroll_at) - (b_i.over_aroll_at + b_i.out - b_i.in) >= 0.5
```

## Step 7 — output

Emit the JSON array per `prompts/broll_matching.md`. Include a one-line `why` per entry.

## Common mistakes

- Symmetric rhythm (line, B-roll, line, B-roll). Vary it.
- Covering a great delivery to "be safe."
- Two adjacent lay-overs from the same setup.
- Cutting on the word instead of 1–3s after the land.
