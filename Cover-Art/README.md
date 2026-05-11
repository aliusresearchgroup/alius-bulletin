# Cover Art

This folder contains standalone LaTeX entry points for the ALIUS Bulletin covers, Issues 1-7.

Each `issueXX-cover.tex` compiles one cover PDF. The TeX files intentionally include the canonical first page extracted from the original full issue PDF, which is the highest-fidelity way to preserve the published cover art while keeping an Overleaf-renderable source file for each cover.

Compile from the repository root, for example:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=Cover-Art Cover-Art/issue01-cover.tex
```

The `reference-covers/` files are one-page source references extracted from the original full issue PDFs. Do not replace them unless the published source cover changes.
