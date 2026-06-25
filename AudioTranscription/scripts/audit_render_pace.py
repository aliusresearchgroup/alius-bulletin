#!/usr/bin/env python3
"""Estimate rendered interview talking pace from source words and MP3 duration."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
DEFAULT_MIN_WPM = 125.0
DEFAULT_MAX_WPM = 165.0


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return float(result.stdout.strip())


def spoken_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    if "QUESTION SPOKEN TEXT:" not in raw or "ANSWER SPOKEN TEXT:" not in raw:
        return raw
    question = raw.split("QUESTION SPOKEN TEXT:", 1)[1].split("ANSWER SPOKEN TEXT:", 1)[0]
    answer = raw.split("ANSWER SPOKEN TEXT:", 1)[1]
    return f"{question} {answer}"


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:['’-][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)?", text))


def pace_status(wpm: float, min_wpm: float, max_wpm: float) -> str:
    if wpm < min_wpm:
        return "slow"
    if wpm > max_wpm:
        return "fast"
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans-dir", type=Path, default=ROOT / "render_plans")
    parser.add_argument("--renders-dir", type=Path, default=ROOT / "renders")
    parser.add_argument("--out", type=Path, default=ROOT / "render_pace_audit.csv")
    parser.add_argument("--min-wpm", type=float, default=DEFAULT_MIN_WPM)
    parser.add_argument("--max-wpm", type=float, default=DEFAULT_MAX_WPM)
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    for plan_path in sorted(args.plans_dir.glob("*.json")):
        plan = read_json(plan_path)
        slug = plan["interview_slug"]
        render_dir = args.renders_dir / slug
        mp3_path = render_dir / f"{plan['output_file_stem']}.mp3"
        manifest_path = render_dir / "render_manifest.json"
        if not mp3_path.exists():
            continue

        qa_dir = repo_path(plan["source_qa_dir"])
        words = sum(word_count(spoken_text(path)) for path in sorted(qa_dir.glob("qa_*.txt")))
        duration = ffprobe_duration(mp3_path)
        minutes = duration / 60.0 if duration else 0.0
        wpm = words / minutes if minutes else 0.0
        manifest = read_json(manifest_path) if manifest_path.exists() else {}
        postprocess = manifest.get("audio_postprocess") or {}
        rows.append(
            {
                "interview_slug": slug,
                "words": str(words),
                "duration_seconds": f"{duration:.3f}",
                "estimated_wpm": f"{wpm:.1f}",
                "pace_status": pace_status(wpm, args.min_wpm, args.max_wpm),
                "target_min_wpm": f"{args.min_wpm:.1f}",
                "target_max_wpm": f"{args.max_wpm:.1f}",
                "tts_speed": str(manifest.get("tts_speed", plan.get("tts", {}).get("speed", ""))),
                "final_tempo": str(postprocess.get("final_tempo", "")),
                "mp3": str(mp3_path),
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "interview_slug",
                "words",
                "duration_seconds",
                "estimated_wpm",
                "pace_status",
                "target_min_wpm",
                "target_max_wpm",
                "tts_speed",
                "final_tempo",
                "mp3",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["pace_status"]] = counts.get(row["pace_status"], 0) + 1
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    print(args.out)


if __name__ == "__main__":
    main()
