from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageStat

ROOT = Path(__file__).resolve().parent
REFS = ROOT / "reference-covers"
BUILD = ROOT / ".build" / "compare"


def render_pdf(pdf: Path, out_prefix: Path) -> Path:
    subprocess.run(
        ["pdftoppm", "-png", "-r", "144", str(pdf), str(out_prefix)],
        check=True,
    )
    return out_prefix.with_name(f"{out_prefix.name}-1.png")


def reference_path(issue: str) -> Path:
    pdf = REFS / f"issue{issue}-original-cover.pdf"
    png = REFS / f"issue{issue}-original-cover.png"
    return pdf if pdf.exists() else png


def make_panel(issue: str, ref: Image.Image, cur: Image.Image, diff: Image.Image) -> Image.Image:
    thumb_size = (238, 336)
    panels = []
    for image in (ref, cur, diff):
        thumb = image.copy()
        thumb.thumbnail(thumb_size)
        panels.append(thumb)

    panel = Image.new("RGB", (714, 366), "white")
    draw = ImageDraw.Draw(panel)
    draw.text((10, 8), f"Issue {issue} reference", fill="black")
    draw.text((248, 8), f"Issue {issue} generated", fill="black")
    draw.text((486, 8), f"Issue {issue} diff", fill="black")
    for idx, image in enumerate(panels):
        panel.paste(image, (idx * 238, 30))
    return panel


def compare(issue: str) -> tuple[str, float, float, int, Image.Image]:
    generated_pdf = ROOT / f"issue{issue}-cover.pdf"
    reference = reference_path(issue)
    BUILD.mkdir(parents=True, exist_ok=True)

    current_png = render_pdf(generated_pdf, BUILD / f"issue{issue}-generated")
    if reference.suffix.lower() == ".pdf":
        reference_png = render_pdf(reference, BUILD / f"issue{issue}-reference")
    else:
        reference_png = reference

    ref = Image.open(reference_png).convert("RGB")
    cur = Image.open(current_png).convert("RGB").resize(ref.size)
    diff = ImageChops.difference(ref, cur)
    stat = ImageStat.Stat(diff)
    mean_delta = sum(stat.mean) / 3
    pixels = diff.get_flattened_data()
    differing = sum(1 for px in pixels if px != (0, 0, 0))
    total = ref.size[0] * ref.size[1]
    max_delta = max(channel[1] for channel in diff.getextrema())

    enhanced = diff.point(lambda x: min(255, x * 4))
    panel = make_panel(issue, ref, cur, enhanced)
    return issue, differing / total, mean_delta, max_delta, panel


def main(args: list[str]) -> int:
    issues = args or [f"{n:02d}" for n in range(1, 8)]
    rows = []
    panels = []
    for issue in issues:
        row = compare(issue)
        rows.append(row[:4])
        panels.append(row[4])

    sheet = Image.new("RGB", (714, 366 * len(panels)), "white")
    for idx, panel in enumerate(panels):
        sheet.paste(panel, (0, idx * 366))
    sheet.save(BUILD / "comparison-sheet.png")

    print("| Issue | Differing pixels | Mean delta | Max delta |")
    print("| --- | ---: | ---: | ---: |")
    for issue, differing, mean_delta, max_delta in rows:
        print(f"| {issue} | {differing:.2%} | {mean_delta:.2f} | {max_delta} |")
    print(f"comparison sheet: {BUILD / 'comparison-sheet.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
