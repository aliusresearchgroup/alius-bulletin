# Cover Verification

## Shared workflow

The cover workflow now uses exactly two shared artwork assets:

- `assets/front-cover-empty-no-leaf.pdf`
- `assets/alius-leaf.svg`

`cover-style.tex` owns the common layer for every issue:

- the background PDF
- the ALIUS leaf SVG
- the shared header block: `ALIUS`, `BULLETIN`, and `exploring the diversity of consciousness`

The issue files own only:

- the editor line
- the left-side interviewee placements
- the issue number, date line, and website text

The generated header crop was compared across Issues 01-07 after compilation; all seven header crops were identical.

## Historical source findings

The original cover references do not all preserve the same kind of source data:

| Issue | Original reference evidence |
| --- | --- |
| 01 | Raster-only cover PDF; no recoverable PDF font metadata. |
| 02 | Raster-only cover PDF; no recoverable PDF font metadata. |
| 03 | Live PDF text with a stripped embedded font; geometry is closest to a Lato-family face among locally available fonts. |
| 04 | Live PDF text using embedded `ArialMT`. |
| 05 | Raster-only cover PDF; no recoverable PDF font metadata. |
| 06 | Historical cover reference is a PNG image, not a live-text cover PDF. |
| 07 | Historical cover reference is a PNG image, not a live-text cover PDF. |

The later historical covers used a different `ALIUS` title treatment. That difference is intentionally no longer reproduced: the shared header was standardized across all seven issues by request.

## QA commands

Build all covers and bulletin PDFs:

```powershell
.\build-bulletins.ps1
```

Render a fresh historical comparison sheet:

```powershell
py Cover-Art\compare_covers.py
```

Because the header is now deliberately standardized, full-cover pixel identity against the historical references is no longer the acceptance criterion. The comparison sheet is retained to tune the issue-specific text placements against the historical covers while keeping the shared header fixed.
