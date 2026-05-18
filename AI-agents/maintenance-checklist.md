# Maintenance Checklist

- [ ] No article, interview, issue, guideline, or QA PDF is staged unless explicitly approved.
- [ ] The only committed PDF asset is `Cover-Art/assets/front-cover-empty-no-leaf.pdf`.
- [ ] Cover leaf artwork is sourced from `Cover-Art/assets/alius-leaf.svg`.
- [ ] Interview `.tex` files typeset native LaTeX and do not include published/original article PDFs.
- [ ] Every bulletin interview has either a rendered original abstract or a commented draft/TBA abstract block.
- [ ] `AI-agents/check_style_uniformity.py` has been run after text-extraction or formatting repairs.
- [ ] Issue files compile via `build-bulletins.ps1`, which generates local cover/issue PDFs as ignored outputs.
- [ ] LuaLaTeX remains the faithful build path, and the pdfTeX fallback still avoids `fontspec` failures for direct Overleaf/file compiles.
- [ ] `AI-agents/formatting-context.md` reflects any new formatting or compile-context lesson from this run.
- [ ] `.aux`, `.log`, `.out`, `.toc`, generated PDFs, and scratch outputs are not staged.
- [ ] Any visual QA references are external or clearly non-build-path resources.
- [ ] Completed changes are committed and pushed to `origin/main` for Overleaf sync.
- [ ] `AI-agents/enforce_quote_and_doi_invariants.py` has been run after regenerating interview sources.
- [ ] `AI-agents/validate_quote_and_doi_rendering.py` passes: no oversized `?` pull quotes, all 41 interview DOI lines are green single-line `\href` links, and every interview has the normalized top-left/bottom-right citation panel.
- [ ] Citation panels preserve the edition-wide structure: white left-column panel, citation text top-left, DOI bottom-right, no overlap with author/contact text or abstract/heading blocks.
