# B-roll Matching

You are placing B-roll lay-overs over a paper-edited A-roll spine. Read `lattimore_taste.md` first.

## Inputs

- **Paper edit** — the A-roll select array (with `role`, `transcript`, in/out).
- **Footage map** — analyzed B-roll clips with summaries / shot lists.
- **Music bed** (optional) — for tempo reference only.

## Output schema

```json
[
  {
    "clip": "BROLL_runway_walk_03.mov",
    "in":  4.20,
    "out": 6.80,
    "over_aroll_at": 17.4,
    "audio": false,
    "covers": "INT_002 12.48–18.92",
    "why": "she says 'walking out' — we land 1.6s after, on her stride"
  }
]
```

`over_aroll_at` is a **timeline second on V1** (the assembled A-roll), not a source-clip second.

## Hard rules

1. **Never lay over a hook line.** Hook plays clean on the talent's face.
2. **Never lay over a reaction.** Reactions are hero shots — see taste doc.
3. **≤ 60% of total runtime under B-roll.** Compute it before you finalize.
4. **≥ 0.5s of bare A-roll between adjacent lay-overs.** No back-to-back lay-overs touching.
5. **Lay-over duration ≤ underlying A-roll duration.** A 1.5s lay-over cannot extend past the A-roll select it sits on.
6. **Land 1–3s after the line lands.** Not on the cut, not on the word. After.
7. **`audio: false` by default.** Natsound only when the lay-over is *about* the sound (a runway clap, a zipper, a cheer).

## How to choose footage

- Start with the **turn** and the **resolve**: what visual makes those land harder? Pick those first.
- For texture: prefer specific over generic. A close-up of hands beats a wide of the room.
- Match energy, not subject. If the line is quiet, the lay-over is quiet — even if it's "exciting" footage.
- Use the footage map's case-insensitive keyword match (`findFootageUrl`-style) to find candidates fast.

## Anti-patterns

- Symmetric lay-over rhythm (every line covered the same way).
- Covering a great delivery with B-roll because you were "supposed to."
- Music-video cutting on the beat.
- Two adjacent lay-overs from the same setup — vary the angle.

## Self-check before output

- [ ] No lay-over over a `hook` or `reaction` line.
- [ ] Sum of lay-over durations ÷ total runtime ≤ 0.60.
- [ ] Every adjacent pair has ≥ 0.5s gap.
- [ ] Every lay-over duration ≤ its underlying A-roll duration.
- [ ] Every `over_aroll_at` is 1–3s after its line's land.
