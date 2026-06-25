#!/usr/bin/env python3
"""Download best available native audio for a reviewed YouTube source URL."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def video_id(url: str) -> str:
    for pattern in (r"[?&]v=([^&]+)", r"youtu\.be/([^?&/]+)"):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", required=True)
    parser.add_argument("--speaker-name", default="")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "sources" / "raw")
    parser.add_argument("--make-wav", action="store_true", help="Also decode a full WAV copy")
    parser.add_argument("--with-captions", action="store_true", help="Also request YouTube VTT captions")
    parser.add_argument("--cookies-from-browser", default="", help="Pass a browser name/profile to yt-dlp, e.g. chrome")
    parser.add_argument("--cookies", type=Path, default=None, help="Netscape-format cookies.txt file for yt-dlp")
    parser.add_argument(
        "--extractor-args",
        action="append",
        default=[],
        help="Pass yt-dlp extractor args, e.g. youtube:player_client=web_embedded,android",
    )
    parser.add_argument("--log", type=Path, default=ROOT / "sources" / "download_log.csv")
    args = parser.parse_args()

    out_dir = args.out_dir / args.speaker
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / "%(id)s.%(ext)s")
    cmd = ["yt-dlp"]
    if args.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
    if args.cookies:
        cmd.extend(["--cookies", str(args.cookies)])
    for extractor_arg in args.extractor_args:
        cmd.extend(["--extractor-args", extractor_arg])
    cmd.extend(
        [
            "-f",
            "bestaudio/best",
            "--no-playlist",
            "--write-info-json",
            "--write-thumbnail",
        ]
    )
    if args.make_wav:
        cmd.extend(["--extract-audio", "--audio-format", "wav", "--audio-quality", "0", "--keep-video"])
    if args.with_captions:
        cmd.extend(
            [
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                "en.*,fr.*,de.*,es.*",
                "--sub-format",
                "vtt",
                "--sleep-subtitles",
                "5",
            ]
        )
    cmd.extend(["-o", template, args.url])

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    vid = video_id(args.url)
    info = {}
    info_path = out_dir / f"{vid}.info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))
    args.log.parent.mkdir(parents=True, exist_ok=True)
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
    write_header = not args.log.exists()
    status = "downloaded" if result.returncode == 0 else "download_error"
    with args.log.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "speaker_slug": args.speaker,
                "speaker_name": args.speaker_name,
                "score": "",
                "download_status": status,
                "video_id": vid,
                "url": args.url,
                "title": info.get("title", ""),
                "channel": info.get("channel") or info.get("uploader") or "",
                "duration": info.get("duration", ""),
                "out_dir": str(out_dir),
                "stderr": (result.stderr or result.stdout)[-1000:],
            }
        )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print(out_dir)


if __name__ == "__main__":
    main()
