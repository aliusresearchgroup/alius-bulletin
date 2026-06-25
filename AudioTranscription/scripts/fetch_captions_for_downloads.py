#!/usr/bin/env python3
"""Fetch VTT captions for already downloaded YouTube source audio."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "sources" / "download_log.csv"


def load_rows(path: Path, speakers: set[str]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("download_status") not in {"downloaded", "already_present"}:
                continue
            if speakers and row.get("speaker_slug") not in speakers:
                continue
            key = (row.get("speaker_slug", ""), row.get("url", ""))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def fetch(row: dict) -> dict:
    out_dir = Path(row["out_dir"])
    template = str(out_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--no-playlist",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "en.*,fr.*,de.*,es.*",
        "--sub-format",
        "vtt",
        "--sleep-subtitles",
        "5",
        "--sleep-requests",
        "1",
        "-o",
        template,
        row["url"],
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return {
        "speaker_slug": row["speaker_slug"],
        "url": row["url"],
        "status": "captions_fetched" if result.returncode == 0 else "caption_error",
        "stderr": (result.stderr or result.stdout)[-1000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=LOG)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--speakers", default="", help="Comma-separated speaker slugs")
    args = parser.parse_args()

    speakers = {item.strip() for item in args.speakers.split(",") if item.strip()}
    rows = load_rows(args.log, speakers)
    print(f"caption queue: {len(rows)}", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(fetch, row) for row in rows]
        for future in as_completed(futures):
            result = future.result()
            print(f"{result['status']} {result['speaker_slug']} {result['url']}", file=sys.stderr)
    print(args.log)


if __name__ == "__main__":
    main()
