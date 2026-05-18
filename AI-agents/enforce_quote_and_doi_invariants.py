r"""Enforce ALIUS pull-quote and interview-DOI/citation layout invariants.

Run after regenerating interview reconstructions from reference PDFs. It is idempotent:
- standalone interview sources load hyperref because DOI links use \href;
- oversized decorative quote placeholders become robust TeX quote macros;
- every interview gets a normalized first-page citation panel: citation text starts
  top-left, and the DOI is appended inline as a single unbroken green hyperlink
  in the same APA 7 citation paragraph.
"""

from __future__ import annotations

from pathlib import Path
import math
import re

REPO = Path(__file__).resolve().parents[1]
SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{)(?P<text>.*)(?P<suffix>\}\s*)$"
)
PANEL_BEGIN = "% ALIUS normalized citation panel begin"
PANEL_END = "% ALIUS normalized citation panel end"
PANEL_TEXT_PREFIX = "% ALIUS normalized citation panel text: "
PULL_QUOTE_TEXT_COLORS = {"ALIUSC000000", "ALIUSC595959", "ALIUSC7F7F7F"}


def bib_doi(tex_path: Path) -> str:
    match = re.search(r"doi\s*=\s*\{([^}]+)\}", tex_path.with_suffix(".bib").read_text(encoding="utf-8"), re.I)
    if not match:
        raise RuntimeError(f"missing DOI in {tex_path.with_suffix('.bib').relative_to(REPO)}")
    return match.group(1).strip()


def ensure_preamble(text: str) -> str:
    if r"\usepackage[hidelinks]{hyperref}" not in text:
        text = text.replace(
            r"\usepackage{iftex}" + "\n",
            r"\usepackage{iftex}" + "\n" + r"\usepackage[hidelinks]{hyperref}" + "\n",
            1,
        )
    if r"\providecommand{\ALIUSPullQuoteOpen}" not in text:
        quote_macros = (
            r"\providecommand{\ALIUSPullQuoteOpen}{\textquotedblleft}" + "\n"
            r"\providecommand{\ALIUSPullQuoteClose}{\textquotedblright}" + "\n"
        )
        text = text.replace("\n\\definecolor", "\n" + quote_macros + r"\definecolor", 1)
    if r"\definecolor{ALIUSC1F8135}" not in text:
        text = text.replace("\n\\definecolor", "\n" + r"\definecolor{ALIUSC1F8135}{HTML}{1F8135}" + "\n" + r"\definecolor", 1)
    return text


def strip_existing_panel(lines: list[str]) -> tuple[list[str], str | None, int | None]:
    out: list[str] = []
    saved_text: str | None = None
    saved_index: int | None = None
    i = 0
    while i < len(lines):
        if lines[i].strip() == PANEL_BEGIN:
            if saved_index is None:
                saved_index = len(out)
            i += 1
            while i < len(lines) and lines[i].strip() != PANEL_END:
                stripped = lines[i].strip()
                if stripped.startswith(PANEL_TEXT_PREFIX):
                    saved_text = stripped[len(PANEL_TEXT_PREFIX):]
                i += 1
            if i < len(lines) and lines[i].strip() == PANEL_END:
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out, saved_text, saved_index


def existing_panel_geometry(text: str) -> dict[str, float] | None:
    panel_match = re.search(re.escape(PANEL_BEGIN) + r"(?P<panel>.*?)" + re.escape(PANEL_END), text, re.S)
    if not panel_match:
        return None
    panel = panel_match.group("panel")
    node_match = re.search(
        r"\\node\[anchor=north west[^\]]*\]\s+at\s+\((?P<x>[0-9.]+)bp,-(?P<y>[0-9.]+)bp\)"
        r".*?\\begin\{minipage\}\{(?P<width>[0-9.]+)bp\}",
        panel,
        re.S,
    )
    if not node_match:
        return None
    return {
        "x": float(node_match.group("x")),
        "y": float(node_match.group("y")),
        "width": float(node_match.group("width")),
    }


