#!/usr/bin/env python3
"""Search YouTube with exact-name query variants for speakers still missing sources."""

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
OUT = ROOT / "sources" / "youtube_candidates.csv"

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


def load_existing(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {(row["speaker_slug"], row["url"]) for row in csv.DictReader(f) if row.get("url")}


def search(query: str, limit: int) -> list[dict]:
    cmd = ["yt-dlp", "--dump-json", "--skip-download", f"ytsearch{limit}:{query}"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def load_jobs(limit_status: str, variants: list[str], limit: int) -> list[dict]:
    jobs: list[dict] = []
    with INVENTORY.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if limit_status and row["source_status"] != limit_status:
                continue
            for variant in variants:
                query = variant.format(name=row["speaker_name"])
                jobs.append({**row, "query": query, "limit": limit})
    return jobs


def run_job(job: dict) -> tuple[dict, list[dict] | None, str]:
    print(f"search {job['speaker_slug']}: {job['query']}", file=sys.stderr)
    try:
        return job, search(job["query"], job["limit"]), ""
    except Exception as exc:
        return job, None, str(exc)[:500]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-status", default="needs_source")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        help='Query template using {name}, e.g. "\\"{name}\\" lecture"',
    )
    args = parser.parse_args()

    variants = args.variant or [
        '"{name}" lecture',
        '"{name}" interview',
        '"{name}" talk',
        '"{name}" seminar',
    ]
    jobs = load_jobs(args.source_status, variants, args.limit)
    existing = load_existing(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_header = not args.out.exists()
    added = 0

    with args.out.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(run_job, job) for job in jobs]
            for future in as_completed(futures):
                job, results, error = future.result()
                if error:
                    writer.writerow(
                        {
                            "speaker_slug": job["speaker_slug"],
                            "speaker_name": job["speaker_name"],
                            "status": "search_error",
                            "query": job["query"],
                            "review_notes": error,
                        }
                    )
                    continue
                for rank, result in enumerate(results or [], start=1):
                    url = result.get("webpage_url") or result.get("original_url") or result.get("url") or ""
                    key = (job["speaker_slug"], url)
                    if key in existing:
                        continue
                    existing.add(key)
                    writer.writerow(
                        {
                            "speaker_slug": job["speaker_slug"],
                            "speaker_name": job["speaker_name"],
                            "status": "unreviewed",
                            "query": job["query"],
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
    print(f"added {added}")
    print(args.out)


if __name__ == "__main__":
    main()
