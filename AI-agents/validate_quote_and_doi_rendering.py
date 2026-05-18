"""Validate ALIUS pull-quote glyph and interview-DOI display invariants.

Checks current TeX sources for two Overleaf-sensitive details:
- oversized pull-quote placeholders must use TeX macros, never literal question marks;
- every interview must display its own BibTeX DOI on page 1 as a green hyperlinked DOI URL;
- every first-page citation panel must keep citation text top-left and the DOI bottom-right
  without overlapping retained native text spans.

Optionally checks compiled PDFs for live DOI URI annotations.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional compiled-PDF check only
    fitz = None

REPO = Path(__file__).resolve().parents[1]
TEX_GLOB = "Interviews/Issue*/*/*.tex"
SPAN_RE = re.compile(
    r"\\ALIUSPlacedTextContent\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{(?P<text>.*)\}"
)
PANEL_BEGIN = "% ALIUS normalized citation panel begin"
PANEL_END = "% ALIUS normalized citation panel end"
FILL_RE = re.compile(
    r"\\fill\[white\] \((?P<x>[0-9.]+)bp,-(?P<y>[0-9.]+)bp\) rectangle "
    r"\+\+\((?P<w>[0-9.]+)bp,-(?P<h>[0-9.]+)bp\);"
)


def bib_doi(tex_path: Path) -> str:
    bib = tex_path.with_suffix(".bib")
    match = re.search(r"doi\s*=\s*\{([^}]+)\}", bib.read_text(encoding="utf-8"), re.I)
    if not match:
        raise RuntimeError(f"missing DOI in {bib.relative_to(REPO)}")
    return match.group(1).strip()


def source_report() -> dict[str, Any]:
    files = sorted(REPO.glob(TEX_GLOB))
    bad_large_questions: list[str] = []
    missing_quote_macros: list[str] = []
    missing_hyperref: list[str] = []
    bad_doi_lines: list[str] = []
    missing_citation_panels: list[str] = []
    bad_panel_geometry: list[str] = []
    doi_urls: set[str] = set()

    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        if r"\providecommand{\ALIUSPullQuoteOpen}" not in text or r"\providecommand{\ALIUSPullQuoteClose}" not in text:
            missing_quote_macros.append(rel)
        if r"\usepackage[hidelinks]{hyperref}" not in text:
            missing_hyperref.append(rel)

        first_page = text.split(r"\end{tikzpicture}", 1)[0]
        doi = bib_doi(path)
        doi_url = f"https://doi.org/{doi}"
        doi_urls.add(doi_url)
        expected_href = rf"\href{{{doi_url}}}{{{doi_url}}}"
        panel_text = ""
        if PANEL_BEGIN not in first_page:
            missing_citation_panels.append(rel)
        else:
            panel_text = first_page.split(PANEL_BEGIN, 1)[1].split(PANEL_END, 1)[0]

        found_good_doi = False
        panel_box = None
        if panel_text:
            fill_match = FILL_RE.search(panel_text)
            if not fill_match:
                bad_panel_geometry.append(f"{rel}: missing white citation panel box")
            else:
                left = float(fill_match.group("x"))
                top = float(fill_match.group("y"))
                right = left + float(fill_match.group("w"))
                bottom = top + float(fill_match.group("h"))
                panel_box = (left, top, right, bottom)

        for line in first_page.splitlines():
            match = SPAN_RE.search(line)
            if match:
                content = match.group("text")
                x = float(match.group("x"))
                y = float(match.group("y"))
                try:
                    size = float(match.group("size"))
                except ValueError:
                    size = 0.0
                if content == "?" and size >= 30.0:
                    bad_large_questions.append(f"{rel}: {line.strip()}")
                if panel_box is not None:
                    left, top, right, bottom = panel_box
                    if left <= x <= right and top <= y <= bottom:
                        bad_panel_geometry.append(
                            f"{rel}: retained native text inside citation panel at ({x:.1f},{y:.1f}): {content[:60]}"
                        )
            # DOI must be a single TeX line, green, hyperlinked, and aligned to the
            # bottom-right of the normalized citation panel.
            if expected_href in line and "text=ALIUSC1F8135" in line and "anchor=south east" in line:
                found_good_doi = True
        if not found_good_doi:
            bad_doi_lines.append(rel)

    return {
        "tex_files": len(files),
        "unique_expected_doi_urls": len(doi_urls),
        "bad_large_question_spans": bad_large_questions,
        "missing_quote_macros": missing_quote_macros,
        "missing_hyperref": missing_hyperref,
        "missing_citation_panels": missing_citation_panels,
        "bad_panel_geometry": bad_panel_geometry,
        "bad_or_missing_green_doi_hrefs": bad_doi_lines,
        "source_ok": not (
            bad_large_questions
            or missing_quote_macros
            or missing_hyperref
            or missing_citation_panels
            or bad_panel_geometry
            or bad_doi_lines
        ),
    }


def compiled_link_report(compiled_dir: Path) -> dict[str, Any]:
    if fitz is None:
        return {"compiled_check": "skipped: PyMuPDF not importable"}
    expected = {f"https://doi.org/{bib_doi(path)}" for path in REPO.glob(TEX_GLOB)}
    seen: set[str] = set()
    pdfs = sorted(compiled_dir.glob("issue*.pdf"))
    for pdf in pdfs:
        doc = fitz.open(pdf)
        try:
            for page in doc:
                for link in page.get_links():
                    uri = link.get("uri")
                    if uri and uri.startswith("https://doi.org/"):
                        seen.add(uri)
        finally:
            doc.close()
    missing = sorted(expected - seen)
    return {
        "compiled_dir": str(compiled_dir),
        "compiled_issue_pdfs": len(pdfs),
        "expected_doi_links": len(expected),
        "seen_doi_links": len(seen),
        "missing_compiled_doi_links": missing,
        "compiled_links_ok": not missing and len(seen) >= len(expected),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled-dir", type=Path, help="optional directory containing compiled issue*.pdf files")
    args = parser.parse_args()
    report = source_report()
    if args.compiled_dir:
        report.update(compiled_link_report(args.compiled_dir))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("source_ok") and report.get("compiled_links_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