def tex_unescape_for_comment(text: str) -> str:
    # Comments store the already TeX-safe panel text. This function is named for clarity:
    # we intentionally keep the TeX escapes rather than reconstructing Unicode/plain text.
    return text


def is_interview_doi_span(text: str) -> bool:
    if "10.1038/" in text:
        return False
    return bool(
        r"\href{https://doi.org/10." in text
        or "https://doi.org/10.34700/" in text
        or "https://doi.org/10.5281/" in text
        or "ttps://doi.org/10.5281/" in text
        or re.search(r"doi:\s*10\.34700/", text, re.I)
    )


def is_footer_span(rec: dict[str, object]) -> bool:
    return str(rec["color"]) == "ALIUSC767171" or float(rec["yf"]) > 760.0


def parse_spans_with_pages(lines: list[str]) -> list[dict[str, object]]:
    page = 0
    spans: list[dict[str, object]] = []
    for idx, line in enumerate(lines):
        page_match = re.match(r"% Page (\d+)", line)
        if page_match:
            page = int(page_match.group(1))
        match = SPAN_RE.match(line)
        if not match:
            continue
        rec: dict[str, object] = match.groupdict()
        rec["idx"] = idx
        rec["page"] = page
        rec["xf"] = float(match.group("x"))
        rec["yf"] = float(match.group("y"))
        rec["wf"] = float(match.group("w"))
        rec["sf"] = float(match.group("size"))
        spans.append(rec)
    return spans


def is_pull_quote_text_candidate(rec: dict[str, object], opener: dict[str, object]) -> bool:
    text = str(rec["text"]).strip()
    return (
        int(rec["page"]) == int(opener["page"])
        and int(rec["idx"]) > int(opener["idx"])
        and float(rec["yf"]) >= float(opener["yf"]) - 1.0
        and float(rec["yf"]) <= float(opener["yf"]) + 165.0
        and float(rec["xf"]) >= float(opener["xf"]) + 5.0
        and "ALIUSFontLato" in str(rec["font"])
        and 13.0 <= float(rec["sf"]) <= 18.5
        and str(rec["color"]) in PULL_QUOTE_TEXT_COLORS
        and text not in {"", "References"}
        and "http" not in text
    )


def replace_span_y(line: str, y: float) -> str:
    return re.sub(r"(\\ALIUSPlacedTextContent\{[^}]+\}\{)[^}]+", rf"\g<1>{y:.3f}", line, count=1)


def align_pull_quote_openers(lines: list[str]) -> int:
    """Lower opening decorative quote marks to the first pull-quote text line."""
    spans = parse_spans_with_pages(lines)
    changes = 0
    for opener in spans:
        if opener["text"] != r"\ALIUSPullQuoteOpen":
            continue
        candidates = [rec for rec in spans if is_pull_quote_text_candidate(rec, opener)]
        if not candidates:
            continue
        target_y = min(float(rec["yf"]) for rec in candidates)
        if abs(target_y - float(opener["yf"])) <= 0.5:
            continue
        idx = int(opener["idx"])
        lines[idx] = replace_span_y(lines[idx], target_y)
        changes += 1
    return changes


def parse_spans(lines: list[str], first_end: int) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    for idx in range(first_end):
        match = SPAN_RE.match(lines[idx])
        if not match:
            continue
        rec: dict[str, object] = match.groupdict()
        rec["idx"] = idx
        rec["xf"] = float(match.group("x"))
        rec["yf"] = float(match.group("y"))
        rec["wf"] = float(match.group("w"))
        rec["sf"] = float(match.group("size"))
        spans.append(rec)
    return spans


def starts_citation(text: str) -> bool:
    stripped = text.strip()
    return bool("Citation:" in stripped or re.search(r"Cite\s+as:", stripped, re.I) or stripped == "Cite")


def is_punctuation_token(token: str) -> bool:
    return bool(re.fullmatch(r"[,.;:)]|\\&", token.strip()))


def join_line_tokens(tokens: list[str]) -> str:
    out = ""
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if not out:
            out = tok
        elif is_punctuation_token(tok) or tok.startswith(",") or tok.startswith("."):
            out += tok
        elif out.endswith("(") or out.endswith("-") or out.endswith("/"):
            out += tok
        else:
            out += " " + tok
    return re.sub(r"\s+", " ", out).strip()


