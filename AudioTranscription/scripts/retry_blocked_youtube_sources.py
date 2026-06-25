#!/usr/bin/env python3
"""Retry verified-but-blocked YouTube source downloads from the blocked ledger."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "sources" / "blocked_youtube_sources.csv"
DOWNLOADER = ROOT / "scripts" / "download_youtube_audio.py"


def load_rows(path: Path, speaker: str, verified_only: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if speaker and row["speaker_slug"] != speaker:
                continue
            if verified_only and not row["verification_status"].startswith("verified"):
                continue
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--speaker", default="", help="Optional speaker_slug filter")
    parser.add_argument("--cookies", type=Path, required=True, help="Netscape-format YouTube cookies.txt")
    parser.add_argument(
        "--extractor-args",
        default="youtube:player_client=web_embedded,android",
        help="yt-dlp extractor args passed through to the downloader",
    )
    parser.add_argument("--include-unverified", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.ledger, args.speaker, verified_only=not args.include_unverified)
    print(f"retry queue: {len(rows)}", file=sys.stderr)
    failures = 0
    for row in rows:
        cmd = [
            sys.executable,
            str(DOWNLOADER),
            "--speaker",
            row["speaker_slug"],
            "--speaker-name",
            row["speaker_name"],
            "--url",
            row["url"],
            "--cookies",
            str(args.cookies),
            "--extractor-args",
            args.extractor_args,
        ]
        print(f"retry {row['speaker_slug']} {row['url']}", file=sys.stderr)
        result = subprocess.run(cmd)
        if result.returncode:
            failures += 1
            if args.stop_on_error:
                raise SystemExit(result.returncode)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
