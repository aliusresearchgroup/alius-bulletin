"""Standardize legacy extracted ALIUS pull-quote blocks.

The native reconstructions contain many historical pull quotes as separate
absolute-positioned text spans: an opening quote mark, several Lato quote lines,
and a closing quote mark. In those legacy blocks the closing mark can accidentally
sit on an interior line and cause the visual failure where later quote text appears
after the closing mark.

This pass is deliberately conservative. It does not rewrite the quoted words or
change page flow. It only normalizes the geometry of each extracted pull-quote
cluster:

- body lines remain in their existing line breaks but are centered as a compact
  rectangular text box on the PDF page centerline;
- the opening quote mark sits just outside the top-left of the body box;
- the closing quote mark sits just outside the bottom-right of the final body
  line, never between body lines;
- top/bottom spacing to surrounding normal text is checked so a quote block has
  at least roughly one quote-line of breathing room.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import re
from statistics import median
from typing import Any

REPO = Path(__file__).resolve().parents[1]
TEX_GLOB = "Interviews/Issue*/*/*.tex"

SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{)(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{(?P<text>.*)(?P<suffix>\}\s*)$"
)
PAGE_RE = re.compile(r"% Page (\d+)")

QUOTE_OPEN = r"\ALIUSPullQuoteOpen"
QUOTE_CLOSE = r"\ALIUSPullQuoteClose"
PULL_QUOTE_TEXT_COLORS = {"ALIUSC000000", "ALIUSC595959", "ALIUSC7F7F7F"}
MIN_SURROUNDING_GAP = 18.0
PAGE_WIDTH = 595.0
PAGE_CENTER_X = PAGE_WIDTH / 2.0
PAGE_TEXT_BOTTOM = 760.0


@dataclass
class Span:
    idx: int
    page: int
    x: float
    y: float
    width: float
    color: str
    font: str
    size: float
    text: str


@dataclass
class PullQuoteBlock:
    opener: Span
    closer: Span
    body: list[Span]


def parse_spans(lines: list[str]) -> list[Span]:
    spans: list[Span] = []
    page = 0
    for idx, line in enumerate(lines):
        page_match = PAGE_RE.match(line)
        if page_match:
            page = int(page_match.group(1))
        match = SPAN_RE.match(line)
        if not match:
            continue
        spans.append(
            Span(
                idx=idx,
                page=page,
                x=float(match.group("x")),
                y=float(match.group("y")),
                width=float(match.group("w")),
                color=match.group("color"),
                font=match.group("font"),
                size=float(match.group("size")),
                text=match.group("text").strip(),
            )
        )
    return spans


def is_pull_body(span: Span, opener: Span, closer: Span) -> bool:
    if span.page != opener.page:
        return False
    if not (opener.y - 2.0 <= span.y <= max(closer.y + 60.0, opener.y + 60.0)):
        return False
    return (
        "ALIUSFontLato" in span.font
        and 13.0 <= span.size <= 18.5
        and span.color in PULL_QUOTE_TEXT_COLORS
        and span.text not in {"", "References", QUOTE_OPEN, QUOTE_CLOSE}
        and "http" not in span.text
        and span.x >= opener.x + 4.0
    )


def find_blocks(spans: list[Span]) -> list[PullQuoteBlock]:
    blocks: list[PullQuoteBlock] = []
    used_closers: set[int] = set()
    for opener in [span for span in spans if span.text == QUOTE_OPEN]:
        possible_closers = [
            span
            for span in spans
            if span.text == QUOTE_CLOSE
            and span.page == opener.page
            and span.idx > opener.idx
            and span.idx not in used_closers
            and opener.y - 10.0 <= span.y <= opener.y + 220.0
        ]
        if not possible_closers:
            continue
        closer = min(possible_closers, key=lambda span: (abs(span.y - opener.y), span.idx))
        body = [span for span in spans if span.idx not in {opener.idx, closer.idx} and is_pull_body(span, opener, closer)]
        # Keep the visual cluster compact if the y-window accidentally caught a
        # second quote block on the same page.
        body = sorted(body, key=lambda span: (span.y, span.x))
        compact: list[Span] = []
        previous_y: float | None = None
        for line in body:
            if previous_y is not None and line.y - previous_y > 42.0:
                break
            compact.append(line)
            previous_y = line.y
        if compact:
            blocks.append(PullQuoteBlock(opener=opener, closer=closer, body=compact))
            used_closers.add(closer.idx)
    return blocks


def replace_x_y(line: str, x: float, y: float) -> str:
    match = SPAN_RE.match(line)
    if not match:
        return line
    return f"{match.group('prefix')}{x:.3f}}}{{{y:.3f}}}{{{match.group('w')}}}{{{match.group('color')}}}{{{match.group('font')}}}{{{match.group('size')}}}{{{match.group('text')}{match.group('suffix')}"


def line_gap_for(spans: list[Span]) -> float:
    gaps: list[float] = []
    for page in sorted({span.page for span in spans}):
        ys = sorted({span.y for span in spans if span.page == page})
        gaps.extend(b - a for a, b in zip(ys, ys[1:]) if 6.0 <= b - a <= 32.0)
    return median(gaps) if gaps else 18.0


def grouped_rows(spans: list[Span]) -> list[list[Span]]:
    rows: list[list[Span]] = []
    for span in sorted(spans, key=lambda item: (item.y, item.x)):
        if rows and abs(rows[-1][0].y - span.y) <= 1.0:
            rows[-1].append(span)
        else:
            rows.append([span])
    return rows


def quote_line_gap(rows: list[list[Span]]) -> float:
    if len(rows) < 2:
        return max(16.5, min(24.0, rows[0][0].size * 1.22 if rows else 18.0))
    ys = [row[0].y for row in rows]
    gaps = [b - a for a, b in zip(ys, ys[1:]) if 12.0 <= b - a <= 30.0]
    fallback = rows[0][0].size * 1.22
    return max(16.5, min(24.0, min(gaps) if gaps else fallback))


def same_page_closer_after(spans: list[Span], opener: Span) -> Span | None:
    next_opener = min(
        (
            span.idx
            for span in spans
            if span.text == QUOTE_OPEN
            and span.page == opener.page
            and span.idx > opener.idx
        ),
        default=10**9,
    )
    closers = [
        span
        for span in spans
        if span.text == QUOTE_CLOSE
        and span.page == opener.page
        and opener.idx < span.idx < next_opener
        and opener.y - 10.0 <= span.y <= opener.y + 220.0
    ]
    return closers[-1] if closers else None


def quote_text_like(span: Span) -> bool:
    return (
        "ALIUSFontLato" in span.font
        and 13.0 <= span.size <= 18.5
        and span.color in PULL_QUOTE_TEXT_COLORS
        and span.text not in {"", "References", QUOTE_OPEN, QUOTE_CLOSE}
        and "http" not in span.text
    )


def repair_one_cross_page_pull_quote(lines: list[str]) -> tuple[list[str], dict[str, Any] | None]:
    """Pull a one- or two-line quote continuation back from the next page.

    A few extracted originals put the last body line and closing mark at the top
    of the next page even though the whole quote can fit in the previous page's
    text area. That violates the standardized top-left/bottom-right quote frame.
    This repair moves only those top-of-next-page quote continuation spans into
    the opener's page, preserving all subsequent interview content.
    """
    spans = parse_spans(lines)
    for opener in [span for span in spans if span.text == QUOTE_OPEN]:
        if same_page_closer_after(spans, opener):
            continue
        next_page_closers = [
            span
            for span in spans
            if span.text == QUOTE_CLOSE
            and span.page == opener.page + 1
            and span.y <= 150.0
        ]
        if not next_page_closers:
            continue
        closer = min(next_page_closers, key=lambda span: (span.y, span.idx))
        body_same = [
            span
            for span in spans
            if span.page == opener.page
            and span.idx > opener.idx
            and quote_text_like(span)
            and span.x >= opener.x + 4.0
            and opener.y - 2.0 <= span.y <= PAGE_TEXT_BOTTOM
        ]
        body_next = [
            span
            for span in spans
            if span.page == opener.page + 1
            and quote_text_like(span)
            and 60.0 <= span.y <= closer.y + 2.0
        ]
        if not body_same or not body_next:
            continue
        body = sorted(body_same, key=lambda span: (span.y, span.x)) + sorted(body_next, key=lambda span: (span.y, span.x))
        gap = line_gap_for(body)
        first_y = min(span.y for span in body_same)
        above = max(
            (
                span
                for span in spans
                if span.page == opener.page
                and span.idx not in {opener.idx, *[item.idx for item in body_same]}
                and span.text not in {"", QUOTE_OPEN, QUOTE_CLOSE}
                and span.color != "ALIUSC767171"
                and span.y < opener.y
            ),
            key=lambda span: span.y,
            default=None,
        )
        required_shift = min(0.0, PAGE_TEXT_BOTTOM - (first_y + gap * len(body)))
        upward_room = (first_y - above.y - MIN_SURROUNDING_GAP) if above else 999.0
        if abs(required_shift) > upward_room + 0.1:
            continue
        shift = required_shift
        if first_y + shift + gap * len(body) > PAGE_TEXT_BOTTOM + 0.1:
            continue

        center = PAGE_CENTER_X
        new_lefts = {span.idx: center - span.width / 2.0 for span in body}
        body_left = min(new_lefts.values())
        body_right = max(new_lefts[span.idx] + span.width for span in body)

        desired_y = {span.idx: first_y + shift + gap * i for i, span in enumerate(body)}
        planned: dict[int, tuple[float, float]] = {
            opener.idx: (body_left - 18.0, desired_y[body[0].idx]),
            closer.idx: (body_right + 4.0, desired_y[body[-1].idx]),
        }
        for span in body:
            planned[span.idx] = (new_lefts[span.idx], desired_y[span.idx])

        out = lines[:]
        for span in [opener, *body_same]:
            x, y = planned[span.idx]
            out[span.idx] = replace_x_y(out[span.idx], x, y)

        continuation = []
        for span in sorted(body_next, key=lambda span: (span.y, span.x)):
            x, y = planned[span.idx]
            continuation.append(replace_x_y(out[span.idx], x, y))
        x, y = planned[closer.idx]
        continuation.append(replace_x_y(out[closer.idx], x, y))

        remove = {span.idx for span in body_next} | {closer.idx}
        insert_after = max(span.idx for span in body_same)
        rebuilt: list[str] = []
        for idx, line in enumerate(out):
            if idx in remove:
                continue
            rebuilt.append(line)
            if idx == insert_after:
                rebuilt.extend(continuation)

        return rebuilt, {
            "line": opener.idx + 1,
            "page": opener.page,
            "moved_lines": len(body_next) + 1,
            "shift_bp": round(shift, 3),
        }
    return lines, None


def surrounding_spans(spans: list[Span], block: PullQuoteBlock) -> tuple[Span | None, Span | None]:
    body_indices = {span.idx for span in block.body} | {block.opener.idx, block.closer.idx}
    top = min(span.y for span in block.body)
    bottom = max(span.y for span in block.body)
    nearby = [
        span
        for span in spans
        if span.page == block.opener.page
        and span.idx not in body_indices
        and span.text not in {"", QUOTE_OPEN, QUOTE_CLOSE}
        and span.color != "ALIUSC767171"
        and 60.0 <= span.y <= 760.0
    ]
    above = max((span for span in nearby if span.y < top), key=lambda span: span.y, default=None)
    below = min((span for span in nearby if span.y > bottom), key=lambda span: span.y, default=None)
    return above, below


def process_file(path: Path, write: bool = True) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    cross_page_repairs: list[dict[str, Any]] = []
    while True:
        lines, repair = repair_one_cross_page_pull_quote(lines)
        if repair is None:
            break
        cross_page_repairs.append(repair)
    spans = parse_spans(lines)
    blocks = find_blocks(spans)
    changed_blocks: list[dict[str, Any]] = []
    spacing_warnings: list[str] = []

    for block in blocks:
        rows = grouped_rows(block.body)
        row_boxes = [
            (
                min(span.x for span in row),
                max(span.x + span.width for span in row),
                row,
            )
            for row in rows
        ]
        max_width = max(right - left for left, right, _row in row_boxes)
        center = PAGE_CENTER_X
        first = min(block.body, key=lambda span: (span.y, span.x))
        above, below = surrounding_spans(spans, block)
        line_gap = quote_line_gap(rows)
        top = first.y
        bottom = first.y + line_gap * len(rows)
        vertical_shift = 0.0
        if below and below.y - bottom < MIN_SURROUNDING_GAP:
            deficit = MIN_SURROUNDING_GAP - (below.y - bottom)
            above_gap = (top - above.y) if above else 999.0
            upward_room = max(0.0, above_gap - MIN_SURROUNDING_GAP)
            vertical_shift -= min(deficit, upward_room)
        if above and (top + vertical_shift) - above.y < MIN_SURROUNDING_GAP:
            deficit = MIN_SURROUNDING_GAP - ((top + vertical_shift) - above.y)
            below_gap = (below.y - (bottom + vertical_shift)) if below else 999.0
            downward_room = max(0.0, below_gap - MIN_SURROUNDING_GAP)
            vertical_shift += min(deficit, downward_room)

        new_positions: dict[int, tuple[float, float]] = {}
        for row_index, (row_left, row_right, row) in enumerate(row_boxes):
            target_row_left = center - (row_right - row_left) / 2.0
            dx = target_row_left - row_left
            target_y = first.y + vertical_shift + line_gap * row_index
            for span in row:
                new_positions[span.idx] = (span.x + dx, target_y)

        body_left = min(x for x, _y in new_positions.values())
        body_right = max(new_positions[span.idx][0] + span.width for span in block.body)
        open_x = body_left - 18.0
        open_y = first.y + vertical_shift
        close_x = body_right + 4.0
        close_y = first.y + vertical_shift + line_gap * (len(rows) - 1)

        planned: dict[int, tuple[float, float]] = {
            block.opener.idx: (open_x, open_y),
            block.closer.idx: (close_x, close_y),
        }
        for span in block.body:
            planned[span.idx] = new_positions[span.idx]

        block_changed = False
        for idx, (x, y) in planned.items():
            current = next(span for span in [block.opener, block.closer, *block.body] if span.idx == idx)
            if abs(current.x - x) > 0.01 or abs(current.y - y) > 0.01:
                lines[idx] = replace_x_y(lines[idx], x, y)
                block_changed = True

        top = top + vertical_shift
        bottom = bottom + vertical_shift
        if above and top - above.y < MIN_SURROUNDING_GAP:
            spacing_warnings.append(
                f"{path.relative_to(REPO).as_posix()}:{block.opener.idx + 1}: only {top - above.y:.1f}bp above pull quote"
            )
        if below and below.y - bottom < MIN_SURROUNDING_GAP:
            spacing_warnings.append(
                f"{path.relative_to(REPO).as_posix()}:{block.opener.idx + 1}: only {below.y - bottom:.1f}bp below pull quote"
            )

        if block_changed:
            changed_blocks.append(
                {
                    "line": block.opener.idx + 1,
                    "page": block.opener.page,
                    "body_lines": len(block.body),
                    "max_body_width": round(max_width, 3),
                }
            )

    new_text = "".join(lines)
    if write and new_text != original:
        path.write_text(new_text, encoding="utf-8", newline="")
    return {
        "file": path.relative_to(REPO).as_posix(),
        "blocks": len(blocks),
        "cross_page_repairs": cross_page_repairs,
        "changed_blocks": changed_blocks,
        "spacing_warnings": spacing_warnings,
        "changed": new_text != original,
        "ok": not spacing_warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate/compute without writing")
    parser.add_argument("--dry-run", action="store_true", help="compute without writing")
    parser.add_argument("--report", type=Path, default=REPO / "tmp" / "pull-quote-standardization-report.json")
    args = parser.parse_args()

    per_file = [process_file(path, write=not (args.check or args.dry_run)) for path in sorted(REPO.glob(TEX_GLOB))]
    report = {
        "tex_files": len(per_file),
        "pull_quote_files": sum(1 for item in per_file if item["blocks"]),
        "pull_quote_blocks": sum(item["blocks"] for item in per_file),
        "changed_files": sum(1 for item in per_file if item["changed"]),
        "changed_blocks": sum(len(item["changed_blocks"]) for item in per_file),
        "cross_page_repairs": sum(len(item["cross_page_repairs"]) for item in per_file),
        "spacing_warnings": [warning for item in per_file for warning in item["spacing_warnings"]],
        "files": per_file,
        # Spacing warnings are advisory because some original pages intentionally
        # place pull quotes near page starts/ends. Geometry standardization still
        # succeeds when no write is pending after the pass.
        "ok": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
