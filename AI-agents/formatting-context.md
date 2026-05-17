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
- New abstracts currently stay commented out in the relevant interview `.tex` files unless the user asks to render them.
- Issue wrappers under `Bulletins/issueXX.tex` should compile from the repository root and input native interview sources.

## Operational rule

When work is done, push the newest committed state to `origin/main` so the user can sync Overleaf immediately. Keep the remote branch set minimal unless the user asks for PR-style branching.
