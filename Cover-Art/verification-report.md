# Cover Verification

## Shared workflow

The cover workflow uses exactly two shared artwork assets:

- `assets/front-cover-empty-no-leaf.pdf`
- `assets/alius-leaf.svg`

`assets/front-cover-empty-no-leaf.pdf` is the only committed PDF asset tolerated in this repository. It is allowed because its explicit purpose is to serve as the shared cover background substrate. All other PDFs are generated outputs or external QA references and should not be committed.

`assets/alius-leaf.svg` is a static vector leaf extracted from the animated ALIUS brand source. It uses three SVG paths and multiply blending for the leaf overlaps; it is the canonical artwork source. `cover-style.tex` renders the leaf through `generated/alius-leaf-paths.tex`, a TeX path cache generated from that SVG rather than a PDF cache.

`cover-style.tex` owns the common layer for every issue:

- the background PDF
- the ALIUS leaf, sourced from the SVG-derived TeX paths
- the shared header block: `ALIUS`, `BULLETIN`, and `exploring the diversity of consciousness`

The issue files own only:

- the editor line
- the left-side interviewee placements
- the issue number, date line, and website text

## QA commands

Build all covers and bulletin PDFs as ignored local outputs:

```powershell
.\build-bulletins.ps1
```

The cover sources are compatible with pdfTeX without Inkscape or shell-escape SVG conversion. `cover-style.tex` uses `fontspec` only under XeLaTeX/LuaLaTeX. Under pdfTeX, it uses TeX Live's packaged Lato fonts for the classic left-column interviewee names plus the early/late issue-specific text layer, and packaged Arial for Issue 04 when available, with Helvetica-compatible fallbacks only if those packages are missing.

Render a fresh comparison sheet from generated cover PDFs and PNG references:

```powershell
py Cover-Art\compare_covers.py
```

Full-cover pixel identity against historical references is not the acceptance criterion. The comparison sheet is retained only to tune issue-specific text placements while keeping the shared source-first cover layer fixed.