def citation_text_from_spans(spans: list[dict[str, object]], citation: dict[str, object], boundary: float, left_limit: float) -> str:
    rows: list[tuple[float, list[dict[str, object]]]] = []
    for rec in spans:
        x = float(rec["xf"])
        y = float(rec["yf"])
        text = str(rec["text"])
        if y < float(citation["yf"]) or y >= boundary:
            continue
        if x >= left_limit:
            continue
        if rec["color"] == "ALIUSC1F8135" or is_interview_doi_span(text):
            continue
        if text.strip() in {"Abstract", "keywords", "Keywords"}:
            continue
        if "ALIUSFontLato" not in str(rec["font"]):
            continue
        for row_y, row in rows:
            if abs(row_y - y) < 1.2:
                row.append(rec)
                break
        else:
            rows.append((y, [rec]))
    rows.sort(key=lambda pair: pair[0])
    line_texts = []
    for _y, row in rows:
        row.sort(key=lambda rec: float(rec["xf"]))
        line_text = join_line_tokens([str(rec["text"]) for rec in row])
        if line_text:
            line_texts.append(line_text)
    text = " ".join(line_texts)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^Citation:\s*", "Cite as: ", text)
    text = re.sub(r"^Cite\s+as:\s*", "Cite as: ", text)
    return text


def panel_lines(x: float, y: float, width: float, height: float, citation_text: str, doi: str) -> list[str]:
    url = f"https://doi.org/{doi}"
    citation_size = 9.2
    chars_per_line = max(28.0, width / 4.25)
    estimated_lines = max(1, math.ceil((len(citation_text) + 1 + len(url)) / chars_per_line))
    panel_height = max(34.0, min(height, estimated_lines * 10.7 + 5.0))
    citation_with_doi = (
        rf"{citation_text} "
        rf"\mbox{{\textcolor{{ALIUSC1F8135}}{{\href{{{url}}}{{{url}}}}}}}"
    )
    return [
        f"  {PANEL_BEGIN}",
        f"  {PANEL_TEXT_PREFIX}{citation_text}",
        f"  \\fill[white] ({x - 1.5:.3f}bp,-{y - 2.0:.3f}bp) rectangle ++({width + 3.0:.3f}bp,-{panel_height + 3.5:.3f}bp);",
        f"  \\node[anchor=north west,inner sep=0pt,outer sep=0pt,text=ALIUSC000000] at ({x:.3f}bp,-{y:.3f}bp) "
        f"{{\\begin{{minipage}}{{{width:.3f}bp}}{{\\ALIUSFontLatoLight\\fontsize{{{citation_size:.3f}bp}}{{10.700bp}}\\selectfont\\raggedright {citation_with_doi}\\par}}\\end{{minipage}}}};",
        f"  {PANEL_END}",
    ]


