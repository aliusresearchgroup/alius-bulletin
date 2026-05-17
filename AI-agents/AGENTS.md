# Agent Instructions

These notes are for AI agents working on the `alius-bulletin` Overleaf archive.

## Mission

Maintain an Overleaf-importable source archive where bulletin pieces and issue-level files are reconstructed from editable LaTeX sources rather than pre-existing article PDFs.

## Repository Contract

- Keep top-level folders intentional: `Interviews`, `Bulletins`, `Cover-Art`, `Guidelines`, `Shared-assets`, and `AI-agents`.
- Do not create extra top-level working folders. Put temporary outputs under ignored build folders or outside the repository.
- Each interview or piece folder should contain editable source: one `.tex` and one `.bib` when a bibliography is present.
- Generated PDFs are build outputs, not source of truth, and should not be committed.
- The only tolerated committed PDF asset is `Cover-Art/assets/front-cover-empty-no-leaf.pdf`, because it is the explicit shared cover background resource.
- The canonical cover leaf asset is `Cover-Art/assets/alius-leaf.svg`.
- Do not include published/original article PDFs from `.tex` sources. Original PDFs may be used only outside the build path for temporary human QA.
- Keep QA evidence textual or image-based unless a PDF is explicitly approved as a shared asset resource.

## Editing Rules

- Prefer editing `.tex` and `.bib` sources, then regenerating local PDFs only as ignored build artifacts.
- Do not manually edit generated PDFs as the only source of truth.
- Preserve standalone behavior for individual interview `.tex` files.
- Preserve issue-level compilation through `Bulletins/issueXX.tex` without relying on original article PDFs.
- Use paths that work when the whole repository is imported into Overleaf.
- Keep folder names stable once published because Overleaf, issue files, and manifest paths depend on them.
- Use ASCII in generated source files unless a source file already requires non-ASCII text.
- After any completed repo change, commit and push the newest state to `origin/main` so Overleaf can sync it immediately.
- Keep `AI-agents/formatting-context.md` current whenever formatting, compile-engine, layout, or visual-QA assumptions change.

## LaTeX Workflow

LuaLaTeX is the faithful reconstruction engine because the interview layouts use OpenType fonts through `fontspec`. The repository includes `.latexmkrc` to force Overleaf/latexmk onto LuaLaTeX even if Overleaf's UI is still set to pdfLaTeX.

When checking a single interview faithfully, compile from the repository root:

```powershell
lualatex -interaction=nonstopmode -halt-on-error "Interviews/Issue01/Carhart-Harris_Fortier_Milliere/Carhart-Harris_Fortier_Milliere.tex"
```

Individual interview files also carry a pdfTeX fallback for Overleaf/direct-compile resilience, but pdfLaTeX output is a compatibility path rather than the visual-fidelity target.

When checking a full issue, compile from the repository root through the build script so cover PDFs are generated locally first:

```powershell
.\build-bulletins.ps1 -Issues 01
```

Generated PDFs should remain untracked.

## Visual QA Expectations

- Compare generated PDFs against external references only when needed; do not wire reference PDFs into the TeX build path.
- Check interview titles, quotation placement, parenthetical text, footnotes, and bibliography rendering.
- Treat missing source text, missing shared cover assets, or issue compilation failures as blockers.

## Before Committing

- Run `git status --short --branch`.
- Confirm no accidental build products such as `.aux`, `.log`, `.out`, `.toc`, or generated `.pdf` files are staged.
- Confirm the only staged PDF, if any, is the approved cover background asset.
- Confirm changed interview folders still have editable `.tex` sources and matching `.bib` files when applicable.
- Summarize any visual QA limits honestly in the final note.
