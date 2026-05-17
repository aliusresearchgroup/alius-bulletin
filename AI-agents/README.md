# ALIUS Bulletin AI-Agent Notes

This repository is a source-first reconstruction archive. The goal is to rebuild bulletin pieces and issue PDFs from editable LaTeX, not to wrap or re-include already published article PDFs.

## Directory roles

- `Interviews/IssueXX/.../`: standalone LaTeX source for each interview or bulletin piece, with a `.bib` file when applicable.
- `Bulletins/`: issue-level LaTeX files that assemble native piece sources.
- `Cover-Art/`: cover sources and the only approved committed PDF asset, `assets/front-cover-empty-no-leaf.pdf`.
- `Shared-assets/`: metadata and non-build-path shared data.
- `AI-agents/`: maintenance notes for future agents.

Generated PDFs are local build artifacts and should stay untracked. The canonical cover leaf is `Cover-Art/assets/alius-leaf.svg`; the cover background PDF is tolerated only because it is explicitly the shared cover artwork substrate.

For current formatting and compile-engine assumptions, read `AI-agents/formatting-context.md` before changing layout code. After completing repo work, commit and push `main` so Overleaf can sync the newest version.
