---
name: im8-naming
description: Apply the IM8 filename convention when client is im8. Use at export time on any deliverable filename. Returns a properly formed name following YYMMDD_FORMAT_ADTYPE_ICP_PROBLEM_CREATIVENUMBER_AGENCY_BATCHNAME_CREATORTYPE_CREATORNAME_HOOKMESSAGE_WTAD_LDP.
---

# im8-naming

The IM8 filename convention. Apply only when `library.yaml` has `client: im8`.

## Convention

```
YYMMDD_FORMAT_ADTYPE_ICP_PROBLEM_CREATIVENUMBER_AGENCY_BATCHNAME_CREATORTYPE_CREATORNAME_HOOKMESSAGE_WTAD_LDP
```

Underscore-separated. Trailing extension is appended by the caller (`.mp4`, `.mov`).

## Field reference

| # | Field            | Notes                                                              |
|---|------------------|--------------------------------------------------------------------|
| 1 | YYMMDD           | Delivery date (e.g. `260506` for 2026-05-06)                       |
| 2 | FORMAT           | `9x16`, `1x1`, `16x9`, `4x5`                                       |
| 3 | ADTYPE           | `STATIC`, `VIDEO`, `CAROUSEL`, etc                                 |
| 4 | ICP              | Default `GEN`                                                      |
| 5 | PROBLEM          | Default `BRAND`                                                    |
| 6 | CREATIVENUMBER   | Blank by default (empty between underscores)                       |
| 7 | AGENCY           | Default `IM8`                                                      |
| 8 | BATCHNAME        | Campaign / batch label                                             |
| 9 | CREATORTYPE      | `UGC`, `INFL`, `BRAND`                                             |
| 10| CREATORNAME      | Talent identifier                                                  |
| 11| HOOKMESSAGE      | Short hook label (no spaces; use camelCase or dashes)              |
| 12| WTAD             | Default `NA`                                                       |
| 13| LDP              | Default `HOMEPAGE`                                                 |

## Defaults

```
ICP=GEN  PROBLEM=BRAND  AGENCY=IM8  WTAD=NA  LDP=HOMEPAGE
CREATIVENUMBER=""        # blank
```

## Organic posts

Organic uses **twelve underscores** (`____________`) for the campaign-only fields between the date/format/adtype prefix and the creator block. Effectively: keep the structure, leave campaign fields empty, separator-only.

## Examples

Paid:

```
260506_9x16_VIDEO_GEN_BRAND__IM8_NYFW26_INFL_KennedyRyan_walkOut_NA_HOMEPAGE.mp4
```

Note the empty `CREATIVENUMBER` (double underscore between `BRAND` and `IM8`).

Organic:

```
260506_9x16_VIDEO____________INFL_KennedyRyan_walkOut_NA_HOMEPAGE.mp4
```

## Procedure

1. Confirm `client: im8` in `library.yaml`.
2. Gather inputs from the user / library (date, format, ad type, batch, creator, hook label).
3. Apply defaults for any missing campaign field.
4. Assemble underscore-joined name. Validate no spaces, no double-underscore-except-CREATIVENUMBER (or organic block).
5. Append the deliverable extension.
