---
name: hook-finder
description: Score hook candidates 0–10 on Fear / Desire / Curiosity, sum to total, identify dominant driver and risk. Mirrors the IM8 bot's scoreHooks(). Use to vet hook selects before locking a paper edit.
---

# hook-finder

Score one or more hook candidate lines.

## Input

A list of candidate hook lines (verbatim transcript text). Optionally with delivery notes (cold open, mid-thought, restart, etc).

## Output schema

```json
[
  {
    "text": "The thing nobody tells you is —",
    "fear": 4,
    "desire": 6,
    "curiosity": 9,
    "total": 19,
    "dominant": "curiosity",
    "risk": "Curiosity-led hooks under-deliver if the payoff isn't planted in the next 10s."
  }
]
```

## Scoring rubric

Each axis is 0–10:

- **Fear** — does the line surface a stake, threat, or loss the viewer recognizes? 0 = none, 10 = visceral, immediate.
- **Desire** — does the line name a wanted state (status, intimacy, freedom, recognition)? 0 = none, 10 = sharp and concrete.
- **Curiosity** — does the line open an information gap the viewer needs closed? 0 = closed, 10 = aching gap.

`total = fear + desire + curiosity`. `dominant` is the highest single axis (ties broken curiosity > desire > fear, matching how Lattimore's pieces tend to sit).

## Risk notes

- **Fear-dominant** — risk is overplay. Lattimore work rarely leads on fear; flag if fear ≥ 8.
- **Desire-dominant** — risk is "commercial" tone. Make sure the desire is named in the talent's voice, not the brief's.
- **Curiosity-dominant** — risk is no payoff. Plant resolution in the first 10s.

## When to use

- Before locking a paper edit. If `total < 18` for the chosen hook, look at alternatives.
- When a brief asks for "a stronger hook" — score what we have, then score what could replace it.

## What this is NOT

- Not a quality score. A 25 with weak delivery loses to a 19 delivered cold.
- Not a substitute for taste. Use the score to surface candidates, not to pick the winner.
