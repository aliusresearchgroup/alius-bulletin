#!/usr/bin/env python3
"""Heuristic style-uniformity audit for reconstructed ALIUS interview TeX.

The reconstruction preserves many intentional style changes: question/answer
colour changes, italic journal titles, hyperlinks, running heads, and pull
quotes. This script therefore does not auto-rewrite files. It flags likely
extraction artifacts: raw private-font glyph leaks, isolated span-style
"islands" where neighboring text on the same visual line has the same
font/size/colour, and category-level drift in titles, questions, answers, and
pull quotes.
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
QUESTION_COLOR = "ALIUSC1F8135"
BODY_COLORS = {"ALIUSC000000", "ALIUSC1A1718", "ALIUSC222222"}


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


def row(span: dict[str, Any], issue: str, detail: str, text: str | None = None) -> dict[str, Any]:
    return {
        **{k: span[k] for k in ("file", "line", "page", "x", "y", "font", "size", "color")},
        "issue": issue,
        "text": span["text"] if text is None else text,
        "detail": detail,
    }


def style_key(span: dict[str, Any]) -> tuple[str, float, str]:
    return (span["font"], round(span["size"], 2), span["color"])


def is_link_or_contact_text(text: str) -> bool:
    return bool(re.search(r"https?://|www\.|doi\.org|@|aliusresearch\.org|[A-Za-z0-9-]+\.[A-Za-z]{2,}", text, re.I))


def is_footer_or_running_head(span: dict[str, Any]) -> bool:
    return span["color"] == "ALIUSC767171" or span["y"] > 760 or span["y"] < 45


def is_symbol_fallback_span(span: dict[str, Any]) -> bool:
    return "ALIUSFontSymbolFallback" in span["font"]


def is_body_greek_symbol_fallback(span: dict[str, Any]) -> bool:
    # Some extracted sources carry UTF-8 mojibake for Greek fallback glyphs
    # (`Î²`, `Îº`) while the rendered font still supplies the intended beta/kappa
    # glyph. Treat these one-glyph fallback spans as allowed symbols, not random
    # answer-font drift inside Cormorant prose.
    return span["text"].strip() in {"β", "κ", "Î²", "Îº"} and span["font"] in {
        r"\ALIUSFontCambria",
        r"\ALIUSFontCalibri",
    }


def visual_lines(spans: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    by_file_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for span in spans:
        by_file_page[(span["file"], span["page"])].append(span)

    lines: list[list[dict[str, Any]]] = []
    for (_file, _page), page_spans in by_file_page.items():
        page_lines: list[list[dict[str, Any]]] = []
        for span in sorted(page_spans, key=lambda s: (s["y"], s["x"])):
            if not page_lines or abs(page_lines[-1][0]["y"] - span["y"]) > 1.1:
                page_lines.append([span])
            else:
                page_lines[-1].append(span)
        lines.extend(page_lines)
    return lines


def suspicious_glyph_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for span in spans:
        chars = sorted({ch for ch in span["text"] if ord(ch) in SUSPICIOUS_CODEPOINTS})
        if chars:
            rows.append(row(span, "suspicious-glyph", " ".join(f"U+{ord(ch):04X}" for ch in chars)))
    return rows


def style_island_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in visual_lines(spans):
        if len(line) < 3:
            continue
        for prev_span, span, next_span in zip(line, line[1:], line[2:]):
            prev_style = style_key(prev_span)
            style = style_key(span)
            next_style = style_key(next_span)
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
            rows.append(row(span, "isolated-style-island", f"between {prev_style} spans: {prev_span['text']!r} … {next_span['text']!r}", text))
    return rows


def category_uniformity_rows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in visual_lines(spans):
        line = sorted(line, key=lambda s: s["x"])
        line_text = "".join(span["text"] for span in line).strip()
        if not line_text:
            continue

        # First-page titles/subtitles should stay in black Lato. Smaller author,
        # affiliation, email, and citation fields are intentionally excluded.
        if line[0]["page"] == 1 and 55 <= line[0]["y"] <= 175 and max(span["size"] for span in line) >= 14:
            for span in line:
                if is_link_or_contact_text(span["text"]):
                    continue
                if "ALIUSFontLato" not in span["font"] or span["color"] != "ALIUSC000000":
                    rows.append(row(span, "title-style-drift", "title/subtitle lines should use black Lato-family text", line_text))

        # Interviewer questions are green Lato-family text. Italic Lato emphasis
        # is allowed; Cormorant/Calibri punctuation, symbols, or words inside a
        # green question line are treated as extraction drift.
        q_spans = [
            span
            for span in line
            if span["color"] == QUESTION_COLOR
            and span["size"] >= 10.5
            and not is_footer_or_running_head(span)
            and not is_link_or_contact_text(span["text"])
            and not is_symbol_fallback_span(span)
            and not is_body_greek_symbol_fallback(span)
        ]
        if q_spans:
            lato_q = [span for span in q_spans if "ALIUSFontLato" in span["font"]]
            dominant_size = None
            if lato_q:
                dominant_size = sorted(round(span["size"], 3) for span in lato_q)[len(lato_q) // 2]
            for span in q_spans:
                if "ALIUSFontLato" not in span["font"]:
                    rows.append(row(span, "question-style-drift", "question text should use the green Lato question style", line_text))
                elif dominant_size is not None and abs(span["size"] - dominant_size) > 0.45:
                    rows.append(row(span, "question-size-drift", f"question span size {span['size']:.3f} differs from line median {dominant_size:.3f}", line_text))

        # Pull-quote text is larger Lato text. The oversized decorative quote
        # marks are validated separately and are excluded here.
        pull_spans = [
            span
            for span in line
            if 14.5 <= span["size"] <= 18.0
            and span["color"] in {"ALIUSC000000", "ALIUSC595959", "ALIUSC7F7F7F"}
            and not is_footer_or_running_head(span)
            and span["text"].strip() != "References"
        ]
        if pull_spans and any("ALIUSFontLato" in span["font"] for span in pull_spans):
            lato_sizes = [round(span["size"], 3) for span in pull_spans if "ALIUSFontLato" in span["font"]]
            median_size = sorted(lato_sizes)[len(lato_sizes) // 2]
            for span in pull_spans:
                if "ALIUSFontLato" not in span["font"]:
                    rows.append(row(span, "pullquote-style-drift", "pull-quote text line mixes non-Lato text into a Lato quote", line_text))
                elif abs(span["size"] - median_size) > 0.45:
                    rows.append(row(span, "pullquote-size-drift", f"pull quote span size {span['size']:.3f} differs from line median {median_size:.3f}", line_text))

        # Answer/body lines may use Cormorant regular/medium/italic and link
        # colours. Non-Cormorant material embedded in ordinary black body prose
        # is usually an extraction artifact unless it is a hyperlink/contact.
        body_spans = [
            span
            for span in line
            if span["color"] in BODY_COLORS
            and span["size"] >= 12.0
            and not is_footer_or_running_head(span)
            and not is_link_or_contact_text(span["text"])
            and not is_symbol_fallback_span(span)
            and not is_body_greek_symbol_fallback(span)
        ]
        if body_spans and any("ALIUSFontCormorant" in span["font"] for span in body_spans):
            cormorant = [span for span in body_spans if "ALIUSFontCormorant" in span["font"] and "Italic" not in span["font"]]
            if cormorant:
                median_size = sorted(round(span["size"], 3) for span in cormorant)[len(cormorant) // 2]
                for span in body_spans:
                    if "ALIUSFontCormorant" not in span["font"]:
                        rows.append(row(span, "answer-style-drift", "answer/body line mixes non-Cormorant text into Cormorant prose", line_text))
                    elif "Italic" not in span["font"] and abs(span["size"] - median_size) > 0.55:
                        rows.append(row(span, "answer-size-drift", f"answer span size {span['size']:.3f} differs from line median {median_size:.3f}", line_text))
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

    rows = suspicious_glyph_rows(all_spans) + style_island_rows(all_spans) + category_uniformity_rows(all_spans)
    write_csv(args.out / "style-uniformity-report.csv", rows)
    print(f"spans={len(all_spans)} issues={len(rows)} report={args.out / 'style-uniformity-report.csv'}")
    for finding in rows[:25]:
        print(f"{finding['file']}:{finding['line']} [{finding['issue']}] {finding['text']!r} {finding['detail']}")
    if len(rows) > 25:
        print(f"... {len(rows) - 25} more rows in CSV")
    return 0 if not rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
