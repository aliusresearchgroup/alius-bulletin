# Citation Verification Summary

Last sweep: 2026-05-18

## Scope

- Parsed all 41 interview-level BibTeX records under `Interviews/Issue*/*/*.bib`.
- Extracted DOI and URL tokens from all reconstructed interview TeX files.
- Compared extracted DOI/URL tokens against the off-repo original reference PDFs listed in `%TEMP%/alius-original-reference-pdfs/manifest.json`.
- Resolved DOI metadata using DOI content negotiation for ALIUS/Zenodo records and Crossref for ordinary scholarly DOIs.

Command used:

```powershell
python AI-agents\verify_citation_integrity.py --workers 1
```

Detailed CSV outputs are written to the ignored folder `tmp/citation-verification/`.

## Results

- Interview BibTeX library: 41 / 41 DOI records resolve.
- Interview BibTeX title check: 41 / 41 match DOI metadata.
- Interview BibTeX author-list check: 8 warnings, all attributable to DOI metadata policy differences rather than non-resolving citations. Example: some Zenodo records list only the interviewee, while repo BibTeX records include interviewers/editors.
- Full reconstructed-text DOI sweep after adding green first-page interview DOI hyperlinks: 513 unique DOI tokens extracted; 511 resolve; 2 do not resolve as written.
- Original-vs-TeX DOI/URL comparison now intentionally reports deltas because every interview citation block includes a newly added green `https://doi.org/...` hyperlink. These deltas are expected for the revised/corrected citation display requested by the user.
- The Issue 4 Nichols & Nichols citation block now displays the resolving repo BibTeX DOI `10.34700/a5hm-fs14` instead of the obsolete/non-resolving original-visible `10.34700/s66k-9j57`.

## Non-resolving DOI strings still printed in original-visible text

These remain preserved in visible TeX for original-PDF fidelity unless the project intentionally moves from reconstruction to corrected edition for the cited reference itself.

| Printed DOI string | Location | Verification finding |
|---|---|---|
| `10.1007/s13164014-0208-1` | `Interviews/Issue04/Vignemont_Milliere_Serrahima/Vignemont_Milliere_Serrahima.tex` | Does not resolve; likely intended current DOI is `10.1007/s13164-014-0208-1`. |
| `10.17151/culdr.2018.23.25` | `Interviews/Issue03/Winkelman_Fortier/Winkelman_Fortier.tex` | Does not resolve; publisher metadata gives `10.17151/culdr.2018.23.25.3`. |

## Notes for future agents

- Do not treat Crossref title-search mismatches for ALIUS/Zenodo records as proof of a bad ALIUS DOI; use DOI content negotiation / Crosscite for those records.
- Do not silently fix original-visible reference DOI typos if the task is faithful reconstruction. Flag them in QA reports and ask before producing a corrected edition.
- The interview-level DOI display is now an explicit revised-edition invariant: green citation-block `\href` links should match the colocated `.bib` DOI, even if an older original PDF showed a stale DOI.
