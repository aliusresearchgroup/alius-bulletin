#!/usr/bin/env python3
"""Build cleaned reference-audio candidates from downloaded source audio."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "sources" / "raw"
FILTERS = ROOT / "config" / "audio_filters.json"
OUT = ROOT / "references"

MEDIA_EXTS = {".webm", ".m4a", ".opus", ".mp3", ".wav", ".aac", ".ogg"}
INTERVIEW_TERMS = ("interview", "podcast", "conversation", "episode", "q&a")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    return float(result.stdout.strip())


def info_for_media(media: Path) -> dict:
    info_path = media.with_suffix(".info.json")
    if info_path.exists():
        return json.loads(info_path.read_text(encoding="utf-8"))
    return {}


def choose_start(duration: float, title: str, requested: float | None) -> float:
    if requested is not None:
        return requested
    title_norm = title.lower()
    if any(term in title_norm for term in INTERVIEW_TERMS):
        start = max(300.0, duration * 0.25)
    else:
        start = max(120.0, duration * 0.18)
    return min(start, max(0.0, duration - 45.0))


def find_media(speaker: str) -> Path | None:
    speaker_dir = RAW / speaker
    if not speaker_dir.exists():
        return None
    media = [
        path
        for path in speaker_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in MEDIA_EXTS
        and not path.name.endswith(".part")
    ]
    if not media:
        return None
    return sorted(media, key=lambda path: path.stat().st_size, reverse=True)[0]


def cut_reference(media: Path, out: Path, preset: dict, start: float, duration: float) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        str(start),
        "-t",
        str(duration),
        "-i",
        str(media),
        "-vn",
        "-af",
        preset["ffmpeg_filter"],
        "-ar",
        str(preset["sample_rate_hz"]),
        "-ac",
        str(preset["channels"]),
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")


def transcribe_reference(model, wav: Path) -> str:
    result = model.transcribe(str(wav), fp16=False, verbose=False)
    text = re.sub(r"\s+", " ", result.get("text", "")).strip()
    return text


def load_speakers(args: argparse.Namespace) -> list[str]:
    if args.speakers:
        return [item.strip() for item in args.speakers.split(",") if item.strip()]
    speakers = [
        path.name
        for path in RAW.iterdir()
        if path.is_dir() and find_media(path.name) is not None
    ]
    speakers.sort()
    if args.exclude:
        excluded = {item.strip() for item in args.exclude.split(",") if item.strip()}
        speakers = [speaker for speaker in speakers if speaker not in excluded]
    if args.max_speakers:
        speakers = speakers[: args.max_speakers]
    return speakers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speakers", default="", help="Comma-separated speaker slugs")
    parser.add_argument("--exclude", default="", help="Comma-separated speaker slugs")
    parser.add_argument("--max-speakers", type=int, default=0)
    parser.add_argument("--duration", type=float, default=14)
    parser.add_argument("--start", type=float)
    parser.add_argument("--preset", default="lecture_cleanup")
    parser.add_argument("--model", default="base")
    parser.add_argument("--manifest", type=Path, default=ROOT / "sources" / "reference_candidates.csv")
    args = parser.parse_args()

    try:
        import whisper
    except ImportError as exc:
        raise SystemExit("OpenAI Whisper is not installed in this Python environment.") from exc

    filters = json.loads(FILTERS.read_text(encoding="utf-8"))
    if args.preset not in filters:
        raise SystemExit(f"Unknown preset {args.preset}")
    preset = filters[args.preset]

    speakers = load_speakers(args)
    print(f"reference queue: {len(speakers)}", file=sys.stderr)
    model = whisper.load_model(args.model)

    fields = [
        "speaker_slug",
        "source_audio",
        "source_url",
        "source_title",
        "source_channel",
        "reference_audio",
        "reference_text",
        "reference_source_start_seconds",
        "reference_duration_seconds",
        "reference_filter_preset",
        "reference_sha256",
        "review_status",
    ]
    existing = args.manifest.exists()
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not existing:
            writer.writeheader()
        for speaker in speakers:
            media = find_media(speaker)
            if media is None:
                continue
            info = info_for_media(media)
            duration = float(info.get("duration") or ffprobe_duration(media))
            start = choose_start(duration, info.get("title", ""), args.start)
            video_id = media.stem
            ref = OUT / speaker / f"{speaker}_youtube_{slugify(video_id)}_ref.wav"
            cut_reference(media, ref, preset, start, args.duration)
            text = transcribe_reference(model, ref)
            writer.writerow(
                {
                    "speaker_slug": speaker,
                    "source_audio": str(media),
                    "source_url": info.get("webpage_url", ""),
                    "source_title": info.get("title", ""),
                    "source_channel": info.get("channel") or info.get("uploader") or "",
                    "reference_audio": str(ref),
                    "reference_text": text,
                    "reference_source_start_seconds": round(start, 3),
                    "reference_duration_seconds": args.duration,
                    "reference_filter_preset": args.preset,
                    "reference_sha256": sha256(ref),
                    "review_status": "needs_listening_review",
                }
            )
            print(f"reference_candidate {speaker} {ref}", file=sys.stderr)
    print(args.manifest)


if __name__ == "__main__":
    main()
