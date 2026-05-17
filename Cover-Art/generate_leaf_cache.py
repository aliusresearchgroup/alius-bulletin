"""Regenerate the vector ALIUS leaf assets used by the cover renderer.

The historical static leaf SVG is an SVG wrapper around three embedded PNG
layers. The animated brand source contains the same three leaves as real SVG
paths. This script extracts the first animation frame into a static vector SVG
and builds an Overleaf-safe vector PDF cache with pdfLaTeX/TikZ.
"""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_SVG = ROOT / "source-assets" / "logo-ALIUS-original-animated-leaf.svg"
STATIC_SVG = ROOT / "assets" / "alius-leaf.svg"
GENERATED_DIR = ROOT / "generated"
GENERATED_TEX = GENERATED_DIR / "alius-leaf-from-svg.tex"
GENERATED_PDF = GENERATED_DIR / "alius-leaf-from-svg.pdf"

SVG_NS = "{http://www.w3.org/2000/svg}"
LEAF_COLORS = {
    "middle-leaf": "AliusLeafMiddle",
    "left-leaf": "AliusLeafLeft",
    "right-leaf": "AliusLeafRight",
}


def _paths_from_source() -> list[tuple[str, str, str]]:
    root = ET.fromstring(SOURCE_SVG.read_text(encoding="utf-8"))
    paths: list[tuple[str, str, str]] = []
    for path in root.findall(f".//{SVG_NS}path"):
        leaf_id = path.attrib["id"]
        fill = path.attrib["fill"].lstrip("#")
        d = path.attrib["d"]
        if leaf_id in LEAF_COLORS:
            paths.append((leaf_id, fill, d))

    expected = ["middle-leaf", "left-leaf", "right-leaf"]
    if [leaf_id for leaf_id, _, _ in paths] != expected:
        raise ValueError("Animated SVG did not contain the expected leaf paths")
    return paths


def _write_static_svg(paths: list[tuple[str, str, str]]) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg width="100%" height="100%" viewBox="0 0 1023 1111" version="1.1"',
        '     xmlns="http://www.w3.org/2000/svg" xml:space="preserve"',
        '     style="fill-rule:evenodd;clip-rule:evenodd;stroke-linejoin:round;stroke-miterlimit:1.41421;overflow:hidden;">',
        "  <title>ALIUS vector leaf logo</title>",
        "  <desc>Three static SVG paths extracted from the ALIUS animated vector leaf source; overlap tones use multiply blending.</desc>",
        "  <style><![CDATA[",
        "    #alius-logo { isolation: isolate; }",
        "    .leaf { mix-blend-mode: multiply; }",
        "  ]]></style>",
        '  <g id="alius-logo">',
    ]
    for leaf_id, fill, d in paths:
        lines.append(f'    <path id="{leaf_id}" class="leaf" fill="#{fill}" d="{d}"/>')
    lines.extend(["  </g>", "</svg>", ""])
    STATIC_SVG.write_text("\n".join(lines), encoding="utf-8")


def _write_pdf_source(paths: list[tuple[str, str, str]]) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\documentclass{article}",
        r"\usepackage[paperwidth=1023bp,paperheight=1111bp,margin=0bp]{geometry}",
        r"\usepackage{xcolor}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{svg.path}",
        r"\pagestyle{empty}",
    ]
    for leaf_id, fill, _ in paths:
        lines.append(rf"\definecolor{{{LEAF_COLORS[leaf_id]}}}{{HTML}}{{{fill}}}")
    lines.extend(
        [
            r"\begin{document}",
            r"\noindent\begin{tikzpicture}[x=1bp,y=1bp]",
            r"\useasboundingbox (0,0) rectangle (1023,1111);",
            r"\begin{scope}[yshift=1111bp,yscale=-1]",
        ]
    )
    for leaf_id, _, d in paths:
        lines.append(r"\begin{scope}[blend mode=multiply]")
        lines.append(rf"\path[fill={LEAF_COLORS[leaf_id]}] svg {{{d}}};")
        lines.append(r"\end{scope}")
    lines.extend([r"\end{scope}", r"\end{tikzpicture}", r"\end{document}", ""])
    GENERATED_TEX.write_text("\n".join(lines), encoding="ascii")


def _build_pdf() -> None:
    subprocess.run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={GENERATED_DIR}",
            str(GENERATED_TEX),
        ],
        cwd=ROOT.parent,
        check=True,
    )
    for suffix in [".aux", ".log"]:
        build_file = GENERATED_TEX.with_suffix(suffix)
        if build_file.exists():
            build_file.unlink()


def main() -> None:
    if not SOURCE_SVG.exists():
        raise FileNotFoundError(
            f"Missing source SVG: {SOURCE_SVG.relative_to(ROOT)}"
        )

    paths = _paths_from_source()
    _write_static_svg(paths)
    _write_pdf_source(paths)
    _build_pdf()

    old_png = GENERATED_DIR / "alius-leaf-from-svg.png"
    if old_png.exists():
        old_png.unlink()

    print(f"Wrote {STATIC_SVG.relative_to(ROOT)}")
    print(f"Wrote {GENERATED_PDF.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
