"""Regenerate the Overleaf-safe ALIUS leaf cache from the canonical SVG.

The leaf SVG exported from the original artwork stores three embedded PNG
layers. Overleaf's SVG conversion can silently drop those layers under pdfTeX,
so the covers include the generated PNG cache while keeping the SVG as the
single editable leaf source.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
SVG_PATH = ROOT / "assets" / "alius-leaf.svg"
OUTPUT_PATH = ROOT / "generated" / "alius-leaf-from-svg.png"


def _required_match(pattern: str, text: str) -> re.Match[str]:
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"SVG did not match expected pattern: {pattern}")
    return match


def main() -> None:
    svg = SVG_PATH.read_text(encoding="utf-8")
    viewbox = _required_match(r'viewBox="\s*0\s+0\s+([\d.]+)\s+([\d.]+)"', svg)
    width, height = int(float(viewbox.group(1))), int(float(viewbox.group(2)))

    images: dict[str, Image.Image] = {}
    image_pattern = (
        r'<image\s+id="([^"]+)"\s+width="([\d.]+)px"\s+height="([\d.]+)px"\s+'
        r'xlink:href="data:image/png;base64,([^"]+)"'
    )
    for match in re.finditer(image_pattern, svg):
        images[match.group(1)] = Image.open(
            io.BytesIO(base64.b64decode(match.group(4)))
        ).convert("RGBA")

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    use_pattern = (
        r'<use\s+xlink:href="#([^"]+)"\s+x="([\d.]+)"\s+y="([\d.]+)"\s+'
        r'width="([\d.]+)px"\s+height="([\d.]+)px"\s+'
        r'transform="matrix\(([\d.\-]+),0,0,([\d.\-]+),0,0\)"'
    )
    for match in re.finditer(use_pattern, svg):
        image_id = match.group(1)
        if image_id not in images:
            raise ValueError(f"SVG references missing image layer: {image_id}")

        x, y = float(match.group(2)), float(match.group(3))
        layer_width, layer_height = float(match.group(4)), float(match.group(5))
        scale_x, scale_y = float(match.group(6)), float(match.group(7))
        layer = images[image_id].resize(
            (max(1, round(layer_width * scale_x)), max(1, round(layer_height * scale_y))),
            Image.Resampling.LANCZOS,
        )
        canvas.alpha_composite(layer, (round(x * scale_x), round(y * scale_y)))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT_PATH, optimize=True)
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
