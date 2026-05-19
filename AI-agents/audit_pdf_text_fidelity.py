#!/usr/bin/env python3
"""Audit rendered interview PDFs against the original ALIUS interview PDFs.

This is a *read-only* reference comparison: it uses original PDFs from an
external checkout when available, but it never copies or relies on them as repo
assets. The generated PDFs are built from the TeX sources into ``tmp/``.

The pass focuses on text fidelity rather than page geometry:

- compile every interview TeX source with LuaLaTeX;
- scan rendered current PDFs for mojibake/tofu/bad inline-spacing markers;
- compare current interview body text against the original per-interview PDF,
  cropping at the first real question so intentionally revised front matter
  (abstracts, APA-7 citation/DOI panels) does not produce false alarms;
- record font/size/color distributions so odd text spans can be inspected.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF


REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "Shared-assets" / "project-manifest.json"
DEFAULT_OUT = REPO / "tmp" / "pdf-text-fidelity"

REFERENCE_ROOT_CANDIDATES = [
    REPO.parents[0]
    / "aliusresearch.org"
    / "site-src"
    / "static"
    / "library"
    / "pdfs"
    / "alius-bulletin",
    REPO.parents[0]
    / "aliusresearch.org"
    / "docs"
    / "library"
    / "pdfs"
    / "alius-bulletin",
]

SPAN_RE = re.compile(
    r"\\ALIUSPlacedTextContent\{(?P<x>[0-9.]+)\}\{(?P<y>[0-9.]+)\}\{(?P<w>[0-9.]+)\}"
    r"\{(?P<color>[^{}]+)\}\{(?P<font>[^{}]+)\}\{(?P<size>[0-9.]+)\}\{(?P<text>.*?)\}"
)
PAGE_RE = re.compile(r"% Page (\d+)")
LINK_RE = re.compile(r"\\(?:ALIUSCitationLink|href)\{[^{}]*\}\{([^{}]*)\}")
COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?")

# Character sequences that should never appear in the current rendered PDFs.
BAD_TEXT_PATTERNS = [
    "Ã",
    "Â",
    "â€",
    "â€“",
    "â€”",
    "â€™",
    "â€œ",
    "â€",
    "�",
    "□",
    "2016PNAS",
    "2016 PNASpaper",
    "PNASpaper",
    "nÂ°",
    "RaphaÃ",
    "MilliÃ",
    "answer/s",  # allowed in Carhart; filtered below because it is original text.
]
ALLOWED_BAD_TEXT_EXCEPTIONS = {
    "answer/s",
}


@dataclass
class Piece:
    issue: str
    slug: str
    tex: Path
    source_basename: str
    doi: str

    @property
    def key(self) -> str:
        return f"{self.issue}/{self.slug}"

    @property
    def output_stem(self) -> str:
        return self.tex.stem


def load_pieces() -> list[Piece]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pieces: list[Piece] = []
    for item in data["pieces"]:
        if item.get("piece_type") != "interview":
            continue
        pieces.append(
            Piece(
                issue=item["issue"],
                slug=item["slug"],
                tex=REPO / item["tex"],
                source_basename=Path(item["source_pdf"]).name,
                doi=item.get("doi", ""),
            )
        )
    return pieces


def resolve_reference_root(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else REFERENCE_ROOT_CANDIDATES
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    tried = "\n".join(str(p) for p in candidates if p)
    raise FileNotFoundError(f"Could not find original PDF reference root. Tried:\n{tried}")


def reference_pdf(piece: Piece, root: Path) -> Path:
    issue_dir = "issue-" + piece.issue[-2:]
    path = root / issue_dir / piece.source_basename
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def plain_tex_text(text: str) -> str:
    text = LINK_RE.sub(r"\1", text)
    text = text.replace(r"\&", "&").replace(r"\%", "%").replace("~", " ")
    text = COMMAND_RE.sub(lambda m: m.group(1) or "", text)
    text = text.replace("{", "").replace("}", "")
    return text


def first_question_from_tex(path: Path) -> str | None:
    page = 0
    rows: list[list[dict[str, Any]]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        page_match = PAGE_RE.match(line)
        if page_match:
            page = int(page_match.group(1))
        match = SPAN_RE.search(line)
        if not match:
            continue
        item = match.groupdict()
        item["page"] = page
        item["x"] = float(item["x"])
        item["y"] = float(item["y"])
        item["size"] = float(item["size"])
        item["text"] = plain_tex_text(item["text"])
        if item["color"] != "ALIUSC1F8135" or item["size"] < 10.5:
            continue
        if not item["text"].strip() or "@" in item["text"] or "doi.org" in item["text"]:
            continue
        if rows and rows[-1][0]["page"] == page and abs(rows[-1][0]["y"] - item["y"]) <= 1.0:
            rows[-1].append(item)
        else:
            rows.append([item])
    for row in rows:
        row = sorted(row, key=lambda x: x["x"])
        text = " ".join(part["text"].strip() for part in row if part["text"].strip())
        text = normalize_text(text)
        if len(text) >= 10 and ("?" in text or text.lower().startswith(("what ", "how ", "can ", "could ", "do ", "does ", "did ", "why "))):
            return text
    return None


def compile_piece(piece: Piece, build_root: Path, reruns: int = 2) -> tuple[Path, str]:
    out_dir = build_root / piece.issue / piece.tex.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"{piece.tex.stem}.pdf"
    log_parts: list[str] = []
    for _ in range(max(1, reruns)):
        cmd = [
            "lualatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={out_dir}",
            str(piece.tex),
        ]
        proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log_parts.append(proc.stdout)
        if proc.returncode != 0:
            tail = "\n".join(proc.stdout.splitlines()[-80:])
            raise RuntimeError(f"LuaLaTeX failed for {piece.key}\n{tail}")
    if not pdf.exists():
        raise FileNotFoundError(f"Expected compiled PDF not found: {pdf}")
    return pdf, "\n".join(log_parts)


def should_skip_line(line: dict[str, Any]) -> bool:
    text = line["text"].strip()
    if not text:
        return True
    y0, y1 = line["bbox"][1], line["bbox"][3]
    page_height = line["page_height"]
    if y1 < 54 or y0 > page_height - 33:
        return True
    if re.fullmatch(r"\d{1,3}", text):
        return True
    if "ALIUS Bulletin" in text or "aliusresearch.org/bulletin" in text:
        return True
    return False


def join_spans(line: dict[str, Any]) -> str:
    parts = sorted(line["spans"], key=lambda span: (span["bbox"][0], span["bbox"][1]))
    out = ""
    prev: dict[str, Any] | None = None
    for span in parts:
        text = span.get("text", "")
        if not text:
            continue
        if prev is not None:
            gap = span["bbox"][0] - prev["bbox"][2]
            left = out[-1:] if out else ""
            right = text[:1]
            if left and right and not left.isspace() and not right.isspace():
                if gap > 1.1 or (gap > -1.8 and re.search(r"[A-Za-z0-9)\]'\u2019]", left) and re.match(r"[A-Za-z0-9('\"\u2018]", right)):
                    out += " "
        out += text
        prev = span
    return out


def extract_lines(pdf: Path, page_numbers: set[int] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    doc = fitz.open(pdf)
    lines: list[dict[str, Any]] = []
    font_counter: Counter[str] = Counter()
    size_counter: Counter[str] = Counter()
    color_counter: Counter[str] = Counter()
    page_count = len(doc)
    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        if page_numbers is not None and page_number not in page_numbers:
            continue
        data = page.get_text("dict")
        page_height = page.rect.height
        for block in data.get("blocks", []):
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if span.get("text")]
                if not spans:
                    continue
                text = join_spans({"spans": spans})
                entry = {
                    "page": page_number,
                    "page_height": page_height,
                    "bbox": line["bbox"],
                    "text": text,
                    "spans": spans,
                }
                if not should_skip_line(entry):
                    lines.append(entry)
                for span in spans:
                    if span.get("text", "").strip():
                        font_counter[span.get("font", "")] += len(span.get("text", ""))
                        size_counter[f"{span.get('size', 0):.2f}"] += len(span.get("text", ""))
                        color_counter[str(span.get("color", ""))] += len(span.get("text", ""))
    summary = {
        "pages": page_count if page_numbers is None else len(page_numbers),
        "fonts": dict(font_counter.most_common(12)),
        "sizes": dict(size_counter.most_common(12)),
        "colors": dict(color_counter.most_common(12)),
    }
    return lines, summary


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00ad", "")
    # Keep apostrophe/quote distinctions mostly intact, but normalize whitespace
    # and repair extraction-only line hyphenation.
    text = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def lines_to_text(lines: list[dict[str, Any]]) -> str:
    return "\n".join(line["text"] for line in sorted(lines, key=lambda x: (x["page"], x["bbox"][1], x["bbox"][0])))


def crop_from_question(text: str, question: str | None) -> tuple[str, bool]:
    norm = normalize_text(text)
    if not question:
        return norm, False
    q = normalize_text(question)
    if len(q) > 80:
        q = q[:80]
    idx = norm.find(q)
    if idx >= 0:
        return norm[idx:], True
    # Try a less brittle token prefix if PDF extraction inserted odd punctuation.
    words = re.findall(r"\w+|[^\w\s]", q, flags=re.UNICODE)
    if len(words) >= 5:
        pattern = r"\s+".join(re.escape(w) for w in words[:8] if w.strip())
        match = re.search(pattern, norm)
        if match:
            return norm[match.start() :], True
    return norm, False


def count_tex_pages(path: Path) -> int:
    pages = [int(m.group(1)) for m in PAGE_RE.finditer(path.read_text(encoding="utf-8", errors="replace"))]
    if not pages:
        raise ValueError(f"No % Page markers found in {path}")
    return max(pages)


def issue_page_ranges(pieces: list[Piece]) -> dict[str, tuple[Path, set[int]]]:
    """Map each piece key to its page range inside the compiled issue PDF.

    Bulletin PDFs include one cover page, then each native interview source in
    manifest/input order. The source ``% Page`` comments are therefore the most
    reliable way to slice current issue PDFs without compiling 41 standalones.
    """

    ranges: dict[str, tuple[Path, set[int]]] = {}
    next_page_by_issue: dict[str, int] = defaultdict(lambda: 2)  # cover is page 1
    for piece in pieces:
        issue_number = piece.issue[-2:]
        issue_pdf = REPO / "Bulletins" / f"issue{issue_number}.pdf"
        page_count = count_tex_pages(piece.tex)
        start = next_page_by_issue[piece.issue]
        pages = set(range(start, start + page_count))
        ranges[piece.key] = (issue_pdf, pages)
        next_page_by_issue[piece.issue] = start + page_count
    return ranges


def suspicious_occurrences(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in BAD_TEXT_PATTERNS:
        if pattern in ALLOWED_BAD_TEXT_EXCEPTIONS:
            continue
        if pattern in text:
            hits.append(pattern)
    return sorted(set(hits))


def compact_diff(a: str, b: str, max_items: int = 5) -> list[dict[str, str]]:
    """Return short human-readable changed chunks: original -> current."""
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    items: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        left = a[max(0, i1 - 80) : min(len(a), i2 + 80)]
        right = b[max(0, j1 - 80) : min(len(b), j2 + 80)]
        items.append(
            {
                "tag": tag,
                "original_context": left,
                "current_context": right,
            }
        )
        if len(items) >= max_items:
            break
    return items


def compare_piece_text(
    piece: Piece,
    ref_pdf: Path,
    current_label: str,
    cur_lines: list[dict[str, Any]],
    cur_fonts: dict[str, Any],
) -> dict[str, Any]:
    ref_lines, ref_fonts = extract_lines(ref_pdf)
    ref_text = lines_to_text(ref_lines)
    cur_text = lines_to_text(cur_lines)
    first_question = first_question_from_tex(piece.tex)
    ref_body, ref_cropped = crop_from_question(ref_text, first_question)
    cur_body, cur_cropped = crop_from_question(cur_text, first_question)
    ratio = difflib.SequenceMatcher(a=ref_body, b=cur_body, autojunk=False).ratio() if ref_body and cur_body else 0.0
    suspicious = suspicious_occurrences(cur_text)
    report = {
        "key": piece.key,
        "tex": str(piece.tex.relative_to(REPO)),
        "reference_pdf": str(ref_pdf),
        "current_pdf": current_label,
        "doi": piece.doi,
        "reference_pages": ref_fonts["pages"],
        "current_pages": cur_fonts["pages"],
        "first_question": first_question,
        "cropped_at_first_question": bool(ref_cropped and cur_cropped),
        "body_similarity": round(ratio, 6),
        "reference_chars": len(ref_body),
        "current_chars": len(cur_body),
        "char_delta": len(cur_body) - len(ref_body),
        "suspicious_current_text": suspicious,
        "font_summary_reference": ref_fonts,
        "font_summary_current": cur_fonts,
        "diff_samples": compact_diff(ref_body, cur_body) if ratio < 0.999 else [],
        "ok": (not suspicious) and ratio >= 0.985 and bool(ref_cropped and cur_cropped),
    }
    return report


def audit_piece(piece: Piece, ref_root: Path, build_root: Path, compile_current: bool, current_root: Path | None) -> dict[str, Any]:
    ref_pdf = reference_pdf(piece, ref_root)
    if compile_current:
        current_pdf, _log = compile_piece(piece, build_root)
    else:
        if current_root is None:
            raise ValueError("--skip-compile requires --current-root")
        current_pdf = current_root / piece.issue / piece.tex.parent.name / f"{piece.tex.stem}.pdf"
        if not current_pdf.exists():
            raise FileNotFoundError(current_pdf)

    cur_lines, cur_fonts = extract_lines(current_pdf)
    current_label = str(current_pdf.relative_to(REPO) if current_pdf.is_relative_to(REPO) else current_pdf)
    return compare_piece_text(piece, ref_pdf, current_label, cur_lines, cur_fonts)


def write_reports(reports: list[dict[str, Any]], out_dir: Path, failures: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "pieces": len(reports),
        "ok_pieces": sum(1 for r in reports if r.get("ok")),
        "suspicious_pieces": sum(1 for r in reports if r.get("suspicious_current_text")),
        "low_similarity_pieces": sum(1 for r in reports if r.get("body_similarity", 0) < 0.985),
        "failures": failures,
        "reports": reports,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "key",
                "body_similarity",
                "char_delta",
                "reference_pages",
                "current_pages",
                "cropped_at_first_question",
                "suspicious_current_text",
                "ok",
            ],
        )
        writer.writeheader()
        for item in reports:
            writer.writerow(
                {
                    "key": item.get("key"),
                    "body_similarity": item.get("body_similarity"),
                    "char_delta": item.get("char_delta"),
                    "reference_pages": item.get("reference_pages"),
                    "current_pages": item.get("current_pages"),
                    "cropped_at_first_question": item.get("cropped_at_first_question"),
                    "suspicious_current_text": ";".join(item.get("suspicious_current_text", [])),
                    "ok": item.get("ok"),
                }
            )

    md: list[str] = [
        "# ALIUS PDF text-fidelity audit",
        "",
        "The current PDFs are rendered from TeX into `tmp/`; original PDFs are read from an external checkout and are not committed as assets.",
        "Body comparison is cropped at the first interview question so added abstracts and APA-7 citation/DOI front matter are treated as intentional editorial additions.",
        "",
        f"- Pieces audited: {len(reports)}",
        f"- Pieces passing the body-text/suspicious-character gate: {summary['ok_pieces']}",
        f"- Pieces with suspicious current text markers: {summary['suspicious_pieces']}",
        f"- Pieces below similarity threshold: {summary['low_similarity_pieces']}",
    ]
    if failures:
        md.extend(["", "## Failures", ""])
        md.extend(f"- {failure}" for failure in failures)
    issues = [r for r in reports if not r.get("ok")]
    if issues:
        md.extend(["", "## Pieces needing manual review", ""])
        for item in issues:
            md.append(
                f"### {item['key']} — similarity {item['body_similarity']}, char delta {item['char_delta']}, suspicious={item['suspicious_current_text'] or 'none'}"
            )
            if item.get("diff_samples"):
                for diff in item["diff_samples"][:3]:
                    md.append(f"- `{diff['tag']}`")
                    md.append(f"  - original: {diff['original_context'][:240]}")
                    md.append(f"  - current: {diff['current_context'][:240]}")
    (out_dir / "manual-review.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, default=None, help="External root containing issue-XX original PDFs")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Compile each interview standalone into tmp/current-pdfs. Default is to slice already-built Bulletins/issueXX.pdf files.",
    )
    parser.add_argument("--skip-compile", action="store_true", help="Standalone mode only: reuse PDFs under --current-root instead of compiling")
    parser.add_argument("--current-root", type=Path, default=None)
    parser.add_argument("--limit", nargs="*", help="Optional slugs or IssueXX/slug keys to audit")
    parser.add_argument("--keep-build", action="store_true", help="Do not delete previous tmp/current-pdfs before compiling")
    args = parser.parse_args()

    ref_root = resolve_reference_root(args.reference_root)
    build_root = args.out_dir / "current-pdfs"
    if args.standalone and not args.skip_compile and build_root.exists() and not args.keep_build:
        shutil.rmtree(build_root)
    all_pieces = load_pieces()
    pieces = all_pieces
    if args.limit:
        wanted = set(args.limit)
        pieces = [p for p in pieces if p.slug in wanted or p.key in wanted or p.tex.stem in wanted]
    failures: list[str] = []
    reports: list[dict[str, Any]] = []
    if args.standalone:
        for idx, piece in enumerate(pieces, start=1):
            print(f"[{idx}/{len(pieces)}] {piece.key}", flush=True)
            try:
                reports.append(audit_piece(piece, ref_root, build_root, not args.skip_compile, args.current_root))
            except Exception as exc:  # keep going; one malformed PDF should not hide other results
                failures.append(f"{piece.key}: {type(exc).__name__}: {exc}")
                print(f"  ! {failures[-1]}", file=sys.stderr, flush=True)
    else:
        ranges = issue_page_ranges(all_pieces)
        for idx, piece in enumerate(pieces, start=1):
            print(f"[{idx}/{len(pieces)}] {piece.key}", flush=True)
            try:
                ref_pdf = reference_pdf(piece, ref_root)
                issue_pdf, pages = ranges[piece.key]
                if not issue_pdf.exists():
                    raise FileNotFoundError(f"Missing built issue PDF: {issue_pdf}; run ./build-bulletins.ps1 first")
                cur_lines, cur_fonts = extract_lines(issue_pdf, pages)
                label = f"{issue_pdf.relative_to(REPO)} pages {min(pages)}-{max(pages)}"
                reports.append(compare_piece_text(piece, ref_pdf, label, cur_lines, cur_fonts))
            except Exception as exc:
                failures.append(f"{piece.key}: {type(exc).__name__}: {exc}")
                print(f"  ! {failures[-1]}", file=sys.stderr, flush=True)
    write_reports(reports, args.out_dir, failures)
    print(f"wrote {args.out_dir / 'summary.json'}")
    print(f"wrote {args.out_dir / 'manual-review.md'}")
    if failures:
        return 2
    bad = [r for r in reports if r.get("suspicious_current_text")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
