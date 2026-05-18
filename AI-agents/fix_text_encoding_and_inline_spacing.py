"""Repair ALIUS interview text encoding and inline-style word spacing.

The reconstructed interview sources are absolute-positioned TikZ text spans.
Two extraction artifacts can survive into otherwise valid TeX:

- UTF-8 punctuation/names decoded as Windows-1252 mojibake, e.g. ``â€“`` or
  ``RaphaÃ«l``;
- missing visual word spaces at boundaries between regular and italic spans,
  e.g. ``2016`` + italic ``PNAS`` + ``paper``.

This pass is intentionally source-level and idempotent. It fixes mojibake with
``ftfy`` and inserts a TeX nonbreaking word space (``~``) at the start of the
right-hand span when an italic/regular boundary visibly needs an inter-word gap.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from ftfy import fix_text

REPO = Path(__file__).resolve().parents[1]
TEX_GLOB = "Interviews/Issue*/*/*.tex"
SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{)(?P<text>.*)(?P<suffix>\}\s*)$"
)
PAGE_RE = re.compile(r"% Page (\d+)")
# Flag only characteristic mojibake sequences, not every legitimate Latin
# letter that happens to contain these codepoints.
MOJIBAKE_RE = re.compile(
    r"(?:Ã.|Â.|â€.|â€“|â€”|â€¦|â€œ|â€|â€˜|â€™|â–¡)"
)
INLINE_GAP = "~"
MAX_INLINE_GAP_BP = 1.5
MIN_INLINE_GAP_BP = -2.0

MANUAL_TEXT_REPAIRS = {
    # ``ftfy`` handles the usual UTF-8/Windows-1252 damage, but a few PDF
    # extraction paths leave these two-character leftovers intact.
    "Ã…": "Å",
    "á¹£": "ṣ",
    # Several original reference URLs carried a tiny external-link glyph that
    # extracted as this mojibake sequence. The reconstructed PDFs already use
    # real hyperlinks, so keeping a tofu-like marker only creates bad output.
    " â–¡": "",
    "â–¡": "",
    " □": "",
}


def plain_text(text: str) -> str:
    text = re.sub(r"\\ALIUSCitationLink\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", text)
    text = text.replace(r"\&", "&")
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{([^}]*)\})?", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    text = text.replace("~", " ")
    return text


def starts_with_gap(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(("~", r"\ ", r"\,", r"\;", r"\quad", r"\qquad", r"\hspace", r"\kern"))


def is_inline_style_boundary(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["font"] == right["font"]:
        return False
    return "Italic" in left["font"] or "Italic" in right["font"]


def allowed_spacing_pair(left: dict[str, Any], right: dict[str, Any], gap: float) -> bool:
    """Return whether two adjacent spans are plausible pieces of one sentence.

    Rows are reconstructed by y-coordinate, and bulletin pages often place
    unrelated footer/header/column snippets on the same baseline. Large negative
    gaps are therefore almost always separate layout objects, not missing word
    spaces. URLs and reference anchors are also left alone: link wrapping is
    handled by the citation/link macros, not by inline prose repair.
    """

    if gap < MIN_INLINE_GAP_BP or gap > MAX_INLINE_GAP_BP:
        return False
    if left["color"] == "ALIUSC767171" or right["color"] == "ALIUSC767171":
        return False
    if left["y"] < 60 or right["y"] < 60 or left["y"] > 760 or right["y"] > 760:
        return False
    joined = left["text"] + right["text"]
    if any(marker in joined for marker in ("http", "doi.org", r"\ALIUSRefAnchor")):
        return False
    return True


def needs_word_space(left_text: str, right_text: str) -> bool:
    if starts_with_gap(right_text):
        return False
    left = plain_text(left_text).rstrip()
    right = plain_text(right_text).lstrip()
    if not left or not right:
        return False
    if left[-1] in "([{/\u2013\u2014-":
        return False
    if right[0] in ".,;:!?)]}/\u2013\u2014-":
        return False
    return bool(re.search(r"[A-Za-z0-9)\]\u00bb'\"]$", left) and re.match(r"[A-Za-z0-9\u00ab'\"]", right))


def parse_spans(lines: list[str]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    page = 0
    for idx, line in enumerate(lines):
        page_match = PAGE_RE.match(line)
        if page_match:
            page = int(page_match.group(1))
        match = SPAN_RE.match(line)
        if not match:
            continue
        item = match.groupdict()
        item["idx"] = idx
        item["page"] = page
        item["x"] = float(item["x"])
        item["y"] = float(item["y"])
        item["w"] = float(item["w"])
        spans.append(item)
    return spans


def row_groups(spans: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for span in sorted(spans, key=lambda item: (item["page"], item["y"], item["x"], item["idx"])):
        if rows and rows[-1][0]["page"] == span["page"] and abs(rows[-1][0]["y"] - span["y"]) <= 0.75:
            rows[-1].append(span)
        else:
            rows.append([span])
    return [sorted(row, key=lambda item: (item["x"], item["idx"])) for row in rows]


def add_leading_gap(line: str) -> str:
    match = SPAN_RE.match(line)
    if not match:
        return line
    text = match.group("text")
    if starts_with_gap(text):
        return line
    return f"{match.group('prefix')}{INLINE_GAP}{text}{match.group('suffix')}"


def repair_inline_spacing(lines: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    spans = parse_spans(lines)
    indices_to_prefix: set[int] = set()
    repairs: list[dict[str, Any]] = []
    for row in row_groups(spans):
        for left, right in zip(row, row[1:]):
            if not is_inline_style_boundary(left, right):
                continue
            gap = right["x"] - (left["x"] + left["w"])
            if not allowed_spacing_pair(left, right, gap):
                continue
            if not needs_word_space(left["text"], right["text"]):
                continue
            indices_to_prefix.add(right["idx"])
            repairs.append(
                {
                    "line": right["idx"] + 1,
                    "page": right["page"],
                    "left": plain_text(left["text"])[-40:],
                    "right": plain_text(right["text"])[:40],
                    "gap_bp": round(gap, 3),
                }
            )
    if not indices_to_prefix:
        return lines, repairs
    out = lines[:]
    for idx in sorted(indices_to_prefix):
        out[idx] = add_leading_gap(out[idx])
    return out, repairs


def process_file(path: Path, write: bool = True) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    fixed = fix_text(original)
    for before, after in MANUAL_TEXT_REPAIRS.items():
        fixed = fixed.replace(before, after)
    mojibake_fixed = original != fixed
    lines = fixed.splitlines(keepends=True)
    lines, spacing_repairs = repair_inline_spacing(lines)
    new_text = "".join(lines)
    if write and new_text != original:
        path.write_text(new_text, encoding="utf-8", newline="")
    return {
        "file": path.relative_to(REPO).as_posix(),
        "mojibake_fixed": mojibake_fixed,
        "inline_spacing_repairs": spacing_repairs,
        "changed": new_text != original,
        "remaining_mojibake_markers": len(MOJIBAKE_RE.findall(new_text)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate without writing")
    parser.add_argument("--report", type=Path, default=REPO / "tmp" / "text-encoding-inline-spacing-report.json")
    args = parser.parse_args()

    reports = [process_file(path, write=not args.check) for path in sorted(REPO.glob(TEX_GLOB))]
    problems = [
        item
        for item in reports
        if (item["changed"] if args.check else False) or item["remaining_mojibake_markers"]
    ]
    report = {
        "tex_files": len(reports),
        "changed_files": sum(1 for item in reports if item["changed"]),
        "mojibake_fixed_files": sum(1 for item in reports if item["mojibake_fixed"]),
        "inline_spacing_repairs": sum(len(item["inline_spacing_repairs"]) for item in reports),
        "remaining_mojibake_markers": sum(item["remaining_mojibake_markers"] for item in reports),
        "files": reports,
        "ok": not problems,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
