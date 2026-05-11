# AI Agent Workspace

This folder is for AI and coding agents maintaining the Overleaf version of the ALIUS Bulletin archive.

The rest of the repository is the deliverable. Keep agent notes, operating assumptions, and maintenance checklists here so the Overleaf project stays understandable without mixing process notes into interview folders.

## What This Repository Contains

- `Interviews/IssueXX/Interview_Names/`: one standalone `.tex`, one `.bib`, and one generated `.pdf` for each interview or bulletin piece.
- `Bulletins/`: issue-level `.tex` files and generated `.pdf` files.
- `Cover-Art/`: standalone cover `.tex` files, generated cover PDFs, and one-page original cover references for Issues 1-7.
- `Instructions/`: ALIUS Bulletin instruction/template sources and rendered PDFs.
- `Shared-assets/`: copied source PDFs, QA logs, visual comparison reports, and the project manifest.
- `AI-agents/`: maintenance guidance for future AI agents.

## Skill Check

Checked on 2026-05-11: no installed Codex skill is specifically dedicated to generating agentic repository documentation.

Closest useful skills:

- `latex-overleaf-writing-ops`: use for LaTeX and Overleaf editing workflows.
- `latex-compile-qa`: use for compile checks, bibliography checks, and LaTeX QA.
- `pdf`: use for PDF rendering and visual inspection tasks.
- `skill-creator`: only relevant if the team wants to create a new reusable Codex skill.
- `agent-survey-corpus`: useful for LLM-agent survey research, not for maintaining this repository.

## First Things To Read

1. `AI-agents/AGENTS.md`
2. `AI-agents/maintenance-checklist.md`
3. `Shared-assets/project-manifest.json`
4. `Shared-assets/qa/visual-fidelity-report.md`

## Regeneration Note

This repository was exported from the website checkout at:

`C:\Users\cogpsy-vrlab\Documents\GitHub\aliusresearch.org`

The current exporter is:

`Bulletin\overleaf\source\scripts\export_flat_overleaf_project.py`

If you regenerate the project, preserve this `AI-agents` folder and verify that `Shared-assets/project-manifest.json` still lists it as a top-level folder.
