# Cover Verification

## Shared workflow

The cover workflow now uses exactly two shared artwork assets:

- `assets/front-cover-empty-no-leaf.pdf`
- `assets/alius-leaf.svg`

`assets/alius-leaf.svg` is a static vector leaf extracted from the animated ALIUS brand source. It uses three SVG paths and multiply blending for the leaf overlaps; it no longer embeds raster PNG data.

`cover-style.tex` owns the common layer for every issue:

- the background PDF
- the ALIUS leaf, sourced from the SVG
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

The cover sources are compatible with Overleaf's `pdflatex` default. `cover-style.tex` uses `fontspec` only under XeLaTeX/LuaLaTeX. Under pdfTeX, it uses TeX Live's packaged Lato fonts for the classic left-column interviewee names plus the early/late issue-specific text layer, and packaged Arial for Issue 04 when available, with Helvetica-compatible fallbacks only if those packages are missing.

All left-column interviewee names now intentionally use the Issue 01-02 convention: light Lato, a larger initial letter, and smaller following capitals. They are also placed with shared right-edge arch bins that follow the figure contour, so later issues can reuse the same curved alignment system instead of bespoke center coordinates.

The TeX layer includes `generated/alius-leaf-from-svg.pdf`, a committed vector cache regenerated from `assets/alius-leaf.svg` and `source-assets/logo-ALIUS-original-animated-leaf.svg` with:

```powershell
py Cover-Art\generate_leaf_cache.py
```

The generated cache contains no raster images (`pdfimages -list Cover-Art\generated\alius-leaf-from-svg.pdf` returns an empty image list).

Render a fresh historical comparison sheet:

```powershell
py Cover-Art\compare_covers.py
```

Because the header is now deliberately standardized, full-cover pixel identity against the historical references is no longer the acceptance criterion. The comparison sheet is retained to tune the issue-specific text placements against the historical covers while keeping the shared header fixed.
