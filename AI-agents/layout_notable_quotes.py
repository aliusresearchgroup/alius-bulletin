r"""Rule-based placement QA/reflow for ALIUS Q&A notable quotes.

The interview reconstructions are absolute-positioned TikZ pages. A TeX macro can
draw a quote, but it cannot inspect the surrounding interview segment or repaginate
following absolute nodes. This script is the formatting rule layer:

- notable quotes are treated as semantic Q&A-segment inserts;
- they must appear after the question/answer material they amplify and before the
  next question;
- if a quote leaves a large dead band before a page footer while the segment
  continues on the next page, following content is pulled forward into the usable
  space;
- running heads, page numbers, footers, and horizontal rules stay fixed;
- notable quote boxes are centered on the PDF/text page horizontally, not
  aligned to nearby paragraph starts;
- quote bodies are pre-wrapped at word boundaries so notable quotes never use
  hyphenated line breaks.

The script is conservative and idempotent. It rewrites generated absolute
coordinates and the generated line breaks inside semantic notable-quote slots.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

REPO = Path(__file__).resolve().parents[1]
TEX_GLOB = "Interviews/Issue*/*/*.tex"

PAGE_TOP = 70.938
PAGE_WIDTH = 595.0
PAGE_CENTER_X = PAGE_WIDTH / 2.0
PAGE_BOTTOM = 760.0
PAGE_HEIGHT = PAGE_BOTTOM - PAGE_TOP
FOOTER_TOP = 780.0
HEADER_BOTTOM = 60.0
QUOTE_VERTICAL_GAP = 8.0
MIN_GAP_AFTER_QUOTE = QUOTE_VERTICAL_GAP
MAX_ALLOWED_DEAD_SPACE = 95.0
PAGE_ROW_TOP = PAGE_TOP
MIN_ROW_GAP = 16.5
QUOTE_TARGET_CHARS_PER_LINE = 42
QUOTE_MAX_LINES = 4

SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{)(?P<text>.*)(?P<suffix>\}\s*)$"
)
QUOTE_RE = re.compile(
    r"(?P<prefix>\s*)\\ALIUSMaybeNotableQuoteAt\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}\{(?P<quote>.*)\}(?P<suffix>\s*)$"
)
PAGE_RE = re.compile(r"% Page (\d+)")
LEGACY_SLOT_RE = re.compile(r"\s*% ALIUS Q&A segment notable quote slot:\s*(?P<id>\S+)")
SLOT_BEGIN = "% ALIUS notable quote slot begin"
SLOT_END = "% ALIUS notable quote slot end"


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
class Quote:
    idx: int
    page: int
    x: float
    y: float
    width: float
    text: str
    quote_id: str


@dataclass
class Row:
    page: int
    y: float
    indices: list[int]
    lead: float


def parse_pages(lines: list[str]) -> dict[int, int]:
    page_for_line: dict[int, int] = {}
    page = 0
    for idx, line in enumerate(lines):
        match = PAGE_RE.match(line)
        if match:
            page = int(match.group(1))
        if page:
            page_for_line[idx] = page
    return page_for_line


def parse_spans(lines: list[str]) -> list[Span]:
    pages = parse_pages(lines)
    spans: list[Span] = []
    for idx, line in enumerate(lines):
        match = SPAN_RE.match(line)
        if not match:
            continue
        spans.append(
            Span(
                idx=idx,
                page=pages.get(idx, 0),
                x=float(match.group("x")),
                y=float(match.group("y")),
                width=float(match.group("w")),
                color=match.group("color"),
                font=match.group("font"),
                size=float(match.group("size")),
                text=match.group("text"),
            )
        )
    return spans


def parse_quotes(lines: list[str]) -> list[Quote]:
    pages = parse_pages(lines)
    quotes: list[Quote] = []
    current_id = ""
    for idx, line in enumerate(lines):
        legacy = LEGACY_SLOT_RE.match(line)
        if legacy:
            current_id = legacy.group("id")
            continue
        if line.strip().startswith("% ALIUS notable quote id:"):
            current_id = line.split(":", 1)[1].strip()
            continue
        match = QUOTE_RE.match(line)
        if not match:
            continue
        quote_id = current_id or f"quote-line-{idx + 1}"
        quotes.append(
            Quote(
                idx=idx,
                page=pages.get(idx, 0),
                x=float(match.group("x")),
                y=float(match.group("y")),
                width=float(match.group("w")),
                text=match.group("quote"),
                quote_id=quote_id,
            )
        )
        current_id = ""
    return quotes


def normalize_quote_slot_metadata(lines: list[str]) -> tuple[list[str], int]:
    """Wrap legacy one-line quote slots in semantic metadata comments."""
    out: list[str] = []
    changes = 0
    i = 0
    while i < len(lines):
        legacy = LEGACY_SLOT_RE.match(lines[i])
        if legacy and i + 1 < len(lines) and QUOTE_RE.match(lines[i + 1]):
            quote_id = legacy.group("id")
            if out and out[-1].strip() == SLOT_BEGIN:
                out.append(lines[i])
                i += 1
                continue
            out.append(f"{SLOT_BEGIN}\n")
            out.append(f"% ALIUS notable quote id: {quote_id}\n")
            out.append("% ALIUS notable quote rule: segment-auto-place; page-centered x; generated coordinates, do not hand-position\n")
            out.append(lines[i + 1])
            out.append(f"{SLOT_END}\n")
            changes += 1
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return out, changes


def unwrap_quote_text(text: str) -> str:
    return re.sub(r"\s*\\\\\s*", " ", text).strip()


def quote_display_lines(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*\\\\\s*", text.strip()) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def strip_tex_for_length(text: str) -> str:
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", "", text)
    text = re.sub(r"[{}]", "", text)
    return text


def best_balanced_linebreaks(words: list[str], line_count: int) -> list[str]:
    if line_count <= 1 or len(words) <= line_count:
        return [" ".join(words)]
    lengths = [len(strip_tex_for_length(word)) for word in words]
    prefix = [0]
    for i, word_len in enumerate(lengths):
        # Include one separating space between adjacent words inside a line.
        prefix.append(prefix[-1] + word_len + (0 if i == 0 else 1))

    def segment_len(start: int, end: int) -> int:
        if start >= end:
            return 0
        return prefix[end] - prefix[start] - (0 if start == 0 else 1)

    total = segment_len(0, len(words))
    target = max(1.0, total / line_count)
    # Dynamic programming keeps the generated quote box rectangular without
    # ever splitting a word, which avoids TeX hyphenation in the rendered PDF.
    dp: list[dict[tuple[int, int], tuple[float, list[int]]]] = [{} for _ in range(line_count + 1)]
    dp[0][(0, 0)] = (0.0, [])
    for line_no in range(1, line_count + 1):
        remaining_lines = line_count - line_no
        for (prev_end, _unused), (score, breaks) in dp[line_no - 1].items():
            min_end = prev_end + 1
            max_end = len(words) - remaining_lines
            for end in range(min_end, max_end + 1):
                width = segment_len(prev_end, end)
                too_long_penalty = max(0.0, width - QUOTE_TARGET_CHARS_PER_LINE - 8) ** 2
                new_score = score + (width - target) ** 2 + too_long_penalty
                key = (end, line_no)
                if key not in dp[line_no] or new_score < dp[line_no][key][0]:
                    dp[line_no][key] = (new_score, [*breaks, end])
    best = dp[line_count].get((len(words), line_count))
    if not best:
        return [" ".join(words)]
    breaks = best[1]
    start = 0
    lines: list[str] = []
    for end in breaks:
        lines.append(" ".join(words[start:end]))
        start = end
    return lines


def wrap_quote_text_for_display(text: str) -> str:
    clean = unwrap_quote_text(text)
    if not clean:
        return text
    words = clean.split()
    if len(words) <= 3:
        return clean
    visible_len = len(strip_tex_for_length(clean))
    line_count = max(2, min(QUOTE_MAX_LINES, math.ceil(visible_len / QUOTE_TARGET_CHARS_PER_LINE)))
    line_count = min(line_count, len(words))
    return r"\\".join(best_balanced_linebreaks(words, line_count))


def normalize_quote_linebreaks(lines: list[str]) -> tuple[list[str], int]:
    """Normalize semantic quote text into balanced manual line breaks."""
    out = lines[:]
    changes = 0
    for idx, line in enumerate(lines):
        match = QUOTE_RE.match(line)
        if not match:
            continue
        wrapped = wrap_quote_text_for_display(match.group("quote"))
        if wrapped == match.group("quote"):
            continue
        out[idx] = (
            f"{match.group('prefix')}\\ALIUSMaybeNotableQuoteAt"
            f"{{{match.group('x')}}}{{{match.group('y')}}}{{{match.group('w')}}}{{{wrapped}}}"
            f"{match.group('suffix')}"
        )
        changes += 1
    return out, changes


def quote_height(quote: Quote) -> float:
    # The TeX macro uses Lato Light 15bp / 18bp. The layout script writes
    # explicit \\ line breaks, so quote height follows the rendered line count
    # rather than relying on TeX hyphenation or a fixed text width.
    line_count = len(quote_display_lines(quote.text))
    if line_count == 0:
        visible = strip_tex_for_length(unwrap_quote_text(quote.text))
        line_count = max(1, math.ceil(len(visible) / QUOTE_TARGET_CHARS_PER_LINE))
    # Closing quote ornaments are shifted slightly below the natural body box so
    # they visually hug the last quote line rather than floating between lines.
    return 18.0 * max(1, line_count) + 8.0


def quote_bottom_y(quote: Quote) -> float:
    return quote.y + quote_height(quote)


def quote_following_text_y(quote: Quote) -> float:
    return quote_bottom_y(quote) + QUOTE_VERTICAL_GAP


def is_movable_content(span: Span) -> bool:
    if span.color == "ALIUSC767171":
        return False
    if span.y < HEADER_BOTTOM or span.y > FOOTER_TOP:
        return False
    if span.text.strip() in {"", r"\ALIUSPullQuoteOpen", r"\ALIUSPullQuoteClose"}:
        return False
    return True


def is_question_span(span: Span) -> bool:
    return (
        span.color == "ALIUSC1F8135"
        and "Lato" in span.font
        and 11.0 <= span.size <= 14.5
        and 60 <= span.y <= 760
        and "doi.org" not in span.text
    )


def next_movable_span_after(spans: list[Span], idx: int) -> Span | None:
    for span in spans:
        if span.idx > idx and is_movable_content(span):
            return span
    return None


def previous_movable_span_before(spans: list[Span], quote: Quote) -> Span | None:
    previous = [
        span
        for span in spans
        if span.page == quote.page
        and span.idx < quote.idx
        and is_movable_content(span)
        and span.text.strip() not in {r"\ALIUSPullQuoteOpen", r"\ALIUSPullQuoteClose"}
    ]
    return max(previous, key=lambda span: (span.y, span.idx), default=None)


def previous_question_before(spans: list[Span], idx: int) -> Span | None:
    questions = [span for span in spans if span.idx < idx and is_question_span(span)]
    return questions[-1] if questions else None


def next_question_after(spans: list[Span], idx: int) -> Span | None:
    for span in spans:
        if span.idx > idx and is_question_span(span):
            return span
    return None


def replace_second_arg_y(line: str, y: float) -> str:
    if SPAN_RE.match(line):
        return re.sub(r"(\\ALIUSPlacedTextContent\{[^}]+\}\{)[^}]+", rf"\g<1>{y:.3f}", line, count=1)
    if QUOTE_RE.match(line):
        return re.sub(r"(\\ALIUSMaybeNotableQuoteAt\{[^}]+\}\{)[^}]+", rf"\g<1>{y:.3f}", line, count=1)
    return line


def replace_quote_x_width(line: str, x: float, width: float | None = None) -> str:
    match = QUOTE_RE.match(line)
    if not match:
        return line
    new_width = float(match.group("w")) if width is None else width
    return (
        f"{match.group('prefix')}\\ALIUSMaybeNotableQuoteAt"
        f"{{{x:.3f}}}{{{match.group('y')}}}{{{new_width:.3f}}}{{{match.group('quote')}}}"
        f"{match.group('suffix')}"
    )


def centered_quote_x(width: float) -> float:
    return PAGE_CENTER_X - width / 2.0


def normalize_quote_horizontal_center(lines: list[str]) -> tuple[list[str], int]:
    """Center semantic memorable/notable quotes on the PDF page.

    The y coordinate remains governed by segment-aware placement. The x
    coordinate is universal: the quote box sits at the page center rather than
    inheriting the paragraph's left edge or a hand-tuned local anchor.
    """
    out = lines[:]
    changes = 0
    for quote in parse_quotes(lines):
        desired_x = centered_quote_x(quote.width)
        if abs(quote.x - desired_x) > 0.01:
            out[quote.idx] = replace_quote_x_width(out[quote.idx], desired_x)
            changes += 1
    return out, changes


def line_is_movable_absolute(lines: list[str], idx: int, quote_idx: int) -> bool:
    span_match = SPAN_RE.match(lines[idx])
    if span_match:
        y = float(span_match.group("y"))
        color = span_match.group("color")
        return color != "ALIUSC767171" and HEADER_BOTTOM <= y <= FOOTER_TOP
    quote_match = QUOTE_RE.match(lines[idx])
    return bool(quote_match and idx != quote_idx)


def line_y(lines: list[str], idx: int) -> float | None:
    match = SPAN_RE.match(lines[idx]) or QUOTE_RE.match(lines[idx])
    return float(match.group("y")) if match else None


def line_x(lines: list[str], idx: int) -> float:
    match = SPAN_RE.match(lines[idx]) or QUOTE_RE.match(lines[idx])
    return float(match.group("x")) if match else 0.0


def line_lead(lines: list[str], idx: int) -> float:
    span_match = SPAN_RE.match(lines[idx])
    if span_match:
        text = span_match.group("text").strip()
        size = float(span_match.group("size"))
        if text in {r"\ALIUSPullQuoteOpen", r"\ALIUSPullQuoteClose"} or size >= 30:
            return 18.0
        return max(MIN_ROW_GAP, min(24.0, size * 1.22))
    quote_match = QUOTE_RE.match(lines[idx])
    if quote_match:
        return quote_height(
            Quote(
                idx=idx,
                page=0,
                x=float(quote_match.group("x")),
                y=float(quote_match.group("y")),
                width=float(quote_match.group("w")),
                text=quote_match.group("quote"),
                quote_id="",
            )
        )
    return MIN_ROW_GAP


def movable_rows_after_quote(lines: list[str], quote_idx: int) -> list[Row]:
    """Group movable absolute elements into visual rows after a quote."""
    pages = parse_pages(lines)
    rows: list[Row] = []
    for idx, _line in enumerate(lines):
        if idx <= quote_idx or not line_is_movable_absolute(lines, idx, quote_idx):
            continue
        y = line_y(lines, idx)
        page = pages.get(idx)
        if y is None or page is None:
            continue
        if rows and rows[-1].page == page and abs(rows[-1].y - y) <= 0.75:
            rows[-1].indices.append(idx)
            rows[-1].lead = max(rows[-1].lead, line_lead(lines, idx))
        else:
            rows.append(Row(page=page, y=y, indices=[idx], lead=line_lead(lines, idx)))
    return rows


def insert_moved_lines_by_page(
    lines: list[str],
    remove_indices: set[int],
    moved: list[tuple[int, float, float, int, str]],
) -> list[str]:
    remaining = [line for idx, line in enumerate(lines) if idx not in remove_indices]
    insertions: dict[int, list[tuple[float, float, int, str]]] = {}
    for item in moved:
        insertions.setdefault(item[0], []).append((item[1], item[2], item[3], item[4]))
    for page in insertions:
        insertions[page].sort(key=lambda item: (item[0], item[1], item[2]))

    out: list[str] = []
    page = 0
    for line in remaining:
        page_match = PAGE_RE.match(line)
        if page_match:
            page = int(page_match.group(1))
        span_match = SPAN_RE.match(line)
        if page in insertions and span_match and span_match.group("color") == "ALIUSC767171" and float(span_match.group("y")) >= FOOTER_TOP:
            out.extend(item[3] for item in insertions.pop(page))
        out.append(line)

    if insertions:
        final: list[str] = []
        page = 0
        for line in out:
            page_match = PAGE_RE.match(line)
            if page_match:
                page = int(page_match.group(1))
            if page in insertions and line.startswith(r"\end{tikzpicture}"):
                final.extend(item[3] for item in insertions.pop(page))
            final.append(line)
        out = final

    if insertions:
        raise RuntimeError(f"uninserted reflow page groups: {sorted(insertions)}")
    return out


def reflow_after_quote(lines: list[str], quote: Quote, next_span: Span) -> tuple[list[str], float]:
    """Pull downstream absolute content forward so the next span follows quote."""
    target_y = quote_following_text_y(quote)
    target_y = min(target_y, PAGE_BOTTOM - 20.0)
    global_next = (next_span.page - quote.page) * PAGE_HEIGHT + next_span.y
    shift = global_next - target_y
    if shift <= 0:
        return lines, 0.0

    page_for_line = parse_pages(lines)
    moved: list[tuple[int, float, float, int, str]] = []
    remove_indices: set[int] = set()
    for idx, line in enumerate(lines):
        page = page_for_line.get(idx)
        if page is None or idx <= quote.idx:
            continue
        if not line_is_movable_absolute(lines, idx, quote.idx):
            continue
        y = line_y(lines, idx)
        if y is None:
            continue
        match = SPAN_RE.match(line) or QUOTE_RE.match(line)
        x = float(match.group("x"))
        flow = (page - quote.page) * PAGE_HEIGHT + y - shift
        page_delta = math.floor(flow / PAGE_HEIGHT)
        new_page = quote.page + page_delta
        new_y = flow - page_delta * PAGE_HEIGHT
        if new_y < PAGE_TOP:
            new_page -= 1
            new_y += PAGE_HEIGHT
        if new_y > PAGE_BOTTOM:
            new_page += 1
            new_y -= PAGE_HEIGHT
        if new_page < quote.page:
            new_page = quote.page
            new_y = max(PAGE_TOP, new_y)
        moved.append((new_page, new_y, x, idx, replace_second_arg_y(line, new_y)))
        remove_indices.add(idx)

    if not moved:
        return lines, 0.0

    return insert_moved_lines_by_page(lines, remove_indices, moved), shift


def normalize_row_flow_after_quote(lines: list[str], quote: Quote) -> tuple[list[str], int]:
    """Keep downstream content rows readable after quote-driven reflow.

    Pulling next-page content forward can create a false continuous coordinate
    system where the last line of one page and the first line of the next page
    end up only a few bp apart. This pass keeps the rule semantic rather than
    absolute: content may flow forward, but rows must retain readable leading
    and wrap to the next reconstructed page before touching the footer.
    """
    rows = movable_rows_after_quote(lines, quote.idx)
    if not rows:
        return lines, 0

    target_y = quote_following_text_y(quote)
    current_page = quote.page
    current_y = max(rows[0].y if rows[0].page == quote.page else PAGE_ROW_TOP, target_y)
    if current_y > PAGE_BOTTOM:
        current_page += 1
        current_y = PAGE_ROW_TOP

    placements: dict[int, tuple[int, float]] = {}
    changed_rows = 0
    previous_page = current_page
    previous_y = current_y
    previous_lead = rows[0].lead
    for row_number, row in enumerate(rows):
        if row_number == 0:
            new_page, new_y = current_page, current_y
        else:
            candidate_page = max(row.page, previous_page)
            candidate_y = row.y
            if candidate_page == previous_page:
                candidate_y = max(candidate_y, previous_y + max(MIN_ROW_GAP, previous_lead))
            if candidate_y > PAGE_BOTTOM:
                candidate_page = previous_page + 1
                candidate_y = PAGE_ROW_TOP
            if candidate_y < PAGE_ROW_TOP:
                candidate_y = PAGE_ROW_TOP
            new_page, new_y = candidate_page, candidate_y

        if new_page != row.page or abs(new_y - row.y) > 0.01:
            changed_rows += 1
        for idx in row.indices:
            placements[idx] = (new_page, new_y)
        previous_page, previous_y, previous_lead = new_page, new_y, row.lead

    if not changed_rows:
        return lines, 0

    moved: list[tuple[int, float, float, int, str]] = []
    remove_indices: set[int] = set()
    for idx, (new_page, new_y) in placements.items():
        moved.append((new_page, new_y, line_x(lines, idx), idx, replace_second_arg_y(lines[idx], new_y)))
        remove_indices.add(idx)
    return insert_moved_lines_by_page(lines, remove_indices, moved), changed_rows


def compact_local_spacing_around_quote(lines: list[str], quote: Quote) -> tuple[list[str], int]:
    """Remove same-page dead air around a semantic notable quote.

    Notable quotes should sit like a paragraph-level insert: one normal row of
    breathing room after the amplified answer material, and one normal row
    before the following text. This pass avoids hand-coded y coordinates by
    deriving both edges from surrounding movable rows.
    """
    spans = parse_spans(lines)
    current_quote = next((item for item in parse_quotes(lines) if item.idx == quote.idx), quote)
    previous = previous_movable_span_before(spans, current_quote)
    next_span = next_movable_span_after(spans, current_quote.idx)
    if not previous or not next_span or next_span.page != current_quote.page:
        return lines, 0

    previous_bottom = previous.y + line_lead(lines, previous.idx)
    desired_quote_y = previous_bottom + QUOTE_VERTICAL_GAP
    changed_rows = 0
    if current_quote.y - desired_quote_y > 4.0:
        lines[current_quote.idx] = replace_second_arg_y(lines[current_quote.idx], desired_quote_y)
        changed_rows += 1
        current_quote = Quote(
            idx=current_quote.idx,
            page=current_quote.page,
            x=current_quote.x,
            y=desired_quote_y,
            width=current_quote.width,
            text=current_quote.text,
            quote_id=current_quote.quote_id,
        )

    target_next_y = quote_following_text_y(current_quote)
    rows = [row for row in movable_rows_after_quote(lines, current_quote.idx) if row.page == current_quote.page]
    if not rows or rows[0].y - target_next_y <= 4.0:
        return lines, changed_rows

    placements: dict[int, float] = {}
    cursor = target_next_y
    for row in rows:
        new_y = min(row.y, max(cursor, PAGE_ROW_TOP))
        if abs(new_y - row.y) > 0.01:
            changed_rows += 1
            for idx in row.indices:
                placements[idx] = new_y
        cursor = new_y + max(MIN_ROW_GAP, row.lead)

    for idx, new_y in placements.items():
        lines[idx] = replace_second_arg_y(lines[idx], new_y)
    return lines, changed_rows


def downstream_row_problems(lines: list[str], quote: Quote) -> list[str]:
    rows = movable_rows_after_quote(lines, quote.idx)
    problems: list[str] = []
    previous: Row | None = None
    for row in rows:
        if row.page == quote.page and row.y < quote_following_text_y(quote) - 0.5:
            problems.append(f"{quote.quote_id}: downstream content row at {row.y:.1f}bp is too close to quote")
        if previous and row.page == previous.page:
            required = max(MIN_ROW_GAP, previous.lead)
            if row.y < previous.y + required - 0.5:
                problems.append(
                    f"{quote.quote_id}: rows at {previous.y:.1f}bp and {row.y:.1f}bp on page {row.page} are too close"
                )
        previous = row
    return problems


def process_file(path: Path, write: bool = True) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    lines, metadata_changes = normalize_quote_slot_metadata(lines)
    lines, linebreak_changes = normalize_quote_linebreaks(lines)
    lines, horizontal_center_changes = normalize_quote_horizontal_center(lines)
    reflow_shifts: list[dict[str, Any]] = []

    # Iterate: a reflow changes downstream pages/y coordinates, so reparse.
    while True:
        spans = parse_spans(lines)
        quotes = parse_quotes(lines)
        changed_this_round = False
        for quote in quotes:
            next_span = next_movable_span_after(spans, quote.idx)
            if not next_span:
                continue
            gap = (PAGE_BOTTOM - quote_bottom_y(quote)) if next_span.page > quote.page else next_span.y - quote_bottom_y(quote)
            if next_span.page > quote.page and gap > MAX_ALLOWED_DEAD_SPACE:
                lines, shift = reflow_after_quote(lines, quote, next_span)
                if shift > 0:
                    reflow_shifts.append(
                        {
                            "quote_id": quote.quote_id,
                            "quote_page": quote.page,
                            "next_content_page_before": next_span.page,
                            "shift_bp": round(shift, 3),
                        }
                    )
                    changed_this_round = True
                    break
        if not changed_this_round:
            break

    row_flow_repairs: list[dict[str, Any]] = []
    while True:
        quotes = parse_quotes(lines)
        repaired_this_round = False
        for quote in quotes:
            lines, changed_rows = normalize_row_flow_after_quote(lines, quote)
            if changed_rows:
                row_flow_repairs.append({"quote_id": quote.quote_id, "changed_rows": changed_rows})
                repaired_this_round = True
                break
        if not repaired_this_round:
            break

    local_spacing_repairs: list[dict[str, Any]] = []
    while True:
        quotes = parse_quotes(lines)
        repaired_this_round = False
        for quote in quotes:
            lines, changed_rows = compact_local_spacing_around_quote(lines, quote)
            if changed_rows:
                local_spacing_repairs.append({"quote_id": quote.quote_id, "changed_rows": changed_rows})
                repaired_this_round = True
                break
        if not repaired_this_round:
            break

    spans = parse_spans(lines)
    quotes = parse_quotes(lines)
    quote_reports: list[dict[str, Any]] = []
    problems: list[str] = []
    for quote in quotes:
        previous_question = previous_question_before(spans, quote.idx)
        next_question = next_question_after(spans, quote.idx)
        next_span = next_movable_span_after(spans, quote.idx)
        qh = quote_height(quote)
        if not previous_question:
            problems.append(f"{quote.quote_id}: no preceding question found")
        if next_question and next_question.idx < quote.idx:
            problems.append(f"{quote.quote_id}: quote is not before next question")
        desired_x = centered_quote_x(quote.width)
        if abs(quote.x - desired_x) > 0.1:
            problems.append(
                f"{quote.quote_id}: quote x={quote.x:.1f}bp is not page-centered at {desired_x:.1f}bp"
            )
        dead_space = 0.0
        if next_span:
            if next_span.page > quote.page:
                dead_space = PAGE_BOTTOM - (quote.y + qh)
            else:
                dead_space = max(0.0, next_span.y - (quote.y + qh))
            if next_span.page > quote.page and dead_space > MAX_ALLOWED_DEAD_SPACE:
                problems.append(f"{quote.quote_id}: leaves {dead_space:.1f}bp dead space before next-page content")
        problems.extend(downstream_row_problems(lines, quote))
        quote_reports.append(
            {
                "id": quote.quote_id,
                "page": quote.page,
                "y": quote.y,
                "x": quote.x,
                "center_x": round(quote.x + quote.width / 2.0, 1),
                "estimated_height": round(qh, 1),
                "next_content_page": next_span.page if next_span else None,
                "dead_space_bp": round(dead_space, 1),
            }
        )

    new_text = "".join(lines)
    if write and new_text != original:
        path.write_text(new_text, encoding="utf-8", newline="")
    return {
        "file": path.relative_to(REPO).as_posix(),
        "quotes": quote_reports,
        "metadata_blocks_added": metadata_changes,
        "linebreaks_normalized": linebreak_changes,
        "horizontal_center_normalized": horizontal_center_changes,
        "reflow_shifts": reflow_shifts,
        "row_flow_repairs": row_flow_repairs,
        "local_spacing_repairs": local_spacing_repairs,
        "problems": problems,
        "changed": new_text != original,
        "ok": not problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate notable quote layout without writing")
    parser.add_argument("--dry-run", action="store_true", help="compute rule-based edits without writing")
    parser.add_argument("--report", type=Path, default=REPO / "tmp" / "notable-quote-layout-report.json")
    args = parser.parse_args()

    per_file = [process_file(path, write=not (args.check or args.dry_run)) for path in sorted(REPO.glob(TEX_GLOB))]
    report = {
        "tex_files": len(per_file),
        "quote_files": sum(1 for item in per_file if item["quotes"]),
        "total_quotes": sum(len(item["quotes"]) for item in per_file),
        "changed_files": sum(1 for item in per_file if item["changed"]),
        "reflowed_quotes": sum(len(item["reflow_shifts"]) for item in per_file),
        "linebreak_normalized_quotes": sum(item["linebreaks_normalized"] for item in per_file),
        "horizontal_centered_quotes": sum(item["horizontal_center_normalized"] for item in per_file),
        "row_flow_repaired_quotes": sum(len(item["row_flow_repairs"]) for item in per_file),
        "local_spacing_repaired_quotes": sum(len(item["local_spacing_repairs"]) for item in per_file),
        "files": per_file,
        "ok": all(item["ok"] for item in per_file),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
