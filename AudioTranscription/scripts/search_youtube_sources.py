#!/usr/bin/env python3
"""Search YouTube for possible speaker source audio with yt-dlp metadata.

This only records candidates. Review each candidate before downloading or using
it as a voice source.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]

FIELDS = [
    "speaker_slug",
    "speaker_name",
    "status",
    "query",
    "url",
    "title",
    "channel",
    "duration",
    "view_count",
    "upload_date",
    "candidate_rank",
    "review_notes",
]


def run_yt_dlp(query: str, limit: int) -> list[dict]:
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--skip-download",
        f"ytsearch{limit}:{query}",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    rows = []
    for line in result.stdout.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", required=True)
    parser.add_argument("--speaker-name", default="")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--out", type=Path, default=ROOT / "sources" / "youtube_candidates.csv")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    exists = args.out.exists()
    rows = run_yt_dlp(args.query, args.limit)
    with args.out.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "speaker_slug": args.speaker,
                    "speaker_name": args.speaker_name,
                    "status": "unreviewed",
                    "query": args.query,
                    "url": row.get("webpage_url") or row.get("original_url") or row.get("url"),
                    "title": row.get("title"),
                    "channel": row.get("channel") or row.get("uploader"),
                    "duration": row.get("duration"),
                    "view_count": row.get("view_count"),
                    "upload_date": row.get("upload_date"),
                    "candidate_rank": rank,
                    "review_notes": "",
                }
            )
    print(args.out)


if __name__ == "__main__":
    main()
