r"""Make in-text author-year citations clickable to their reference entries.

The ALIUS interview reconstructions are absolute-positioned native TeX, not
BibTeX-driven prose. This script therefore works at the generated TeX layer:

- find the visible References section in each interview source;
- add an invisible ``\ALIUSRefAnchor{...}`` at each parsed reference entry;
- wrap matching in-text author-year strings with ``\ALIUSCitationLink{...}{...}``.

It is intentionally conservative: ambiguous same-file author/year patterns are
left untouched rather than linked to the wrong bibliography entry. Hyperlinks
are hidden by the existing ``hyperref[hidelinks]`` setup, so successful edits
should not change the visible reconstruction.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - compiled-PDF check is optional
    fitz = None

REPO = Path(__file__).resolve().parents[1]
TEX_GLOB = "Interviews/Issue*/*/*.tex"

SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{)(?P<text>.*)(?P<suffix>\}\s*)$"
)


@dataclass
class Span:
    idx: int
    line_no: int
    page: int
    prefix: str
    suffix: str
    x: float
    y: float
    width: float
    color: str
    font: str
    size: float
    text: str


@dataclass
class ReferenceEntry:
    anchor: str
    first_span_idx: int
    text: str
    year: str
    surnames: list[str]
    patterns: set[str] = field(default_factory=set)


def parse_spans(lines: list[str]) -> list[Span]:
    page = 0
    spans: list[Span] = []
    for idx, line in enumerate(lines):
        page_match = re.match(r"% Page (\d+)", line)
        if page_match:
            page = int(page_match.group(1))
            continue
        match = SPAN_RE.match(line)
        if not match:
            continue
        groups = match.groupdict()
        spans.append(
            Span(
                idx=idx,
                line_no=idx + 1,
                page=page,
                prefix=groups["prefix"],
                suffix=groups["suffix"],
                x=float(groups["x"]),
                y=float(groups["y"]),
                width=float(groups["w"]),
                color=groups["color"],
                font=groups["font"],
                size=float(groups["size"]),
                text=groups["text"],
            )
        )
    return spans


def strip_link_macros(text: str) -> str:
    """Return the visible payload of already-linked text for parsing."""
    text = re.sub(r"\\ALIUSRefAnchor\{[^{}]*\}", "", text)
    # Current citation payloads do not contain nested braces; keep the parser
    # narrow so it cannot damage arbitrary TeX.
    changed = True
    while changed:
        new = re.sub(r"\\ALIUSCitationLink\{[^{}]*\}\{([^{}]*)\}", r"\1", text)
        changed = new != text
        text = new
    return text


def unwrap_citation_links(text: str) -> str:
    """Remove existing citation-link wrappers while preserving visible text."""
    changed = True
    while changed:
        new = re.sub(r"\\ALIUSCitationLink\{[^{}]*\}\{([^{}]*)\}", r"\1", text)
        changed = new != text
        text = new
    return text


def unwrap_citation_links_in_lines(lines: list[str]) -> int:
    changed = 0
    for i, line in enumerate(lines):
        if r"\ALIUSCitationLink{" not in line:
            continue
        new = unwrap_citation_links(line)
        if new != line:
            lines[i] = new
            changed += 1
    return changed


def plainish(text: str) -> str:
    text = strip_link_macros(text)
    replacements = {
        r"\&": "&",
        r"\textendash": "-",
        r"\textemdash": "-",
        r"\textquotedblleft": '"',
        r"\textquotedblright": '"',
        r"\textquotesingle": "'",
        r"\'": "",
        r"\`": "",
        r"\~": "",
        r"\=": "",
        r"\^": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\\[A-Za-z]+\*?", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify(value: str) -> str:
    value = plainish(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "ref"


def find_references_heading(spans: list[Span]) -> Span | None:
    for span in spans:
        if plainish(span.text).strip().lower() == "references":
            return span
    return None


def eligible_reference_span(span: Span, heading: Span) -> bool:
    if span.idx <= heading.idx:
        return False
    if span.page == heading.page and span.y <= heading.y + 5:
        return False
    if span.y < 45 or span.y > 755:
        return False
    if span.color == "ALIUSC767171":
        return False
    if span.size < 10.0:
        return False
    if "Cormorant" not in span.font and "Times" not in span.font:
        return False
    text = plainish(span.text)
    if not text or text.lower().startswith("alius bulletin"):
        return False
    return True


def starts_reference_entry(span: Span, left_margin: float) -> bool:
    if span.x > left_margin + 8.5:
        return False
    text = plainish(span.text)
    # APA-style entries begin with a surname or named author followed by a
    # comma before initials. This keeps hanging-indent continuations out.
    return bool(re.match(r"^[A-Za-zÀ-ÖØ-öø-ÿ'’.\- ]{2,90},\s+", text))


def parse_year(text: str) -> str | None:
    # Prefer the publication year in parentheses near the author block. Accept
    # suffixes such as 2017a if they appear in the visible bibliography.
    match = re.search(r"\((\d{4}[a-z]?)", text)
    if match:
        return match.group(1)
    # Some original bulletin reference lists are not APA-styled and use
    # "Surname, I. 2017." rather than "(2017)." In that case the first 18xx,
    # 19xx, or 20xx token is normally the publication year.
    match = re.search(r"\b((?:18|19|20)\d{2}[a-z]?)\b", text)
    if match:
        return match.group(1)
    return None


def parse_surnames(reference_text: str, year: str) -> list[str]:
    year_at = reference_text.find(f"({year}")
    if year_at < 0:
        year_match = re.search(rf"\b{re.escape(year)}\b", reference_text)
        year_at = year_match.start() if year_match else -1
    author_part = reference_text[:year_at] if year_at >= 0 else reference_text
    author_part = re.sub(r"\s+", " ", author_part).strip()
    surnames: list[str] = []
    # Matches APA author fragments: "Surname, A.", ", & Surname, A.",
    for match in re.finditer(r"(?:^|,\s+(?:&\s+)?)\s*([^,]+?),\s+[A-ZÀ-ÖØ-Þ]\.", author_part):
        surname = match.group(1).strip()
        surname = re.sub(r"^(?:and|&)\s+", "", surname).strip()
        if surname and surname not in surnames:
            surnames.append(surname)
    # Matches non-inverted later authors in lists such as
    # "Raballo, A., D. Sæbye, and J. Parnas. 2009."
    for match in re.finditer(r"(?:,|\band\b)\s+(?:[A-ZÀ-ÖØ-Þ]\.\s*)+([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]+)", author_part):
        surname = match.group(1).strip()
        if surname and surname not in surnames:
            surnames.append(surname)
    if not surnames and "," in author_part:
        surnames.append(author_part.split(",", 1)[0].strip())
    return surnames


def make_patterns(surnames: list[str], year: str) -> set[str]:
    if not surnames:
        return set()
    first = surnames[0]
    patterns: set[str] = set()
    if len(surnames) == 1:
        patterns.add(f"{first}, {year}")
        patterns.add(f"{first} ({year})")
    elif len(surnames) == 2:
        second = surnames[1]
        patterns.update(
            {
                rf"{first} \& {second}, {year}",
                f"{first} & {second}, {year}",
                f"{first} and {second}, {year}",
                rf"{first} \& {second} ({year})",
                f"{first} & {second} ({year})",
                f"{first} and {second} ({year})",
            }
        )
    else:
        patterns.update(
            {
                f"{first} et al., {year}",
                f"{first} et al. {year}",
                f"{first} et al. ({year})",
            }
        )
    # Some interviews use "Author, Year" even for multi-author entries when the
    # prose has introduced the collaborator list nearby; keep this pattern only
    # if it proves unambiguous within the file.
    patterns.add(f"{first}, {year}")
    return {p for p in patterns if p.strip()}


def extract_reference_entries(path: Path, spans: list[Span]) -> tuple[list[ReferenceEntry], dict[str, Any]]:
    heading = find_references_heading(spans)
    if not heading:
        return [], {"missing_references_heading": True}

    ref_spans = [span for span in spans if eligible_reference_span(span, heading)]
    if not ref_spans:
        return [], {"missing_reference_spans": True}

    left_margin = min(span.x for span in ref_spans)
    groups: list[list[Span]] = []
    current: list[Span] = []
    for span in ref_spans:
        if starts_reference_entry(span, left_margin):
            if current:
                groups.append(current)
            current = [span]
        elif current:
            current.append(span)
    if current:
        groups.append(current)

    entries: list[ReferenceEntry] = []
    used_anchors: dict[str, int] = {}
    file_slug = slugify(path.stem)
    skipped_no_year = 0
    skipped_no_author = 0
    for group in groups:
        combined = " ".join(plainish(span.text) for span in group)
        year = parse_year(combined)
        if not year:
            skipped_no_year += 1
            continue
        surnames = parse_surnames(combined, year)
        if not surnames:
            skipped_no_author += 1
            continue
        existing_anchor = re.search(r"\\ALIUSRefAnchor\{([^{}]+)\}", group[0].text)
        if existing_anchor:
            anchor = existing_anchor.group(1)
        else:
            ref_slug = "-".join(slugify(s) for s in surnames[:2])
            base = f"aliusref-{file_slug}-{ref_slug}-{slugify(year)}"
            ordinal = used_anchors.get(base, 0) + 1
            used_anchors[base] = ordinal
            anchor = base if ordinal == 1 else f"{base}-{ordinal}"
        entry = ReferenceEntry(
            anchor=anchor,
            first_span_idx=group[0].idx,
            text=combined,
            year=year,
            surnames=surnames,
        )
        entry.patterns = make_patterns(surnames, year)
        entries.append(entry)

    return entries, {
        "references_heading_line": heading.line_no,
        "reference_entry_groups": len(groups),
        "parsed_reference_entries": len(entries),
        "skipped_reference_entries_no_year": skipped_no_year,
        "skipped_reference_entries_no_author": skipped_no_author,
    }


def add_reference_anchors(lines: list[str], entries: list[ReferenceEntry]) -> int:
    added = 0
    for entry in entries:
        idx = entry.first_span_idx
        if r"\ALIUSRefAnchor{" in lines[idx]:
            continue
        match = SPAN_RE.match(lines[idx])
        if not match:
            continue
        lines[idx] = f"{match.group('prefix')}\\ALIUSRefAnchor{{{entry.anchor}}}{match.group('text')}{match.group('suffix')}"
        added += 1
    return added


def citation_pattern_map(entries: list[ReferenceEntry]) -> tuple[dict[str, str], dict[str, list[str]]]:
    candidates: dict[str, list[str]] = {}
    for entry in entries:
        for pattern in entry.patterns:
            candidates.setdefault(pattern, []).append(entry.anchor)
    unique: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for pattern, anchors in candidates.items():
        deduped = sorted(set(anchors))
        if len(deduped) == 1:
            unique[pattern] = deduped[0]
        else:
            ambiguous[pattern] = deduped
    return unique, ambiguous


def should_link_span(span: Span, references_heading: Span | None) -> bool:
    if references_heading and span.idx >= references_heading.idx:
        return False
    if r"\ALIUSCitationLink{" in span.text:
        return False
    if r"\ALIUSRefAnchor{" in span.text:
        return False
    if "http" in span.text or "doi.org" in span.text:
        return False
    if "Citation:" in span.text or re.search(r"Cite\s+as:", span.text, re.I):
        return False
    if span.y > 760 or span.size < 8:
        return False
    return True


def wrap_citations_in_text(text: str, pattern_to_anchor: dict[str, str]) -> tuple[str, int]:
    if not pattern_to_anchor:
        return text, 0
    # Longest first prevents "Author, 2017" from stealing part of an
    # "Author and Coauthor, 2017" citation.
    patterns = sorted(pattern_to_anchor, key=len, reverse=True)
    selected: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []
    for pattern in patterns:
        start = 0
        while True:
            pos = text.find(pattern, start)
            if pos < 0:
                break
            end = pos + len(pattern)
            if not any(pos < occ_end and end > occ_start for occ_start, occ_end in occupied):
                selected.append((pos, end, pattern, pattern_to_anchor[pattern]))
                occupied.append((pos, end))
            start = pos + 1
    if not selected:
        return text, 0
    selected.sort(key=lambda item: item[0])
    out: list[str] = []
    cursor = 0
    for start, end, pattern, anchor in selected:
        out.append(text[cursor:start])
        out.append(rf"\ALIUSCitationLink{{{anchor}}}{{{pattern}}}")
        cursor = end
    out.append(text[cursor:])
    return "".join(out), len(selected)


def add_in_text_links(lines: list[str], spans: list[Span], entries: list[ReferenceEntry]) -> tuple[int, dict[str, Any]]:
    references_heading = find_references_heading(spans)
    pattern_to_anchor, ambiguous = citation_pattern_map(entries)
    links_added = 0
    linked_patterns: dict[str, int] = {}
    for span in spans:
        if not should_link_span(span, references_heading):
            continue
        new_text, count = wrap_citations_in_text(span.text, pattern_to_anchor)
        if count == 0 or new_text == span.text:
            continue
        match = SPAN_RE.match(lines[span.idx])
        if not match:
            continue
        lines[span.idx] = f"{match.group('prefix')}{new_text}{match.group('suffix')}"
        links_added += count
        for pattern in pattern_to_anchor:
            if pattern in span.text:
                linked_patterns[pattern] = linked_patterns.get(pattern, 0) + span.text.count(pattern)
    return links_added, {
        "unique_citation_patterns": len(pattern_to_anchor),
        "ambiguous_citation_patterns": {k: v for k, v in sorted(ambiguous.items())},
        "linked_patterns": dict(sorted(linked_patterns.items())),
    }


def validate_links(text: str) -> dict[str, Any]:
    anchors = re.findall(r"\\ALIUSRefAnchor\{([^{}]+)\}", text)
    links = re.findall(r"\\ALIUSCitationLink\{([^{}]+)\}\{", text)
    duplicate_anchors = sorted({anchor for anchor in anchors if anchors.count(anchor) > 1})
    missing_targets = sorted(set(links) - set(anchors))
    return {
        "anchors": len(anchors),
        "citation_links": len(links),
        "duplicate_anchors": duplicate_anchors,
        "missing_link_targets": missing_targets,
        "ok": not duplicate_anchors and not missing_targets,
    }


def process_file(path: Path, write: bool = True) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    unwrapped_lines = unwrap_citation_links_in_lines(lines)
    spans = parse_spans(lines)
    entries, ref_report = extract_reference_entries(path, spans)

    anchors_added = 0
    links_added = 0
    link_report: dict[str, Any] = {}
    if entries:
        anchors_added = add_reference_anchors(lines, entries)
        # Reparse after anchor insertion so line content is current before links.
        spans_after_anchors = parse_spans(lines)
        links_added, link_report = add_in_text_links(lines, spans_after_anchors, entries)

    new_text = "".join(lines)
    validation = validate_links(new_text)
    if write and new_text != original:
        path.write_text(new_text, encoding="utf-8", newline="")

    return {
        "file": path.relative_to(REPO).as_posix(),
        **ref_report,
        "anchors_added": anchors_added,
        "links_added": links_added,
        "citation_link_lines_refreshed": unwrapped_lines,
        **link_report,
        "validation": validation,
        "changed": new_text != original,
    }


def compiled_validation_report(compiled_dir: Path, expected_named_links: int) -> dict[str, Any]:
    if fitz is None:
        return {"compiled_check": "skipped: PyMuPDF not importable", "compiled_ok": True}
    pdfs = sorted(compiled_dir.glob("issue*.pdf"))
    pdf_report = []
    total_named = 0
    for pdf in pdfs:
        doc = fitz.open(pdf)
        named = 0
        uri = 0
        try:
            for page in doc:
                for link in page.get_links():
                    if link.get("uri"):
                        uri += 1
                    elif link.get("kind") == fitz.LINK_NAMED:
                        named += 1
        finally:
            doc.close()
        total_named += named
        pdf_report.append({"pdf": pdf.name, "named_internal_links": named, "uri_links": uri})
    return {
        "compiled_dir": str(compiled_dir),
        "compiled_issue_pdfs": len(pdfs),
        "expected_source_citation_links": expected_named_links,
        "seen_named_internal_links": total_named,
        "pdfs": pdf_report,
        "compiled_ok": total_named >= expected_named_links,
    }


def source_validation_report(files: list[Path], compiled_dir: Path | None = None) -> dict[str, Any]:
    per_file = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        per_file.append({"file": path.relative_to(REPO).as_posix(), **validate_links(text)})
    bad = [item for item in per_file if not item["ok"]]
    report = {
        "tex_files": len(files),
        "total_anchors": sum(item["anchors"] for item in per_file),
        "total_citation_links": sum(item["citation_links"] for item in per_file),
        "bad_files": bad,
        "ok": not bad,
    }
    if compiled_dir:
        compiled = compiled_validation_report(compiled_dir, report["total_citation_links"])
        report.update(compiled)
        report["ok"] = report["ok"] and compiled.get("compiled_ok", True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate existing links without modifying files")
    parser.add_argument("--dry-run", action="store_true", help="report planned changes without writing")
    parser.add_argument("--compiled-dir", type=Path, help="optional directory containing compiled issue*.pdf files")
    parser.add_argument("--report", type=Path, default=REPO / "tmp" / "citation-linking-report.json")
    args = parser.parse_args()

    files = sorted(REPO.glob(TEX_GLOB))
    if args.check:
        report = source_validation_report(files, args.compiled_dir)
    else:
        per_file = [process_file(path, write=not args.dry_run) for path in files]
        report = {
            "tex_files": len(files),
            "changed_files": sum(1 for item in per_file if item["changed"]),
            "anchors_added": sum(item["anchors_added"] for item in per_file),
            "links_added": sum(item["links_added"] for item in per_file),
            "files": per_file,
            "ok": all(item["validation"]["ok"] for item in per_file),
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
