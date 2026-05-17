# Cover Art

This folder contains standalone TeX entry points for the ALIUS Bulletin covers, Issues 1-7.

The source artwork is intentionally limited to two shared files in `assets/`:

- `front-cover-empty-no-leaf.pdf`
- `alius-leaf.svg`

The common cover layer is generated once in `cover-style.tex`:

- the background PDF
- the ALIUS leaf SVG
- the shared `ALIUS / BULLETIN / exploring the diversity of consciousness` header block

Each `issueXX-cover.tex` file contains only issue-specific content:

- the editor line under the header
- the left-side interviewee names, with explicit placements that follow the white area of the background art
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

`cover-style.tex` is engine-aware. Overleaf can compile the cover files with `pdflatex`; XeLaTeX/LuaLaTeX are also supported for local font matching.

`cover-style.tex` prefers the canonical SVG leaf. For local preview work, it also accepts an untracked raster cache at `Cover-Art/.build/alius-leaf-preview.png`; Overleaf can compile directly from the SVG path.

The second LaTeX pass is required because the shared renderer uses TikZ page anchors for absolute positioning.
