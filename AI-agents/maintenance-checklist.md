# Maintenance Checklist

Use this checklist when adding, regenerating, or reviewing bulletin material.

## Structure

- [ ] Root contains only the intended top-level folders plus `.git`.
- [ ] Every piece lives under `Interviews/IssueXX/<LastNames>/`.
- [ ] Every piece folder has exactly one `.tex`, one `.bib`, and one generated `.pdf`.
- [ ] `Bulletins/` contains `issueXX.tex` and `issueXX.pdf` for each complete issue.
- [ ] `Instructions/` contains matching `.tex` and `.pdf` instruction/template files.
- [ ] `Shared-assets/project-manifest.json` reflects the current top-level folders and exported files.

## Compilation

- [ ] Compile each changed interview `.tex` from the repository root.
- [ ] Compile each changed issue `.tex` from the repository root.
- [ ] Confirm no LaTeX errors remain.
- [ ] Remove transient build outputs unless they are deliberately tracked.

## Visual Fidelity

- [ ] Compare each generated interview PDF to its source/original PDF.
- [ ] Check page count and page size.
- [ ] Check title block, author/interviewer credits, quotation layout, parentheses, and bibliography styling.
- [ ] Check that issue-level PDFs include the expected pieces in the expected order.
- [ ] Update `Shared-assets/qa/visual-fidelity-report.md` when QA is rerun.

## Git Hygiene

- [ ] Stage only intentional files.
- [ ] Commit with a short message describing the archival or documentation change.
- [ ] Push to `origin/main` when the update is ready for GitHub.
