#!/usr/bin/env python3
r"""
Rebuild ALIUS interview TeX files from off-repo reference PDFs.

This is a reconstruction aid, not a build dependency: it reads reference PDFs
from a temporary/cache location, infers the Word-like page layout (text spans,
fonts, colours, and simple vector rectangles), and writes native TeX that
recreates the pages without \includepdf or committed original-PDF assets.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from io import BytesIO
from typing import Any

import fitz  # PyMuPDF
from ftfy import fix_text
from PIL import Image, ImageChops, ImageStat


REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    Path(os.environ.get("TEMP", ""))
    / "alius-original-reference-pdfs"
    / "manifest.json"
)


def tex_escape(text: str) -> str:
    """Escape text for LuaLaTeX while preserving Unicode typography."""

    text = normalize_extracted_text(text)
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "%": r"\%",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "\u00a0": " ",
        "\u202f": " ",
        "\u00ad": "",
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
    }
    cleaned: list[str] = []
    for ch in text:
        if ch in replacements:
            cleaned.append(replacements[ch])
        elif ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F:
            # PDF text extraction can surface Word/private control bytes. They
            # have no printable visual footprint and make LuaTeX abort.
            continue
        else:
            cleaned.append(ch)
    return "".join(cleaned)


def normalize_extracted_text(text: str) -> str:
    """Repair common Word/PDF mojibake before TeX escaping."""

    manual = {
        "Ã¢â‚¬â€": "â€”",
        "Ã¢â‚¬â€œ": "â€“",
        "Ã¢â‚¬Å“": "â€œ",
        "Ã¢â‚¬\x9d": "â€",
        "Ã¢â‚¬Â": "â€",
        "Ã¢â‚¬Ëœ": "â€˜",
        "Ã¢â‚¬â„¢": "â€™",
        "Ã¢â‚¬Â¦": "â€¦",
        "Ã‚Â°": "Â°",
        "Ã‚ ": " ",
        "Ã‚": "",
        # Issue 6 uses an embedded Word subset font whose ToUnicode map leaks
        # ligature-like private glyphs. These must be normalized in the source:
        # LuaLaTeX otherwise faithfully prints the extraction artifact.
        "\u025c": "q",
        "\u0278": "t",
        "\u02ae": "Th",
        "\u02b0": "ff",
        "\u02b4": "ffi",
        "\u02be": "ft",
        "\u02bf": "fi",
        "\u02c0": "fl",
        "\u02c1": "fi",
        "\u02d9": "Th",
        "\u02ef": "gy",
        "\u068d": "-",
        "\u08bc": "ti",
        "\u099e": "ti",
        "ãNEUROSCI": "JNEUROSCI",
        "'ps://": "ttps://",
        "'p://doi.org/10.5281/10.5281/": "ttps://doi.org/10.5281/",
        "bulle\u099en": "bulletin",
        "bulle\u08bcn": "bulletin",
    }
    for bad, good in manual.items():
        text = text.replace(bad, good)
    return fix_text(text)


def color_name(value: int) -> str:
    return f"ALIUSC{value:06X}"


def color_hex(value: int) -> str:
    return f"{value & 0xFFFFFF:06X}"


def normalize_color(value: int) -> int:
    """Collapse near-black extraction noise into canonical black."""

    value = value & 0xFFFFFF
    if value <= 0x00000F:
        return 0
    return value


def drawing_color_name(rgb: tuple[float, float, float] | None) -> str:
    if rgb is None:
        return "black"
    r, g, b = [max(0, min(255, round(c * 255))) for c in rgb]
    return color_name((r << 16) | (g << 8) | b)


def font_macro(font: str) -> str:
    f = font.lower()
    if "lato" in f and "light" in f and "italic" in f:
        return r"\ALIUSFontLatoLightItalic"
    if "lato" in f and "light" in f:
        return r"\ALIUSFontLatoLight"
    if "lato" in f and "italic" in f:
        return r"\ALIUSFontLatoItalic"
    if "lato" in f:
        return r"\ALIUSFontLatoRegular"
    if "cormorant" in f and "italic" in f:
        return r"\ALIUSFontCormorantItalic"
    if "cormorant" in f and "bold" in f:
        return r"\ALIUSFontCormorantBold"
    if "cormorant" in f and "medium" in f:
        return r"\ALIUSFontCormorantMedium"
    if "cormorant" in f and "light" in f:
        return r"\ALIUSFontCormorantLight"
    if "cormorant" in f:
        return r"\ALIUSFontCormorantRegular"
    if "times" in f:
        return r"\ALIUSFontTimes"
    if "calibri" in f:
        return r"\ALIUSFontCalibri"
    if "cambria" in f:
        return r"\ALIUSFontCambria"
    if "garamond" in f and "italic" in f:
        return r"\ALIUSFontCormorantItalic"
    if "garamond" in f:
        return r"\ALIUSFontCormorantRegular"
    if "symbol" in f or "wingdings" in f:
        return r"\ALIUSFontSymbolFallback"
    # Later issues contain embedded Word-subset font names. They are usually
    # body/header serif faces, so Cormorant is a closer fallback than Latin Modern.
    if font.startswith("___WRD_EMBED_SUB_"):
        return r"\ALIUSFontCormorantRegular"
    return r"\ALIUSFontCormorantRegular"


def extract_commented_abstract(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^%\s*\\section\*\{Abstract\}", line):
            start = i
            break
    if start is None:
        return []
    block: list[str] = []
    for line in lines[start:]:
        if line.startswith("% --- End draft abstract"):
            break
        if line.startswith("%"):
            block.append(line)
            continue
        break
    return block


def image_is_solid(image_bytes: bytes) -> bool:
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        return all(lo == hi for lo, hi in image.getextrema())
    except Exception:
        return False


def collect_page_elements(page: fitz.Page) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[int], set[int]]:
    spans: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    colors: set[int] = set()
    fonts_seen: set[int] = set()
    data = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
    for block_index, block in enumerate(data.get("blocks", [])):
        if block.get("type") == 1 and block.get("image"):
            image_bytes = block["image"]
            # Word often emits solid-black image masks for decorative quotation
            # marks. Including those as raster boxes would be visually worse than
            # omitting them; non-solid blocks are actual article images/figures.
            if image_is_solid(image_bytes):
                continue
            x0, y0, x1, y1 = [float(v) for v in block.get("bbox", (0, 0, 0, 0))]
            if x1 <= x0 or y1 <= y0:
                continue
            images.append(
                {
                    "block": block_index,
                    "x": x0,
                    "y": y0,
                    "w": x1 - x0,
                    "h": y1 - y0,
                    "bytes": image_bytes,
                }
            )
            continue
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                raw = span.get("text", "")
                if not raw or not raw.strip():
                    continue
                text = raw.strip()
                bbox = span.get("bbox")
                if not bbox:
                    continue
                x0, y0, x1, y1 = [float(v) for v in bbox]
                width = max(0.2, x1 - x0)
                size = float(span.get("size", 10.0))
                color = normalize_color(int(span.get("color", 0)))
                colors.add(color)
                flags = int(span.get("flags", 0))
                fonts_seen.add(flags)
                spans.append(
                    {
                        "x": x0,
                        "y": y0,
                        "w": width,
                        "h": max(0.2, y1 - y0),
                        "size": size,
                        "color": color,
                        "font": span.get("font", ""),
                        "text": text,
                    }
                )
    spans.sort(key=lambda s: (s["y"], s["x"]))
    images.sort(key=lambda s: (s["y"], s["x"]))
    return spans, images, colors, fonts_seen


def rect_commands(page: fitz.Page, color_accumulator: set[int]) -> list[str]:
    commands: list[str] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        stroke = drawing.get("color")
        rect = drawing.get("rect")
        if rect is None:
            continue
        x0, y0, x1, y1 = rect
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            continue
        if fill is not None:
            r, g, b = [max(0, min(255, round(c * 255))) for c in fill]
            val = (r << 16) | (g << 8) | b
            color_accumulator.add(val)
            commands.append(
                rf"\fill[{color_name(val)}] ({x0:.3f}bp,-{y0:.3f}bp) rectangle ++({w:.3f}bp,-{h:.3f}bp);"
            )
        elif stroke is not None:
            r, g, b = [max(0, min(255, round(c * 255))) for c in stroke]
            val = (r << 16) | (g << 8) | b
            color_accumulator.add(val)
            line_w = float(drawing.get("width") or 0.5)
            commands.append(
                rf"\draw[{color_name(val)},line width={line_w:.3f}bp] ({x0:.3f}bp,-{y0:.3f}bp) rectangle ++({w:.3f}bp,-{h:.3f}bp);"
            )
    return commands


def repair_decorative_quote_marks(
    pages: list[tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]],
) -> None:
    """Use typographic marks for oversized pull-quote glyphs.

    PyMuPDF extracts Word's decorative opening/closing quote glyphs as plain
    ASCII double quotes or question marks, depending on the embedded font's
    ToUnicode map. Emit robust TeX quote macros while leaving normal in-line
    quotes untouched.
    """

    open_quote = True
    for spans, _rects, _images in pages:
        for span in spans:
            if span.get("text") in {'"', "?"} and float(span.get("size", 0.0)) >= 30.0:
                span["text"] = "__ALIUS_PULLQUOTE_OPEN__" if open_quote else "__ALIUS_PULLQUOTE_CLOSE__"
                open_quote = not open_quote


def preamble(width: float, height: float, colors: set[int]) -> list[str]:
    lines = [
        r"% !TeX program = lualatex",
        r"% ALIUS Bulletin native visual reconstruction source.",
        r"% Generated from off-repo reference layout data; does not include or input a pre-existing article PDF.",
        r"\ifdefined\ALIUSIssueBuild",
        r"\else",
        r"\documentclass{article}",
        rf"\usepackage[paperwidth={width:.4f}bp,paperheight={height:.4f}bp,margin=0bp]{{geometry}}",
        r"\usepackage{graphicx}",
        r"\usepackage{xcolor}",
        r"\usepackage{tikz}",
        r"\usepackage{iftex}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\ifPDFTeX",
        r"  \usepackage[T1]{fontenc}",
        r"  \usepackage[utf8]{inputenc}",
        r"  \usepackage{textcomp}",
        r"  \usepackage{amssymb}",
        r"\else",
        r"  \usepackage{fontspec}",
        r"\fi",
        r"\pagestyle{empty}",
        r"\fi",
        r"\ifPDFTeX",
        r"  \\providecommand{\\ALIUSDeclareUnicodeFallbacks}{%",
        r"    \\DeclareUnicodeCharacter{00AC}{\\ensuremath{\\neg}}%",
        r"    \\DeclareUnicodeCharacter{00BE}{\\ensuremath{\\frac{3}{4}}}%",
        r"    \\DeclareUnicodeCharacter{0101}{\\=a}%",
        r"    \\DeclareUnicodeCharacter{0107}{\\\'c}%",
        r"    \\DeclareUnicodeCharacter{012B}{\\=\\i}%",
        r"    \\DeclareUnicodeCharacter{0131}{\\i}%",
        r"    \\DeclareUnicodeCharacter{0142}{\\l}%",
        r"    \\DeclareUnicodeCharacter{015B}{\\\'s}%",
        r"    \\DeclareUnicodeCharacter{016B}{\\=u}%",
        r"    \\DeclareUnicodeCharacter{025C}{\\ensuremath{\\epsilon}}%",
        r"    \\DeclareUnicodeCharacter{0278}{\\ensuremath{\\phi}}%",
        r"    \\DeclareUnicodeCharacter{02AE}{Th}%",
        r"    \\DeclareUnicodeCharacter{02B0}{ff}%",
        r"    \\DeclareUnicodeCharacter{02B4}{ffi}%",
        r"    \\DeclareUnicodeCharacter{02BE}{\'}%",
        r"    \\DeclareUnicodeCharacter{02BF}{fi}%",
        r"    \\DeclareUnicodeCharacter{02C0}{fl}%",
        r"    \\DeclareUnicodeCharacter{02C1}{fi}%",
        r"    \\DeclareUnicodeCharacter{02D9}{Th}%",
        r"    \\DeclareUnicodeCharacter{02EF}{gy}%",
        r"    \\DeclareUnicodeCharacter{0394}{\\ensuremath{\\Delta}}%",
        r"    \\DeclareUnicodeCharacter{03B2}{\\ensuremath{\\beta}}%",
        r"    \\DeclareUnicodeCharacter{03BA}{\\ensuremath{\\kappa}}%",
        r"    \\DeclareUnicodeCharacter{068D}{-}%",
        r"    \\DeclareUnicodeCharacter{08BC}{ti}%",
        r"    \\DeclareUnicodeCharacter{099E}{ti}%",
        r"    \\DeclareUnicodeCharacter{1E43}{\\d{m}}%",
        r"    \\DeclareUnicodeCharacter{1E47}{\\d{n}}%",
        r"    \\DeclareUnicodeCharacter{1E63}{\\d{s}}%",
        r"    \\DeclareUnicodeCharacter{201C}{``}%",
        r"    \\DeclareUnicodeCharacter{201D}{''}%",
        r"    \\DeclareUnicodeCharacter{2260}{\\ensuremath{\\neq}}%",
        r"    \\DeclareUnicodeCharacter{25A1}{\\ensuremath{\\square}}%",
        r"  }%",
        r"  \\ifdefined\\ALIUSIssueBuild\\else\\ALIUSDeclareUnicodeFallbacks\\fi",
        r"  \providecommand{\ALIUSFontLatoLight}{\fontfamily{lato-LF}\fontseries{l}\selectfont}",
        r"  \providecommand{\ALIUSFontLatoRegular}{\fontfamily{lato-LF}\fontseries{m}\selectfont}",
        r"  \providecommand{\ALIUSFontLatoItalic}{\fontfamily{lato-LF}\fontseries{m}\itshape}",
        r"  \providecommand{\ALIUSFontLatoLightItalic}{\fontfamily{lato-LF}\fontseries{l}\itshape}",
        r"  \providecommand{\ALIUSFontCormorantRegular}{\fontfamily{CormorantGaramond-LF}\fontseries{m}\selectfont}",
        r"  \providecommand{\ALIUSFontCormorantLight}{\fontfamily{CormorantGaramond-LF}\fontseries{l}\selectfont}",
        r"  \providecommand{\ALIUSFontCormorantMedium}{\fontfamily{CormorantGaramond-LF}\fontseries{medium}\selectfont}",
        r"  \providecommand{\ALIUSFontCormorantBold}{\fontfamily{CormorantGaramond-LF}\fontseries{b}\selectfont}",
        r"  \providecommand{\ALIUSFontCormorantItalic}{\fontfamily{CormorantGaramond-LF}\fontseries{m}\itshape}",
        r"  \providecommand{\ALIUSFontTimes}{\fontfamily{ptm}\selectfont}",
        r"  \providecommand{\ALIUSFontCalibri}{\fontfamily{phv}\selectfont}",
        r"  \providecommand{\ALIUSFontCambria}{\fontfamily{ptm}\selectfont}",
        r"  \providecommand{\ALIUSFontSymbolFallback}{\fontfamily{ptm}\selectfont}",
        r"\else",
        r"  \providecommand{\ALIUSFontLatoLight}{\fontspec{Lato Light}}",
        r"  \providecommand{\ALIUSFontLatoRegular}{\fontspec{Lato Regular}}",
        r"  \providecommand{\ALIUSFontLatoItalic}{\fontspec{Lato Italic}}",
        r"  \providecommand{\ALIUSFontLatoLightItalic}{\fontspec{Lato Light Italic}}",
        r"  \providecommand{\ALIUSFontCormorantRegular}{\fontspec{Cormorant Garamond Regular}}",
        r"  \providecommand{\ALIUSFontCormorantLight}{\fontspec{Cormorant Garamond Light}}",
        r"  \providecommand{\ALIUSFontCormorantMedium}{\fontspec{Cormorant Garamond Medium}}",
        r"  \providecommand{\ALIUSFontCormorantBold}{\fontspec{Cormorant Garamond Bold}}",
        r"  \providecommand{\ALIUSFontCormorantItalic}{\fontspec{Cormorant Garamond Italic}}",
        r"  \providecommand{\ALIUSFontTimes}{\fontspec{Times New Roman}}",
        r"  \providecommand{\ALIUSFontCalibri}{\fontspec{Calibri}}",
        r"  \providecommand{\ALIUSFontCambria}{\fontspec{Cambria}}",
        r"  \providecommand{\ALIUSFontSymbolFallback}{\fontspec{Times New Roman}}",
        r"\fi",
        r"\providecommand{\ALIUSPullQuoteOpen}{\textquotedblleft}",
        r"\providecommand{\ALIUSPullQuoteClose}{\textquotedblright}",
        r"\providecommand{\ALIUSNotableQuoteAt}[4]{%",
        r"  \node[anchor=north west,inner sep=0pt,outer sep=0pt,text=ALIUSC595959] at (#1bp,-#2bp) {%",
        r"    \begin{minipage}{#3bp}%",
        r"      {\ALIUSFontLatoLight\fontsize{15.000bp}{18.000bp}\selectfont\raggedright{\textcolor{ALIUSC7F7F7F}{\ALIUSFontCormorantLight\fontsize{32.000bp}{32.000bp}\selectfont\ALIUSPullQuoteOpen}}\hspace{2.000bp}#4\hspace{2.000bp}{\textcolor{ALIUSC7F7F7F}{\ALIUSFontCormorantLight\fontsize{32.000bp}{32.000bp}\selectfont\ALIUSPullQuoteClose}}\par}%",
        r"    \end{minipage}%",
        r"  };%",
        r"}",
        r"\providecommand{\ALIUSMaybeNotableQuoteAt}[4]{%",
        r"  \if\relax\detokenize{#4}\relax\else\ALIUSNotableQuoteAt{#1}{#2}{#3}{#4}\fi%",
        r"}",
        r"\providecommand{\ALIUSRefAnchor}[1]{\hypertarget{#1}{}}",
        r"\providecommand{\ALIUSCitationLink}[2]{\hyperlink{#1}{#2}}",
    ]
    for c in sorted(colors):
        lines.append(rf"\definecolor{{{color_name(c)}}}{{HTML}}{{{color_hex(c)}}}")
    lines += [
        r"\providecommand{\ALIUSPlacedText}[6]{%",
        r"  \node[anchor=north west,inner sep=0pt,outer sep=0pt,text=#4] at (#1bp,-#2bp) {%",
        r"    \resizebox{#3bp}{!}{{#5\fontsize{#6bp}{#6bp}\selectfont #6\kern0pt}}%",
        r"  };%",
        r"}",
        r"\providecommand{\ALIUSPlacedTextContent}[7]{%",
        r"  \node[anchor=north west,inner sep=0pt,outer sep=0pt,text=#4] at (#1bp,-#2bp) {%",
        r"    \resizebox{#3bp}{!}{{#5\fontsize{#6bp}{#6bp}\selectfont #7}}%",
        r"  };%",
        r"}",
        "",
    ]
    return lines


def assert_child_path(child: Path, parent: Path) -> None:
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    try:
        child_resolved.relative_to(parent_resolved)
    except ValueError as exc:
        raise RuntimeError(f"refusing to write outside {parent_resolved}: {child_resolved}") from exc


def prepare_image_assets(
    item: dict[str, Any],
    pages: list[tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]],
) -> dict[tuple[int, int], str]:
    """Write extracted article images as lossless PNG assets beside the interview."""

    tex_path = REPO / item["tex"]
    assets_dir = tex_path.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    assert_child_path(assets_dir, tex_path.parent)

    for stale in assets_dir.glob("alius-extracted-image-*.png"):
        assert_child_path(stale, assets_dir)
        stale.unlink()

    image_refs: dict[tuple[int, int], str] = {}
    for page_index, (_, images, _) in enumerate(pages, start=1):
        for image in images:
            asset_name = f"alius-extracted-image-p{page_index:03d}-b{int(image['block']):03d}.png"
            asset_path = assets_dir / asset_name
            assert_child_path(asset_path, assets_dir)
            pil_image = Image.open(BytesIO(image["bytes"]))
            # Preserve the original pixel dimensions and samples, but use PNG
            # as the repository-side container so the asset itself is lossless.
            if pil_image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                pil_image = pil_image.convert("RGB")
            pil_image.save(asset_path, format="PNG", compress_level=9)
            image_refs[(page_index, image["block"])] = asset_path.relative_to(REPO).as_posix()
    return image_refs


def apply_manual_overrides(item: dict[str, Any], pages: list[tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]]) -> None:
    """Apply editorial corrections that intentionally differ from the reference PDF."""

    if not pages:
        return

    if item["tex"] == "Interviews/Issue02/Friston/Friston.tex":
        spans = pages[0][0]
        for span in spans:
            if span["text"] == "Karl Friston" and 70 <= span["x"] <= 80 and 130 <= span["y"] <= 145:
                span["text"] = "Karl Friston, Martin Fortier, Matthieu Koroma and Rapha\u00ebl Milli\u00e8re"
                span["w"] = 268.0
            elif span["text"] == "Karl Friston" and 345 <= span["x"] <= 360 and 150 <= span["y"] <= 165:
                span["text"] = "Karl Friston, Martin Fortier, Matthieu Koroma & Rapha\u00ebl Milli\u00e8re"
                span["w"] = 168.0
            elif span["text"].startswith("Citation: Friston, K. (2018)."):
                span["text"] = "Citation: Friston, K., Fortier, M., Koroma, M. & Milli\u00e8re, R. (2018)."
                span["w"] = 268.941
            elif span["text"] == "autobiography.":
                span["text"] = "Am I autistic? An intellectual autobiography."
                span["w"] = 175.0
            elif span["text"] == "ALIUS Bulletin":
                span["x"] = 253.0
                span["w"] = 57.395
            elif span["text"] == ", 2, 45-52.":
                span["x"] = 310.5
                span["w"] = 42.082

    if item["tex"] == "Interviews/Issue05/Canna_Seligman_Koroma/Canna_Seligman_Koroma.tex":
        for spans, _images, _rects in pages:
            for span in spans:
                if span["text"] == "\u2013" and 315 <= span["x"] <= 322 and 30 <= span["y"] <= 42:
                    span["color"] = 0x767171

    if item["tex"] == "Interviews/Issue07/Changeux_Dumas/Changeux_Dumas.tex":
        for spans, _images, _rects in pages:
            for span in spans:
                if span["text"] == "\u2014" and span["color"] == 0x221E1F and span["y"] >= 235:
                    span["color"] = 0x000000


def generate_tex_for_item(item: dict[str, Any]) -> str:
    tex_path = REPO / item["tex"]
    commented_abstract = extract_commented_abstract(tex_path)
    doc = fitz.open(item["ref"])
    if len(doc) == 0:
        raise ValueError(f"empty PDF: {item['ref']}")
    width = float(doc[0].rect.width)
    height = float(doc[0].rect.height)

    pages: list[tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]] = []
    colors: set[int] = set()
    for page in doc:
        spans, images, page_colors, _ = collect_page_elements(page)
        colors.update(page_colors)
        rects = rect_commands(page, colors)
        pages.append((spans, images, rects))

    repair_decorative_quote_marks(pages)
    apply_manual_overrides(item, pages)

    lines = preamble(width, height, colors)
    image_refs = prepare_image_assets(item, pages)
    if commented_abstract:
        lines.append("% --- Draft abstract retained as comments; not rendered in reconstruction. ---")
        lines.extend(commented_abstract)
        lines.append("% --- End draft abstract. ---")
        lines.append("")
    lines += [
        r"\ifdefined\ALIUSIssueBuild",
        r"\else",
        r"\begin{document}",
        r"\fi",
        "",
    ]

    for i, (spans, images, rects) in enumerate(pages, start=1):
        lines += [
            rf"% Page {i}",
            r"\thispagestyle{empty}",
            r"\noindent\begin{tikzpicture}[remember picture,overlay,x=1bp,y=1bp,shift={(current page.north west)}]",
        ]
        lines.extend("  " + cmd for cmd in rects)
        for image in images:
            asset_rel = image_refs[(i, image["block"])]
            lines.append(
                "  "
                + rf"\node[anchor=north west,inner sep=0pt,outer sep=0pt] at ({image['x']:.3f}bp,-{image['y']:.3f}bp) "
                + rf"{{\includegraphics[width={image['w']:.3f}bp,height={image['h']:.3f}bp]{{{asset_rel}}}}};"
            )
        for span in spans:
            if span["text"] == "__ALIUS_PULLQUOTE_OPEN__":
                text = r"\ALIUSPullQuoteOpen"
            elif span["text"] == "__ALIUS_PULLQUOTE_CLOSE__":
                text = r"\ALIUSPullQuoteClose"
            else:
                text = tex_escape(span["text"])
            # Very small spans are usually extraction artefacts; retain page numbers
            # and punctuation by only suppressing genuinely invisible widths.
            if not text:
                continue
            lines.append(
                "  "
                + rf"\ALIUSPlacedTextContent{{{span['x']:.3f}}}{{{span['y']:.3f}}}{{{span['w']:.3f}}}{{{color_name(span['color'])}}}{{{font_macro(span['font'])}}}{{{span['size']:.3f}}}{{{text}}}"
            )
        lines += [
            r"\end{tikzpicture}",
            r"\null",
        ]
        if i != len(pages):
            lines.append(r"\newpage")
        lines.append("")

    lines += [
        r"\ifdefined\ALIUSIssueBuild",
        r"\clearpage",
        r"\expandafter\endinput",
        r"\fi",
        r"\end{document}",
        "",
    ]
    return "\n".join(lines)


def safe_build_dir(tex_rel: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", tex_rel.replace("\\", "/"))
    return REPO / "tmp" / "interview-reconstruction-build" / slug


def compile_tex(tex_rel: str) -> tuple[Path | None, str]:
    tex_path = REPO / tex_rel
    out_dir = safe_build_dir(tex_rel)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / (tex_path.stem + ".pdf")
    if pdf.exists():
        pdf.unlink()
    cmd = [
        "lualatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={out_dir}",
        str(tex_path.relative_to(REPO)).replace("\\", "/"),
    ]
    proc = subprocess.run(cmd, cwd=REPO, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return (pdf if proc.returncode == 0 and pdf.exists() else None), proc.stdout


def pixmap_to_image(page: fitz.Page, zoom: float) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def compare_pdfs(ref: str, gen: Path, zoom: float = 1.0) -> dict[str, Any]:
    ref_doc = fitz.open(ref)
    gen_doc = fitz.open(str(gen))
    page_count = min(len(ref_doc), len(gen_doc))
    changed_fracs: list[float] = []
    mean_abs: list[float] = []
    for i in range(page_count):
        a = pixmap_to_image(ref_doc[i], zoom)
        b = pixmap_to_image(gen_doc[i], zoom)
        if a.size != b.size:
            b = b.resize(a.size)
        diff = ImageChops.difference(a, b)
        gray = diff.convert("L")
        stat = ImageStat.Stat(gray)
        mean_abs.append(float(stat.mean[0]))
        mask = gray.point(lambda px: 255 if px > 25 else 0)
        changed = ImageStat.Stat(mask).sum[0] / 255
        changed_fracs.append(changed / (mask.size[0] * mask.size[1]))
    return {
        "ref_pages": len(ref_doc),
        "gen_pages": len(gen_doc),
        "page_mismatch": len(ref_doc) != len(gen_doc),
        "mean_changed": sum(changed_fracs) / len(changed_fracs) if changed_fracs else math.nan,
        "max_changed": max(changed_fracs) if changed_fracs else math.nan,
        "mean_abs": sum(mean_abs) / len(mean_abs) if mean_abs else math.nan,
        "max_abs": max(mean_abs) if mean_abs else math.nan,
    }


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--target", help="substring filter for tex path")
    parser.add_argument("--write", action="store_true", help="overwrite interview .tex files")
    parser.add_argument("--compile", action="store_true", help="compile generated/interview TeX with LuaLaTeX")
    parser.add_argument("--compare", action="store_true", help="compare compiled PDFs against reference PDFs")
    parser.add_argument("--report", type=Path, default=REPO / "tmp" / "interview-reconstruction-report.csv")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    if args.target:
        manifest = [item for item in manifest if args.target.lower() in item["tex"].lower()]
    if not manifest:
        print("No manifest items selected.", file=sys.stderr)
        return 2

    rows: list[dict[str, Any]] = []
    for item in manifest:
        tex_rel = item["tex"]
        print(f"==> {tex_rel}")
        if args.write:
            tex = generate_tex_for_item(item)
            path = REPO / tex_rel
            path.write_text(tex, encoding="utf-8", newline="\n")
            print(f"    wrote {path}")
        pdf: Path | None = None
        compile_log = ""
        if args.compile or args.compare:
            pdf, compile_log = compile_tex(tex_rel)
            if pdf is None:
                print("    compile failed")
                rows.append({"tex": tex_rel, "compile": "failed"})
                (safe_build_dir(tex_rel) / "compile.log").write_text(compile_log, encoding="utf-8", errors="replace")
                continue
            print(f"    compiled {pdf}")
        row: dict[str, Any] = {"tex": tex_rel, "compile": "ok" if pdf else "not-run"}
        if args.compare and pdf is not None:
            metrics = compare_pdfs(item["ref"], pdf)
            row.update(metrics)
            print(
                f"    pages {metrics['gen_pages']}/{metrics['ref_pages']} "
                f"mean_changed={metrics['mean_changed']:.4%} max_changed={metrics['max_changed']:.4%}"
            )
        rows.append(row)

    if rows and (args.compare or args.compile):
        args.report.parent.mkdir(parents=True, exist_ok=True)
        keys = sorted({k for row in rows for k in row.keys()})
        with args.report.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)
        print(f"report: {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
