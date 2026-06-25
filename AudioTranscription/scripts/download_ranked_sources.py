#!/usr/bin/env python3
"""Download top-ranked YouTube source audio candidates in parallel."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RANKING = ROOT / "sources" / "youtube_candidate_ranking.csv"


def video_id(url: str) -> str:
    patterns = [
        r"[?&]v=([^&]+)",
        r"youtu\.be/([^?&/]+)",
        r"youtube\.com/shorts/([^?&/]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def load_queue(path: Path, min_score: int, exclude: set[str], max_downloads: int) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["decision"] != "download_review":
                continue
            if int(row["score"]) < min_score:
                continue
            if row["speaker_slug"] in exclude:
                continue
            if not row.get("url"):
                continue
            rows.append(row)

    best: dict[str, dict] = {}
    for row in rows:
        slug = row["speaker_slug"]
        if slug not in best or int(row["score"]) > int(best[slug]["score"]):
            best[slug] = row

    queue = sorted(best.values(), key=lambda row: (-int(row["score"]), row["speaker_slug"]))
    if max_downloads:
        queue = queue[:max_downloads]
    return queue


def download(row: dict, out_root: Path) -> dict:
    slug = row["speaker_slug"]
    url = row["url"]
    vid = video_id(url)
    out_dir = out_root / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    media_exts = {".webm", ".m4a", ".opus", ".mp3", ".wav", ".aac", ".ogg"}
    existing_media = [path for path in out_dir.glob(f"{vid}.*") if path.suffix.lower() in media_exts]
    if vid and existing_media:
        return {**row, "download_status": "already_present", "video_id": vid, "out_dir": str(out_dir)}

    template = str(out_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f",
        "bestaudio/best",
        "--no-playlist",
        "--write-info-json",
        "--write-thumbnail",
        "-o",
        template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    status = "downloaded" if result.returncode == 0 else "download_error"
    return {
        **row,
        "download_status": status,
        "video_id": vid,
        "out_dir": str(out_dir),
        "stderr": (result.stderr or result.stdout)[-1000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranking", type=Path, default=RANKING)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "sources" / "raw")
    parser.add_argument("--log", type=Path, default=ROOT / "sources" / "download_log.csv")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--min-score", type=int, default=85)
    parser.add_argument("--max-downloads", type=int, default=0)
    parser.add_argument("--exclude", default="", help="Comma-separated speaker slugs")
    args = parser.parse_args()

    exclude = {item.strip() for item in args.exclude.split(",") if item.strip()}
    queue = load_queue(args.ranking, args.min_score, exclude, args.max_downloads)
    print(f"download queue: {len(queue)}", file=sys.stderr)

    fields = [
        "speaker_slug",
        "speaker_name",
        "score",
        "download_status",
        "video_id",
        "url",
        "title",
        "channel",
        "duration",
        "out_dir",
        "stderr",
    ]
    existing_log = args.log.exists()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not existing_log:
            writer.writeheader()
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(download, row, args.out_dir) for row in queue]
            for future in as_completed(futures):
                result = future.result()
                writer.writerow(result)
                print(f"{result['download_status']} {result['speaker_slug']} {result['url']}", file=sys.stderr)
    print(args.log)


if __name__ == "__main__":
    main()
