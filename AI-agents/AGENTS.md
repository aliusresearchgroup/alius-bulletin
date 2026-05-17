# Agent Instructions

These notes are for AI agents working on the `alius-bulletin` Overleaf archive.

## Mission

Maintain an Overleaf-importable archive where each bulletin piece has its own folder, source, bibliography, and final rendered PDF, while issue-level files can compile complete bulletin PDFs.

## Repository Contract

- Keep top-level folders intentional: `Interviews`, `Bulletins`, `Cover-Art`, `Guidelines`, `Shared-assets`, and `AI-agents`.
- Do not create extra top-level working folders. Put temporary outputs outside the repository or under an ignored local scratch area if one is later added.
- Each interview or piece folder must contain one `.tex`, one `.bib`, and one final `.pdf`.
- Each issue file in `Bulletins/` should have a matching generated `.pdf`.
- Each cover file in `Cover-Art/` should have a matching generated `.pdf`.
- Keep one-page original cover references under `Cover-Art/reference-covers/`.
- Keep original/source PDFs under `Shared-assets/original-pdfs/`.
- Keep QA evidence under `Shared-assets/qa/`.

## Editing Rules

- Prefer editing `.tex` and `.bib` sources, then regenerating PDFs.
- Do not manually edit generated PDFs as the only source of truth.
- Preserve standalone behavior for individual interview `.tex` files.
- Use paths that work when the whole repository is imported into Overleaf.
- Keep folder names stable once published because Overleaf, issue files, and manifest paths depend on them.
- Use ASCII in generated source files unless a source file already requires non-ASCII text.

## LaTeX Workflow

When checking a single interview, compile from the repository root:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error "Interviews/Issue01/Carhart-Harris_Fortier_Milliere/Carhart-Harris_Fortier_Milliere.tex"
```

When checking a full issue, compile from the repository root:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error "Bulletins/issue01.tex"
```

After compilation, move or confirm the final PDF sits beside the source `.tex` it came from.

## Visual QA Expectations

- Compare generated PDFs against original/source PDFs for page count, page size, and obvious visual drift.
- Check interview titles, quotation placement, parenthetical text, footnotes, and bibliography rendering.
- Treat large layout drift, missing pages, missing included PDFs, or broken issue compilation as blockers.

## Before Committing

- Run `git status --short --branch`.
- Confirm no accidental build products such as `.aux`, `.log`, `.out`, `.toc`, or scratch directories are staged.
- Confirm every changed interview folder still has `.tex`, `.bib`, and `.pdf`.
- Confirm every changed issue has both `.tex` and `.pdf`.
- Summarize any visual QA limits honestly in the final note.
