#!/usr/bin/env python3
"""Normalize visible prose quotation marks in reconstructed interview TeX.

The original ALIUS PDFs were produced from word-processor typography and use
curly apostrophes/quotation marks in interview prose. Early text reconstruction
passes flattened many of those characters to ASCII. This source-level pass
restores typographic quotes inside visible ``\\ALIUSPlacedTextContent`` spans,
without touching paths, URLs, emails, DOI strings, or TeX command names.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[1]
TEX_GLOB = "Interviews/Issue*/*/*.tex"
SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{[^}]*\}\{[^}]*\}\{[^}]*\}"
    r"\{[^}]*\}\{[^}]*\}\{[^}]*\}\{)(?P<text>.*)(?P<suffix>\}\s*)$"
)

PDFTEX_FALLBACK_SENTINEL = r"\DeclareUnicodeCharacter{2019}{'}%"
PDFTEX_FALLBACK_INSERT_AFTER = r"\DeclareUnicodeCharacter{201D}{''}%"
PDFTEX_FALLBACK_BLOCK = (
    r"\DeclareUnicodeCharacter{2018}{`}%"
    "\n"
    r"    \DeclareUnicodeCharacter{2019}{'}%"
)


def previous_raw(text: str, index: int) -> str:
    return text[index - 1] if index > 0 else ""


def next_raw(text: str, index: int) -> str:
    return text[index + 1] if index + 1 < len(text) else ""


def is_open_context(ch: str) -> bool:
    return not ch or ch.isspace() or ch in "([{/<–—-~"


def smarten_text(text: str, *, double_open: bool, single_open: bool) -> tuple[str, bool, bool]:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        prev = previous_raw(text, i)
        nxt = next_raw(text, i)

        # Copy TeX command names as names. Their brace arguments remain visible
        # text and are processed normally.
        if ch == "\\" and i + 1 < len(text) and text[i + 1].isalpha():
            j = i + 2
            while j < len(text) and text[j].isalpha():
                j += 1
            out.append(text[i:j])
            i = j
            continue

        if ch == "'":
            if (prev.isalnum() or prev in ")]") and (nxt.isalnum() or nxt in "’"):
                out.append("’")
            elif (nxt.isalnum() or nxt in "([{") and single_open:
                out.append("‘")
                single_open = False
            elif (nxt.isalnum() or nxt in "([{") and is_open_context(prev):
                out.append("‘")
            else:
                out.append("’")
                single_open = True
            i += 1
            continue

        if ch == '"':
            if double_open or (is_open_context(prev) and (nxt.isalnum() or nxt in "([{‘“")):
                out.append("“")
                double_open = False
            else:
                out.append("”")
                double_open = True
            i += 1
            continue

        out.append(ch)
        i += 1
    fixed = "".join(out)
    # When a quotation mark is split across PDF extraction spans, the closing
    # mark can be encountered in a new span with little context. These patterns
    # are never valid openings in the bulletin prose.
    fixed = re.sub(r"(?<=[A-Za-z0-9\]\)’”\.])“(?=[,\.\)\s])", "”", fixed)
    fixed = re.sub(r"(?<=~)“(?=[,\.\)\s])", "”", fixed)
    fixed = re.sub(r"(^|~)’(?=[A-Za-z][^{}]*’)", r"\1‘", fixed)
    return fixed, double_open, single_open


def should_skip_span_text(text: str) -> bool:
    plain = text.strip()
    if not plain:
        return True
    if any(marker in plain for marker in ("http://", "https://", "doi.org", "@")):
        return True
    return False


def process_file(path: Path, write: bool) -> dict[str, object]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changes: list[dict[str, object]] = []
    out_lines = lines[:]
    double_open = True
    single_open = True
    for idx, line in enumerate(lines):
        match = SPAN_RE.match(line)
        if not match:
            continue
        text = match.group("text")
        if should_skip_span_text(text):
            continue
        fixed, double_open, single_open = smarten_text(
            text, double_open=double_open, single_open=single_open
        )
        if fixed != text:
            out_lines[idx] = f"{match.group('prefix')}{fixed}{match.group('suffix')}"
            changes.append({"line": idx + 1, "before": text[:120], "after": fixed[:120]})

    new_text = "".join(out_lines)
    if PDFTEX_FALLBACK_SENTINEL not in new_text and PDFTEX_FALLBACK_INSERT_AFTER in new_text:
        new_text = new_text.replace(
            PDFTEX_FALLBACK_INSERT_AFTER,
            PDFTEX_FALLBACK_INSERT_AFTER + "\n    " + PDFTEX_FALLBACK_BLOCK,
            1,
        )

    changed = new_text != original
    if write and changed:
        path.write_text(new_text, encoding="utf-8", newline="")
    return {
        "file": path.relative_to(REPO).as_posix(),
        "changed": changed,
        "span_changes": len(changes),
        "examples": changes[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without writing")
    parser.add_argument("--report", type=Path, default=REPO / "tmp" / "smart-quotes-report.json")
    args = parser.parse_args()

    reports = [process_file(path, write=not args.check) for path in sorted(REPO.glob(TEX_GLOB))]
    changed = [item for item in reports if item["changed"]]
    report = {
        "tex_files": len(reports),
        "changed_files": len(changed),
        "span_changes": sum(int(item["span_changes"]) for item in reports),
        "files": reports,
        "ok": not changed if args.check else True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
