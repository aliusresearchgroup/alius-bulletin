# Formatting Context for Future Agents

This file records the current formatting and build assumptions for the ALIUS Bulletin reconstruction. Update it whenever a formatting, compile-engine, layout, or visual-QA lesson changes.

## Current build posture

- The source of truth is editable LaTeX, not pre-existing article PDFs.
- Generated interview files are native visual reconstructions: absolute-positioned TikZ/text/image elements derived from off-repo reference layout data.
- LuaLaTeX is the faithful build engine. It preserves the intended OpenType font path through `fontspec` for Lato, Cormorant Garamond, Times New Roman, Calibri, and Cambria.
- Overleaf can still invoke pdfLaTeX when a file is selected directly or when project settings drift. The root `.latexmkrc` forces latexmk/Overleaf to use LuaLaTeX, and every generated interview file has an `iftex` pdfTeX fallback so direct pdfLaTeX compilation no longer dies on `fontspec`.
- pdfLaTeX fallback output is for compile resilience only. Do not treat it as the visual-fidelity reference unless the user explicitly changes the target engine.

## Known formatting constraints

- Do not commit generated PDFs. The only committed PDF asset allowed is `Cover-Art/assets/front-cover-empty-no-leaf.pdf`, the explicit shared cover background resource.
- Cover leaf artwork is sourced from `Cover-Art/assets/alius-leaf.svg`; the generated TeX path cache is derived from that SVG.
- Extracted image elements inside interview folders are allowed when they represent real non-text image elements from the original layout.
- Abstract policy: every bulletin interview TeX file should now have either an original rendered abstract or a commented abstract metadata block. Commented draft/TBA abstracts stay non-rendered unless the user asks to render a revised edition, because rendering them would change the reconstructed PDF.
- Issue wrappers under `Bulletins/issueXX.tex` should compile from the repository root and input native interview sources.
- Decorative pull quotes can be extracted from Word/PDF as plain ASCII `"` even when the visible glyph is a typographic opening/closing quote. Oversized standalone quote spans should be normalized to curly `“` / `”` in source generation.
- Issue 6 PDFs use embedded Word subset fonts whose ToUnicode maps leak ligature-like artifacts into extracted text. The reconstruction script now normalizes the high-confidence glyph leaks (`fi`, `fl`, `ff`, `ffi`, `ft`, `Th`, `ti`, `gy`, etc.) before TeX escaping; do not reintroduce the raw extraction glyphs as visible LuaLaTeX text.
- Run `AI-agents/check_style_uniformity.py` after extraction repairs. It checks for suspicious private-font glyph leaks and isolated font/size/colour islands while ignoring deliberate inline italics, hyperlinks, running heads, and question/answer colour changes.
- Some visible reference DOIs in the original bulletins are themselves invalid or obsolete. Preserve original-visible text unless the user explicitly asks for a corrected/revised edition; record validity findings in citation QA reports instead of silently diverging from the reference PDF.

## Citation QA context

- `AI-agents/verify_citation_integrity.py` audits both the per-interview BibTeX library and DOI/URL tokens printed in reconstructed interview TeX files.
- The broad verification pass uses DOI content negotiation for ALIUS/Zenodo records and Crossref for ordinary scholarly reference DOIs. Run it politely (`--workers 1`) when checking hundreds of DOIs to avoid resolver rate limits being mistaken for citation failures.
- The current library-level result is clean for all 41 interview `.bib` DOIs: all resolve and titles match DOI metadata. A few author-list warnings are metadata-policy differences, e.g. Zenodo records sometimes list only the interviewee while the repo BibTeX lists interviewers/editors too.
- The current full-text DOI sweep found three DOI strings printed in the original bulletins that do not resolve as written: `10.1007/s13164014-0208-1`, `10.17151/culdr.2018.23.25`, and `10.34700/s66k-9j57`. Known likely/current corrections are `10.1007/s13164-014-0208-1`, `10.17151/culdr.2018.23.25.3`, and the repo-library DOI `10.34700/a5hm-fs14` for the Nichols & Nichols article, but changing visible TeX would intentionally break original-PDF fidelity.

## Operational rule

When work is done, push the newest committed state to `origin/main` so the user can sync Overleaf immediately. Keep the remote branch set minimal unless the user asks for PR-style branching.