def enforce_file(path: Path) -> tuple[int, int, int]:
    doi = bib_doi(path)
    original = path.read_text(encoding="utf-8")
    ensured = ensure_preamble(original)
    existing_geom = existing_panel_geometry(ensured)
    lines, saved_panel_text, saved_panel_index = strip_existing_panel(ensured.splitlines())

    quote_replacements = 0
    open_quote = True
    for idx, line in enumerate(lines):
        match = SPAN_RE.match(line)
        if not match:
            continue
        if match.group("text") == "?" and float(match.group("size")) >= 30.0:
            macro = r"\ALIUSPullQuoteOpen" if open_quote else r"\ALIUSPullQuoteClose"
            lines[idx] = f"{match.group('prefix')}{macro}{match.group('suffix')}"
            quote_replacements += 1
            open_quote = not open_quote
    quote_alignments = align_pull_quote_openers(lines)

    first_end = next((idx for idx, line in enumerate(lines) if line.strip() == r"\end{tikzpicture}"), len(lines))
    spans = parse_spans(lines, first_end)

    citation = None
    for rec in spans:
        if starts_citation(str(rec["text"])) and float(rec["yf"]) < 360:
            citation = rec
            break
    if citation is None and existing_geom:
        citation = {
            "xf": existing_geom["x"],
            "yf": existing_geom["y"],
            "wf": existing_geom["width"],
            "text": saved_panel_text or "",
        }
    if citation is None:
        raise RuntimeError(f"cannot locate citation block in {path.relative_to(REPO)}")

    citation_y = float(citation["yf"])
    citation_x = float(citation["xf"])
    # Author/contact column normally starts to the right of the citation block.
    right_candidates = [
        float(rec["xf"])
        for rec in spans
        if float(rec["xf"]) > citation_x + 235 and citation_y - 65 <= float(rec["yf"]) <= citation_y + 100
    ]
    right_col_x = min(right_candidates) if right_candidates else citation_x + 320
    panel_right = min(right_col_x - 10.0, citation_x + 312.0, 520.0)
    panel_width = max(245.0, panel_right - citation_x)
    left_limit = citation_x + panel_width + 8.0
    abstract_ys = [float(rec["yf"]) for rec in spans if float(rec["yf"]) > citation_y and str(rec["text"]).strip() == "Abstract"]
    left_green_ys = [
        float(rec["yf"])
        for rec in spans
        if float(rec["yf"]) > citation_y and float(rec["xf"]) < left_limit and rec["color"] == "ALIUSC1F8135" and not is_interview_doi_span(str(rec["text"]))
    ]
    body_ys = [
        float(rec["yf"])
        for rec in spans
        if citation_y + 20.0 < float(rec["yf"]) < 760.0
        and float(rec["xf"]) < left_limit
        and "ALIUSFontLato" not in str(rec["font"])
        and not is_footer_span(rec)
    ]
    boundary = min(abstract_ys + left_green_ys + body_ys + [citation_y + 124.0])
    panel_height = max(46.0, min(92.0, boundary - citation_y - 8.0))

    citation_text = tex_unescape_for_comment(saved_panel_text) if saved_panel_text else citation_text_from_spans(spans, citation, boundary, left_limit)
    if not citation_text:
        raise RuntimeError(f"empty citation text in {path.relative_to(REPO)}")

    # Remove old left-column citation/DOI fragments but keep the right author/contact column intact.
    kept: list[str] = []
    idx = 0
    insert_at: int | None = saved_panel_index
    while idx < len(lines):
        if idx < first_end:
            match = SPAN_RE.match(lines[idx])
            if match:
                x = float(match.group("x"))
                y = float(match.group("y"))
                text = match.group("text")
                if insert_at is None and starts_citation(text):
                    insert_at = len(kept)
                if y >= citation_y and y < boundary and x < left_limit and (
                    is_interview_doi_span(text)
                    or ("ALIUSFontLato" in match.group("font") and match.group("color") != "ALIUSC1F8135")
                ):
                    idx += 1
                    continue
                if text == "h" and idx + 1 < first_end:
                    next_match = SPAN_RE.match(lines[idx + 1])
                    if next_match and next_match.group("text").startswith("ttps://doi.org/"):
                        idx += 2
                        continue
        kept.append(lines[idx])
        idx += 1
    lines = kept
    if insert_at is None:
        raise RuntimeError(f"cannot determine panel insertion point in {path.relative_to(REPO)}")
    lines[insert_at:insert_at] = panel_lines(citation_x, citation_y, panel_width, panel_height, citation_text, doi)

    updated = "\n".join(lines) + "\n"
    if updated != original:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return quote_replacements, quote_alignments, 1


def main() -> int:
    total_quotes = 0
    total_quote_alignments = 0
    total_panels = 0
    for tex_path in sorted(REPO.glob("Interviews/Issue*/*/*.tex")):
        q, qa, d = enforce_file(tex_path)
        total_quotes += q
        total_quote_alignments += qa
        total_panels += d
    print(
        f"enforced {total_panels} normalized citation panels; "
        f"repaired {total_quotes} pull-quote placeholders; "
        f"aligned {total_quote_alignments} opening pull quotes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
