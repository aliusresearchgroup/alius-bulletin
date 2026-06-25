#!/usr/bin/env python3
"""Batch-search YouTube source candidates for speaker voice profiles."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "speaker_inventory.csv"


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


def run_search(query: str, limit: int) -> list[dict]:
    cmd = ["yt-dlp", "--dump-json", "--skip-download", f"ytsearch{limit}:{query}"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def load_existing(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {(row["speaker_slug"], row["url"]) for row in csv.DictReader(f) if row.get("url")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3, help="Candidates per speaker")
    parser.add_argument("--offset", type=int, default=0, help="Zero-based speaker offset")
    parser.add_argument("--max-speakers", type=int, default=0, help="0 means all")
    parser.add_argument("--include-ready", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, default=ROOT / "sources" / "youtube_candidates.csv")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    existing = load_existing(args.out)
    speakers = []
    with INVENTORY.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not args.include_ready and row["source_status"] == "ready":
                continue
            speakers.append(row)
    if args.offset:
        speakers = speakers[args.offset :]
    if args.max_speakers:
        speakers = speakers[: args.max_speakers]

    def search_speaker(row: dict) -> tuple[dict, list[dict] | None, str]:
        print(f"search {row['speaker_slug']}: {row['youtube_query']}", file=sys.stderr)
        try:
            return row, run_search(row["youtube_query"], args.limit), ""
        except Exception as exc:
            return row, None, str(exc)[:500]

    workers = max(1, args.workers)
    write_header = not args.out.exists()
    added = 0
    with args.out.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        if workers == 1:
            results_iter = (search_speaker(row) for row in speakers)
        else:
            executor = ThreadPoolExecutor(max_workers=workers)
            futures = [executor.submit(search_speaker, row) for row in speakers]
            results_iter = (future.result() for future in as_completed(futures))

        for row, results, error in results_iter:
            if error:
                writer.writerow(
                    {
                        "speaker_slug": row["speaker_slug"],
                        "speaker_name": row["speaker_name"],
                        "status": "search_error",
                        "query": row["youtube_query"],
                        "review_notes": error,
                    }
                )
                continue
            for rank, result in enumerate(results, start=1):
                url = result.get("webpage_url") or result.get("original_url") or result.get("url") or ""
                key = (row["speaker_slug"], url)
                if key in existing:
                    continue
                existing.add(key)
                writer.writerow(
                    {
                        "speaker_slug": row["speaker_slug"],
                        "speaker_name": row["speaker_name"],
                        "status": "unreviewed",
                        "query": row["youtube_query"],
                        "url": url,
                        "title": result.get("title", ""),
                        "channel": result.get("channel") or result.get("uploader") or "",
                        "duration": result.get("duration", ""),
                        "view_count": result.get("view_count", ""),
                        "upload_date": result.get("upload_date", ""),
                        "candidate_rank": rank,
                        "review_notes": "",
                    }
                )
                added += 1
        if workers > 1:
            executor.shutdown(wait=True)
    print(f"added {added}")
    print(args.out)


if __name__ == "__main__":
    main()
