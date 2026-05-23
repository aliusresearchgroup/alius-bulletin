# ALIUS Policy Archive

This folder tracks the editable source history for ALIUS internal rules and policy procedures.

The archive is source-first: commit LaTeX and Markdown files here, and keep generated PDFs and original zip files out of Git. The original zip files listed in `source-index.md` are provenance inputs stored outside this repository.

## Folder Layout

- `versions/`: clean policy snapshots intended to represent a full readable version at a point in time.
- `changes/`: tracked-change or proposal documents that show amendments against an earlier version.
- `policy-change-log.md`: human-readable timeline of substantive changes.
- `source-index.md`: mapping from original zip files to extracted repository files, including SHA-256 hashes.

## Naming Rules

Use `YYYY-MM-...` when a date is known from the source filename or supporting context. Use `undated-...` when the source does not identify a reliable date.

Use `versions/` for clean snapshots and `changes/` for documents containing change markup such as `\sout{...}` or `\textcolor{red}{...}`.

## Building Local PDFs

PDFs are build artifacts and should remain untracked. To build one policy document locally from the repository root:

```powershell
New-Item -ItemType Directory -Force -Path tmp/policy-build | Out-Null
pdflatex -interaction=nonstopmode -halt-on-error -output-directory tmp/policy-build -jobname 2025-10-internal-rules "\PassOptionsToPackage{expansion=false}{microtype}\input{ALIUS-Policy/versions/2025-10-internal-rules.tex}"
```

For tracked-change documents, build the matching file under `ALIUS-Policy/changes/`.

The command disables `microtype` font expansion at build time because some MiKTeX installations otherwise fail when using bitmap EC fonts. The source files are left unchanged.

## Current Timeline

The current indexed sequence is:

1. `versions/undated-baseline-internal-rules.tex`
2. `changes/2022-04-changes-from-baseline.tex`
3. `versions/2022-04-internal-rules.tex`
4. `changes/2022-10-changes-from-2022-04.tex`
5. `changes/2024-05-proposed-changes.tex`
6. `versions/2025-10-internal-rules.tex`

Approval status is only recorded when it is explicit in the source or supporting records. In particular, the May 2024 file is treated as a proposal/status-unknown source, and the October 2025 clean snapshot is not assumed to supersede it unless a later decision record confirms that.
