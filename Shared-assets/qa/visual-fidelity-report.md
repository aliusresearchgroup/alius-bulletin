# Visual Fidelity Report

This report previously documented a facsimile workflow that included published article PDFs. That workflow has been retired.

Current repository contract:

- interview and issue sources must typeset from native LaTeX;
- generated PDFs are local build outputs and remain untracked;
- the only committed PDF asset tolerated in the repository is `Cover-Art/assets/front-cover-empty-no-leaf.pdf`, the shared cover background;
- the cover leaf is sourced from `Cover-Art/assets/alius-leaf.svg`.

Future visual QA should compare generated outputs against external references or explicitly approved non-build-path resources, never by wiring original article PDFs into the TeX sources.
