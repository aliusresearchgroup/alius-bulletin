# Cover Art

This folder contains standalone TeX entry points for the ALIUS Bulletin covers, Issues 1-7.

The only committed PDF tolerated in the repository is the shared cover background:

- `assets/front-cover-empty-no-leaf.pdf`

The editable vector leaf source is:

- `assets/alius-leaf.svg`

`alius-leaf.svg` is the canonical leaf asset: three SVG paths extracted from the animated ALIUS brand source, with multiply blending preserving the overlap logic. The original animated vector file is retained in `source-assets/` for provenance and regeneration, but it is not used directly by the covers.

The common cover layer is generated in `cover-style.tex` from those two assets:

- the background PDF
- the ALIUS vector leaf, rendered from a TeX path cache generated from the SVG
- the shared `ALIUS / BULLETIN / exploring the diversity of consciousness` header block

Each `issueXX-cover.tex` file contains only issue-specific live TeX text:

- the editor line under the header
- the left-side interviewee names
- the issue number, date line, and website values in the footer

No committed per-issue cover PDFs are source assets. Cover PDFs are generated locally and ignored by Git.

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

Render a comparison sheet while tuning the issue-specific text layer, using PNG references only:

```powershell
py Cover-Art\compare_covers.py
```

`cover-style.tex` is engine-aware. Overleaf can compile the cover files with `pdflatex` without Inkscape or shell-escape SVG conversion, because `generated/alius-leaf-paths.tex` is a TeX path cache derived from the SVG. XeLaTeX/LuaLaTeX are also supported for local font matching. Under pdfTeX, the issue-specific text layer uses TeX Live's packaged Lato and Arial fonts when available, with Helvetica-compatible fallbacks only if those packages are missing.

Regenerate the static SVG and TeX path cache from the animated source:

```powershell
py Cover-Art\generate_leaf_cache.py
```

The second LaTeX pass is required because the shared renderer uses TikZ page anchors for absolute positioning.
