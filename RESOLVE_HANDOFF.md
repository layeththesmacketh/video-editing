# Handing the cutdown off to DaVinci Resolve

This repo can produce two flavors of cutdown for the same interview:

1. **Export-mode (today).** The splitter runs against a flattened `.mov`
   render of the master. Output: an FCPXML where every `[in, out]` is a
   timecode in that single export file. Resolve imports it; you finish
   from there. **Cuts will not round-trip back to the master clips.**
2. **Master-mode (the drive is plugged in).** The splitter runs against
   the actual Resolve master timeline. Output: an FCPXML where each
   soundbite references its **original master clip** at the original
   source timecode. Cuts round-trip cleanly.

## When export-mode is fine

- The export was rendered from the current master and the master has not
  been edited since.
- No re-trims, added/removed shots, retimes, or slate adds since the
  render.
- Both timelines run at the same rate and start at the same TC.

If all four are true, the export and the master are mirror images in
time. Soundbite times in one are soundbite times in the other.

## How to verify before trusting a 1:1 mapping

When the drive is in, take three soundbites — one early, one in the
middle, one near the tail — and scrub each `T_export` on the master
timeline. If you hear the same word at the same beat in both, the
mapping is exact. If the late one drifts, do not trust the cross-
reference; switch to master-mode.

## Master-mode workflow (the bulletproof path)

When the drive is connected:

1. Open the project in Resolve. Confirm the master timeline opens cleanly
   and the master clips relink.
2. Render an audio-only `.wav` from the master timeline (or a tiny proxy
   `.mov`). This is just for transcription — the master clips stay
   untouched.
3. Run `python -m lattimore.cli cutdown <render.wav> <out_dir>` — same
   command, same skill, just pointed at master-timeline-rendered audio.
4. Now `soundbites.json` carries timeline-times that match the master
   timeline directly (because we transcribed off it).
5. To get those segments back to the master clips at the right source-
   timecode:
   - **Quick path:** import the FCPXML into the existing Resolve project
     as a new sequence; copy/paste the V2 segments above the master on
     V2 of the master timeline. The relink dialog will offer to map the
     render back to the master clips automatically (confirm
     timecodes / framerates match).
   - **Direct path (requires `davinci-resolve-mcp`):** read the master
     timeline's clip list via the MCP, walk each soundbite's
     `[in_master, out_master]`, locate the source clip + source TC for
     each end, and emit moves that lift those segments to V2 in the
     master timeline. This is more work to wire up; do it only if the
     quick path is insufficient.

## Why we don't try to map export → master automatically

We could, when the export is a faithful render. The math is trivial.
The risk isn't the math — it's silent drift. A frame trim on the master
shifts every downstream soundbite by a frame. A retime nest invalidates
a region. The verifying step above costs 30 seconds. If you trust the
result, the rest is mechanical.

## Companion MCPs (recommended, install separately)

- `davinci-resolve-mcp` — direct Resolve control. Useful for the
  master-mode direct path.
- `vfx-mcp` — visual-effects helpers.
- `stockpile` — stock-footage search.
- `fast-whisper-mcp` — alternative transcription backend.

None of these are bundled here. Install only when you actually need them.
