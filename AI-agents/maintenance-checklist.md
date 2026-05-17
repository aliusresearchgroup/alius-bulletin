# Maintenance Checklist

Use this checklist when adding, regenerating, or reviewing bulletin material.

## Structure

- [ ] Root contains only the intended top-level folders plus `.git`.
- [ ] Every piece lives under `Interviews/IssueXX/<LastNames>/`.
- [ ] Every piece folder has exactly one `.tex`, one `.bib`, and one generated `.pdf`.
- [ ] `Bulletins/` contains `issueXX.tex` and `issueXX.pdf` for each complete issue.
- [ ] `Cover-Art/` contains `issueXX-cover.tex` and `issueXX-cover.pdf` for each issue cover.
- [ ] `Cover-Art/reference-covers/` contains the one-page original cover references used by the cover TeX files.
- [ ] `Guidelines/` contains guideline/template sources, original DOCX guideline files, and rendered PDFs.
- [ ] `Shared-assets/project-manifest.json` reflects the current top-level folders and exported files.

## Compilation

- [ ] Compile each changed interview `.tex` from the repository root.
- [ ] Compile each changed issue `.tex` from the repository root.
- [ ] Compile each changed cover `.tex` from the repository root.
- [ ] Confirm no LaTeX errors remain.
- [ ] Remove transient build outputs unless they are deliberately tracked.

## Visual Fidelity

- [ ] Compare each generated interview PDF to its source/original PDF.
- [ ] Check page count and page size.
- [ ] Check title block, author/interviewer credits, quotation layout, parentheses, and bibliography styling.
- [ ] Check that issue-level PDFs include the expected pieces in the expected order.
- [ ] Check cover PDFs against page 1 of the corresponding original full issue PDF.
- [ ] Update `Shared-assets/qa/visual-fidelity-report.md` when QA is rerun.
- [ ] Update `Shared-assets/qa/cover-art-visual-fidelity-report.md` when cover QA is rerun.

## Git Hygiene

- [ ] Stage only intentional files.
- [ ] Commit with a short message describing the archival or documentation change.
- [ ] Push to `origin/main` when the update is ready for GitHub.
