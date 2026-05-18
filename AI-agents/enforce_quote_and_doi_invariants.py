r"""Enforce ALIUS pull-quote and interview-DOI TeX invariants.

Run after regenerating interview reconstructions from reference PDFs. It is idempotent:
- standalone interview sources load hyperref because DOI lines use \href;
- oversized decorative quote placeholders become robust TeX quote macros;
- every interview displays its own BibTeX DOI on page 1 in the citation block as a green hyperlink.
"""

from __future__ import annotations

from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[1]
SPAN_RE = re.compile(
    r"(?P<prefix>\s*\\ALIUSPlacedTextContent\{(?P<x>[^}]*)\}\{(?P<y>[^}]*)\}\{(?P<w>[^}]*)\}"
    r"\{(?P<color>[^}]*)\}\{(?P<font>[^}]*)\}\{(?P<size>[^}]*)\}\{)(?P<text>.*)(?P<suffix>\}\s*)$"
)


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
    return text


def make_doi_line(x: float, y: float, font: str, size: float, doi: str) -> str:
    url = f"https://doi.org/{doi}"
    width = max(170.0, min(300.0, len(url) * size * 0.50))
    return (
        f"  \\ALIUSPlacedTextContent{{{x:.3f}}}{{{y:.3f}}}{{{width:.3f}}}"
        f"{{ALIUSC1F8135}}{{{font}}}{{{size:.3f}}}"
        f"{{\\href{{{url}}}{{{url}}}}}"
    )


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
        rec["sf"] = float(match.group("size"))
        spans.append(rec)
    return spans


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


def enforce_file(path: Path) -> tuple[int, int]:
    doi = bib_doi(path)
    original = path.read_text(encoding="utf-8")
    lines = ensure_preamble(original).splitlines()

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

    first_end = next((idx for idx, line in enumerate(lines) if line.strip() == r"\end{tikzpicture}"), len(lines))
    kept: list[str] = []
    idx = 0
    while idx < len(lines):
        if idx < first_end:
            match = SPAN_RE.match(lines[idx])
            if match and match.group("text") == "h" and idx + 1 < first_end:
                next_match = SPAN_RE.match(lines[idx + 1])
                if next_match and next_match.group("text").startswith("ttps://doi.org/"):
                    idx += 2
                    continue
            if match and is_interview_doi_span(match.group("text")):
                idx += 1
                continue
        kept.append(lines[idx])
        idx += 1
    lines = kept
    first_end = next((idx for idx, line in enumerate(lines) if line.strip() == r"\end{tikzpicture}"), len(lines))
    spans = parse_spans(lines, first_end)

    citation = None
    for rec in spans:
        text = str(rec["text"]).strip()
        if ("Citation:" in text or re.search(r"Cite\s+as:", text, re.I) or text == "Cite") and float(rec["yf"]) < 360:
            citation = rec
            break
    if citation is None:
        raise RuntimeError(f"cannot locate citation block in {path.relative_to(REPO)}")

    citation_y = float(citation["yf"])
    citation_x = float(citation["xf"])
    abstract_ys = [float(rec["yf"]) for rec in spans if float(rec["yf"]) > citation_y and str(rec["text"]).strip() == "Abstract"]
    left_limit = min(320.0, citation_x + 220.0)
    left_green_ys = [
        float(rec["yf"])
        for rec in spans
        if float(rec["yf"]) > citation_y and float(rec["xf"]) < left_limit and rec["color"] == "ALIUSC1F8135"
    ]
    boundary = min(abstract_ys + left_green_ys + [citation_y + 125.0])
    block = [
        rec
        for rec in spans
        if citation_y <= float(rec["yf"]) < boundary
        and float(rec["xf"]) < 385
        and "ALIUSFontLato" in str(rec["font"])
        and rec["color"] != "ALIUSC1F8135"
        and str(rec["text"]).strip() not in {"Abstract", "keywords", "Keywords"}
    ] or [citation]
    last = max(block, key=lambda rec: (float(rec["yf"]), int(rec["idx"])))
    gap = max(11.5, float(citation["sf"]) * 1.18)
    y = float(last["yf"]) + gap
    if y > boundary - 8:
        y = max(float(last["yf"]) + 2.5, boundary - 13)
    size = float(citation["sf"])
    if size > 11.0:
        size = min(size, 10.2)
    lines.insert(int(last["idx"]) + 1, make_doi_line(citation_x, y, str(citation["font"]), size, doi))

    updated = "\n".join(lines) + "\n"
    if updated != original:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return quote_replacements, 1


def main() -> int:
    total_quotes = 0
    total_dois = 0
    for tex_path in sorted(REPO.glob("Interviews/Issue*/*/*.tex")):
        q, d = enforce_file(tex_path)
        total_quotes += q
        total_dois += d
    print(f"enforced {total_dois} DOI citation links; repaired {total_quotes} pull-quote placeholders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
