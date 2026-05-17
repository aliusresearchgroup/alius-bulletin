# Cover Art

This folder contains standalone TeX entry points for the ALIUS Bulletin covers, Issues 1-7.

The editable source artwork is intentionally limited to two shared files in `assets/`:

- `front-cover-empty-no-leaf.pdf`
- `alius-leaf.svg`

`alius-leaf.svg` is the true vector leaf asset: three SVG paths extracted from the animated ALIUS brand source, with multiply blending preserving the overlap logic. The original animated vector file is retained in `source-assets/` for provenance and regeneration, but it is not used directly by the covers.

The common cover layer is generated once in `cover-style.tex`:

- the background PDF
- the ALIUS vector leaf
- the shared `ALIUS / BULLETIN / exploring the diversity of consciousness` header block

Each `issueXX-cover.tex` file contains only issue-specific content:

- the editor line under the header
- the left-side interviewee names, placed against shared right-edge arch bins that follow the white area of the background art
- the issue number, date line, and website values in the footer

All text remains live TeX text; no per-issue raster overlays are used.

The QA references in `reference-covers/` are comparison inputs only; they are not used to build the covers.

Compile one cover from the repository root:

```powershell
1..2 | ForEach-Object {
  pdflatex -interaction=nonstopmode -halt-on-error -shell-escape -output-directory=Cover-Art Cover-Art/issue01-cover.tex
}
```

Build all covers and then all issue PDFs:

```powershell
.\build-bulletins.ps1
```

Render a reference comparison sheet while tuning the issue-specific text layer:

```powershell
py Cover-Art\compare_covers.py
```

`cover-style.tex` is engine-aware. Overleaf can compile the cover files with `pdflatex`; XeLaTeX/LuaLaTeX are also supported for local font matching. Under pdfTeX, the issue-specific text layer uses TeX Live's packaged Lato and Arial fonts when available, with Helvetica-compatible fallbacks only if those packages are missing.

For Overleaf/pdfTeX reliability, `cover-style.tex` first includes `generated/alius-leaf-from-svg.pdf`, which is a committed vector cache derived from `assets/alius-leaf.svg`. The SVG remains the canonical editable leaf source; the cache avoids an Inkscape dependency while preserving vector output. For local preview work, the style also accepts an untracked raster cache at `Cover-Art/.build/alius-leaf-preview.png`, then falls back to direct SVG conversion.

Regenerate the static SVG and vector PDF cache from the animated source:

```powershell
py Cover-Art\generate_leaf_cache.py
```

The second LaTeX pass is required because the shared renderer uses TikZ page anchors for absolute positioning.
