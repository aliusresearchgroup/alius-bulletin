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
- Abstract policy: every bulletin interview TeX file should now have either an original rendered abstract, a user-requested revised rendered abstract, or a commented abstract metadata block. Commented draft/TBA abstracts stay non-rendered unless the user asks to render a revised edition, because rendering them changes the reconstructed PDF.
- When a user explicitly asks for a revised abstract to render visibly, do not shrink it into microscopic metadata text. Use the bulletin's readable abstract style: a Lato `Abstract` label and body text at the same visual scale/family as answer prose (`\ALIUSFontCormorantRegular`, about 13.9bp in Issue 1 reconstructions), adding or reflowing pages if needed rather than compressing the abstract.
- Issue wrappers under `Bulletins/issueXX.tex` should compile from the repository root and input native interview sources.
- Decorative pull quotes can be extracted from Word/PDF as plain ASCII `"` even when the visible glyph is a typographic opening/closing quote. Oversized standalone quote spans should be normalized to `\ALIUSPullQuoteOpen` / `\ALIUSPullQuoteClose` rather than raw font-dependent glyphs.
- Issue 6 PDFs use embedded Word subset fonts whose ToUnicode maps leak ligature-like artifacts into extracted text. The reconstruction script now normalizes the high-confidence glyph leaks (`fi`, `fl`, `ff`, `ffi`, `ft`, `Th`, `ti`, `gy`, etc.) before TeX escaping; do not reintroduce the raw extraction glyphs as visible LuaLaTeX text.
- Run `AI-agents/check_style_uniformity.py` after extraction repairs. It checks for suspicious private-font glyph leaks and isolated font/size/colour islands while ignoring deliberate inline italics, hyperlinks, running heads, and question/answer colour changes.
- `AI-agents/check_style_uniformity.py` now also enforces category-level typography: title/subtitle lines should stay black Lato, interviewer questions should stay green Lato, answer/body prose should stay in the Cormorant body family apart from deliberate italics/links/symbol fallbacks, and pull-quote text should keep a uniform Lato quote style. Use this as the guardrail for the user's requested title/question/answer/quotation uniformity.
- Some visible reference DOIs in the original bulletins are themselves invalid or obsolete. Preserve original-visible text unless the user explicitly asks for a corrected/revised edition; record validity findings in citation QA reports instead of silently diverging from the reference PDF.

## Citation QA context

- `AI-agents/verify_citation_integrity.py` audits both the per-interview BibTeX library and DOI/URL tokens printed in reconstructed interview TeX files.
- The broad verification pass uses DOI content negotiation for ALIUS/Zenodo records and Crossref for ordinary scholarly reference DOIs. Run it politely (`--workers 1`) when checking hundreds of DOIs to avoid resolver rate limits being mistaken for citation failures.
- The current library-level result is clean for all 41 interview `.bib` DOIs: all resolve and titles match DOI metadata. A few author-list warnings are metadata-policy differences, e.g. Zenodo records sometimes list only the interviewee while the repo BibTeX lists interviewers/editors too.
- The current full-text DOI sweep found three DOI strings printed in the original bulletins that do not resolve as written: `10.1007/s13164014-0208-1`, `10.17151/culdr.2018.23.25`, and `10.34700/s66k-9j57`. Known likely/current corrections are `10.1007/s13164-014-0208-1`, `10.17151/culdr.2018.23.25.3`, and the repo-library DOI `10.34700/a5hm-fs14` for the Nichols & Nichols article, but changing visible TeX would intentionally break original-PDF fidelity.

## Operational rule

When work is done, push the newest committed state to `origin/main` so the user can sync Overleaf immediately. Keep the remote branch set minimal unless the user asks for PR-style branching.

## Pull-quote and DOI display invariants

- Oversized decorative pull quotes must never be literal `?` glyphs. They now render through `\ALIUSPullQuoteOpen` / `\ALIUSPullQuoteClose`, defined as TeX quote commands rather than Unicode/font-subset glyphs. This keeps both LuaLaTeX and pdfLaTeX/Overleaf fallbacks from substituting question marks.
- Every interview source must load `hyperref` in standalone mode, because the visible citation DOI is a live `\href`.
- Every interview source must define `ALIUSC1F8135` locally, because standalone files and issue wrappers both use that green for DOI links.
- Citation panels use APA 7 reference styling: the DOI is appended to the same citation paragraph after the final period, e.g. `ALIUS Bulletin, 1, 1-16. https://doi.org/<doi>`.
- Every interview's own DOI from its colocated `.bib` file must appear on page 1 in the normalized citation panel as a green (`ALIUSC1F8135`) linked URL: `\href{https://doi.org/<doi>}{https://doi.org/<doi>}`.
- DOI links must be single unbroken TeX lines. Do not split a DOI across `\ALIUSPlacedTextContent` spans or line-wrap the `\href`; the PDF should expose one complete clickable annotation per interview DOI.
- First-page citation panels have a uniform structure across issues: white panel background over the left citation column, citation text anchored top-left, and the DOI appended inline inside the same citation block. Do not detach the DOI as a bottom-right footer or a separate green line. The panel deliberately stops before the right-side author/contact column and before the abstract/heading zone to prevent overlap with neighboring text elements.
- Citation panel sizing is standardized: citation text and inline DOI use `\ALIUSFontLatoLight` at 9.2bp with 10.7bp leading; the DOI is wrapped in `\mbox{\textcolor{ALIUSC1F8135}{\href{...}{...}}}` so it remains green, clickable, and unbroken. If a source is regenerated, preserve these rules unless a deliberate edition-wide restyling is requested.
- The Nichols & Nichols Issue 4 citation DOI display intentionally uses the resolving BibTeX DOI `10.34700/a5hm-fs14`, replacing the obsolete/non-resolving original-visible `10.34700/s66k-9j57` in the citation block because the current user request explicitly asked for valid interview DOI links.
- After regenerating interview TeX files, run `python AI-agents/enforce_quote_and_doi_invariants.py`, then `python AI-agents/validate_quote_and_doi_rendering.py`. When issue PDFs are compiled, add `--compiled-dir <build-dir>` to verify live PDF link annotations.
