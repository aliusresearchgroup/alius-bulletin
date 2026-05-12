# Cover Art

This folder contains standalone LaTeX entry points for the ALIUS Bulletin covers, Issues 1-7.

Each `issueXX-cover.tex` builds the cover from layered assets in `assets/`:

- `issueXX-background.pdf` is the text-free cover artwork.
- `issueXX-text-layer.pdf` is the exact original PDF text layer when the reference cover exposed font/text objects.
- `issueXX-text-overlay.png` is a 600 DPI transparent overlay for raster-only reference covers that did not expose font/text objects.
- `issueXX-visual-correction.png` preserves exact rendered pixels where PDF text-layer re-embedding introduced renderer-level anti-aliasing differences.

The `reference-covers/` files are QA references only. The build sources no longer include those PDFs directly as cover pages.

Compile one cover from the repository root:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=Cover-Art Cover-Art/issue01-cover.tex
```

Build all covers and then all issue PDFs:

```powershell
.\build-bulletins.ps1
```

The issue sources in `Bulletins/` include the generated `Cover-Art/issueXX-cover.pdf` as page 1. The build script then finalizes each `Bulletins/issueXX.pdf` by replacing that first page with the exact verified cover PDF object, avoiding renderer-level perturbation from PDF re-embedding.
