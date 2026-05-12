"""Replace each compiled issue PDF's first page with its verified cover PDF.

The TeX sources include the generated cover PDFs so local/manual builds remain
self-contained. This final pass preserves the exact verified cover page object in
the distributable issue PDFs.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError as exc:  # pragma: no cover - dependency message for local builds
    raise SystemExit("Missing Python package 'pypdf'. Install it with: python -m pip install pypdf") from exc


def finalize_issue(root: Path, issue: str) -> None:
    cover_pdf = root / "Cover-Art" / f"issue{issue}-cover.pdf"
    issue_pdf = root / "Bulletins" / f"issue{issue}.pdf"
    tmp_pdf = issue_pdf.with_suffix(".tmp.pdf")

    if not cover_pdf.exists():
        raise FileNotFoundError(f"Missing generated cover PDF: {cover_pdf}")
    if not issue_pdf.exists():
        raise FileNotFoundError(f"Missing compiled issue PDF: {issue_pdf}")

    cover_reader = PdfReader(str(cover_pdf))
    issue_reader = PdfReader(str(issue_pdf))
    if len(cover_reader.pages) != 1:
        raise ValueError(f"Expected one cover page in {cover_pdf}, found {len(cover_reader.pages)}")
    if len(issue_reader.pages) < 1:
        raise ValueError(f"Expected at least one issue page in {issue_pdf}")

    writer = PdfWriter()
    writer.add_page(cover_reader.pages[0])
    for page in issue_reader.pages[1:]:
        writer.add_page(page)

    with tmp_pdf.open("wb") as handle:
        writer.write(handle)
    tmp_pdf.replace(issue_pdf)
    print(f"issue{issue}: finalized {len(issue_reader.pages)} pages")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--issues", nargs="+", default=["01", "02", "03", "04", "05", "06", "07"])
    args = parser.parse_args()

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    root = args.root.resolve()
    for issue in args.issues:
        finalize_issue(root, issue)


if __name__ == "__main__":
    main()
