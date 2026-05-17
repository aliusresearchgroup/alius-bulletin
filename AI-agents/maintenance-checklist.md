# Maintenance Checklist

- [ ] No article, interview, issue, guideline, or QA PDF is staged unless explicitly approved.
- [ ] The only committed PDF asset is `Cover-Art/assets/front-cover-empty-no-leaf.pdf`.
- [ ] Cover leaf artwork is sourced from `Cover-Art/assets/alius-leaf.svg`.
- [ ] Interview `.tex` files typeset native LaTeX and do not include published/original article PDFs.
- [ ] Issue files compile via `build-bulletins.ps1`, which generates local cover/issue PDFs as ignored outputs.
- [ ] `.aux`, `.log`, `.out`, `.toc`, generated PDFs, and scratch outputs are not staged.
- [ ] Any visual QA references are external or clearly non-build-path resources.
