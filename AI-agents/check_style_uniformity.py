#!/usr/bin/env python3
"""Heuristic style-uniformity audit for reconstructed ALIUS interview TeX.

The reconstruction preserves many intentional style changes: question/answer
colour changes, italic journal titles, hyperlinks, running heads, and pull
quotes. This script therefore does not auto-rewrite files. It flags likely
extraction artifacts: raw private-font glyph leaks and isolated span-style
"islands" where the neighbouring text on the same visual line has the same
font/size/colour.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import re
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "tmp" / "style-uniformity"

SPAN_RE = re.compile(
    r"\\ALIUSPlacedTextContent\{([0-9.]+)\}\{([0-9.]+)\}\{([0-9.]+)\}"
    r"\{([^{}]+)\}\{([^{}]+)\}\{([0-9.]+)\}\{(.*?)\}"
)

SUSPICIOUS_CODEPOINTS = {
    *range(0x02B0, 0x0300),  # modifier letters leaked by embedded Word fonts
    *range(0x0600, 0x0A00),  # Arabic/Bengali artifacts seen in Issue 6 extraction
}
INTENTIONAL_INLINE_COLORS = {
    "ALIUSC0000FF",  # hyperlinks in older issues
    "ALIUSC1155CC",  # hyperlinks in later issues
    "ALIUSC1F8135",  # question/interviewer colour
    "ALIUSC767171",  # running-head/footer grey
}


def parse_spans(path: Path) -> list[dict[str, Any]]:
    page = 0
    spans: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        page_match = re.match(r"% Page (\d+)", line)
        if page_match:
            page = int(page_match.group(1))
        match = SPAN_RE.search(line)
        if not match:
            continue
        x, y, w, color, font, size, text = match.groups()
        spans.append(
            {
                "file": path.relative_to(REPO).as_posix(),
                "line": line_no,
                "page": page,
                "x": float(x),
                "y": float(y),
                "w": float(w),
                "color": color,
                "font": font,
                "size": float(size),
                "text": text,
            }
        )
    return spans


def suspicious_glyph_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for span in spans:
        chars = sorted({ch for ch in span["text"] if ord(ch) in SUSPICIOUS_CODEPOINTS})
        if chars:
            rows.append(
                {
                    **{k: span[k] for k in ("file", "line", "page", "x", "y", "font", "size", "color")},
                    "issue": "suspicious-glyph",
                    "text": span["text"],
                    "detail": " ".join(f"U+{ord(ch):04X}" for ch in chars),
                }
            )
    return rows


def style_island_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_file_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        by_file_page[(span["file"], span["page"])].append(span)

    for (_file, _page), page_spans in by_file_page.items():
        visual_lines: list[list[dict[str, Any]]] = []
        for span in sorted(page_spans, key=lambda s: (s["y"], s["x"])):
            if not visual_lines or abs(visual_lines[-1][0]["y"] - span["y"]) > 1.1:
                visual_lines.append([span])
            else:
                visual_lines[-1].append(span)

        for line in visual_lines:
            if len(line) < 3:
                continue
            for prev_span, span, next_span in zip(line, line[1:], line[2:]):
                prev_style = (prev_span["font"], round(prev_span["size"], 2), prev_span["color"])
                style = (span["font"], round(span["size"], 2), span["color"])
                next_style = (next_span["font"], round(next_span["size"], 2), next_span["color"])
                if prev_style != next_style or style == prev_style:
                    continue
                # Normal bibliography/citation typography often italicizes the
                # surrounding title or venue while leaving conjunctions, volume
                # numbers, punctuation, or formula operators roman.
                if (
                    "Italic" in prev_span["font"]
                    and "Italic" in next_span["font"]
                    and "Italic" not in span["font"]
                    and round(prev_span["size"], 2) == round(span["size"], 2) == round(next_span["size"], 2)
                    and prev_span["color"] == span["color"] == next_span["color"]
                ):
                    continue
                text = span["text"].strip()
                if not text or len(text) > 10:
                    continue
                if re.fullmatch(r"[.,;:()\[\]{}0-9\-–—]+", text):
                    continue
                if "Italic" in span["font"] or span["color"] in INTENTIONAL_INLINE_COLORS:
                    continue
                rows.append(
                    {
                        **{k: span[k] for k in ("file", "line", "page", "x", "y", "font", "size", "color")},
                        "issue": "isolated-style-island",
                        "text": text,
                        "detail": f"between {prev_style} spans: {prev_span['text']!r} … {next_span['text']!r}",
                    }
                )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["file", "line", "page", "x", "y", "font", "size", "color", "issue", "text", "detail"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    repo = args.repo.resolve()
    all_spans: list[dict[str, Any]] = []
    for tex in sorted((repo / "Interviews").glob("Issue*/*/*.tex")):
        all_spans.extend(parse_spans(tex))

    rows = suspicious_glyph_rows(all_spans) + style_island_rows(all_spans)
    write_csv(args.out / "style-uniformity-report.csv", rows)
    print(f"spans={len(all_spans)} issues={len(rows)} report={args.out / 'style-uniformity-report.csv'}")
    for row in rows[:25]:
        print(f"{row['file']}:{row['line']} [{row['issue']}] {row['text']!r} {row['detail']}")
    if len(rows) > 25:
        print(f"... {len(rows) - 25} more rows in CSV")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
