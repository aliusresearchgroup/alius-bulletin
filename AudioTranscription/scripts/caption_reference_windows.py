#!/usr/bin/env python3
"""Extract candidate reference-text windows from YouTube VTT captions."""

from __future__ import annotations

import argparse
import csv
import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TIME_RE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})\.(?P<ms>\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")
WORD_TIME_RE = re.compile(r"<(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})><c>(?P<word>.*?)</c>")
BAD_MARKERS = {
    "applause",
    "music",
    "laughter",
    "laughs",
    "inaudible",
    "foreign",
}


def parse_time(value: str) -> float:
    match = TIME_RE.search(value)
    if not match:
        raise ValueError(f"Invalid timestamp: {value}")
    return (
        int(match.group("h")) * 3600
        + int(match.group("m")) * 60
        + int(match.group("s"))
        + int(match.group("ms")) / 1000
    )


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = TAG_RE.sub(" ", value)
    value = re.sub(r"\[[^\]]+\]|\([^\)]*(?:music|applause|laughter)[^\)]*\)", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" -\t\r\n")


def extract_words(vtt: Path) -> list[dict]:
    words: list[dict] = []
    seen: set[tuple[float, str]] = set()
    cue_start: float | None = None
    text = vtt.read_text(encoding="utf-8-sig")
    has_word_times = WORD_TIME_RE.search(text) is not None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "-->" in line:
            cue_start = parse_time(line.split("-->", 1)[0])
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue

        matches = list(WORD_TIME_RE.finditer(line))
        if matches:
            prefix = line[: matches[0].start()]
            prefix_text = clean_text(prefix)
            if prefix_text and cue_start is not None:
                for token in prefix_text.split():
                    key = (round(cue_start, 3), token.lower())
                    if key not in seen:
                        words.append({"start": cue_start, "word": token})
                        seen.add(key)
            for match in matches:
                token = clean_text(match.group("word"))
                if not token:
                    continue
                start = parse_time(match.group("time"))
                key = (round(start, 3), token.lower())
                if key not in seen:
                    words.append({"start": start, "word": token})
                    seen.add(key)
        elif cue_start is not None and not has_word_times:
            text = clean_text(line)
            for token in text.split():
                key = (round(cue_start, 3), token.lower())
                if key not in seen:
                    words.append({"start": cue_start, "word": token})
                    seen.add(key)

    words.sort(key=lambda item: item["start"])
    return words


def text_for_window(words: list[dict], start: float, duration: float) -> str:
    end = start + duration
    tokens = [item["word"] for item in words if start <= item["start"] <= end]
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def score_window(text: str, duration: float) -> tuple[int, str]:
    lower = text.lower()
    words = text.split()
    notes: list[str] = []
    score = 100

    if len(words) < max(18, int(duration * 1.5)):
        score -= 35
        notes.append("sparse")
    if any(marker in lower for marker in BAD_MARKERS):
        score -= 60
        notes.append("caption_noise_marker")
    if "[" in text or "]" in text:
        score -= 30
        notes.append("bracketed_caption")
    if text.count("?") > 1:
        score -= 15
        notes.append("question_heavy")
    if len(words) > int(duration * 4.8):
        score -= 10
        notes.append("very_fast")

    return max(score, 0), ";".join(notes)


def write_windows(vtt: Path, out: Path, speaker: str, source_url: str, duration: float, step: float) -> None:
    words = extract_words(vtt)
    if not words:
        raise SystemExit(f"No caption words extracted from {vtt}")

    starts = []
    current = words[0]["start"]
    last = words[-1]["start"]
    while current + duration <= last:
        starts.append(round(current, 3))
        current += step

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "speaker_slug",
                "source_url",
                "start_seconds",
                "duration_seconds",
                "score",
                "review_notes",
                "reference_text",
            ],
        )
        writer.writeheader()
        for start in starts:
            text = text_for_window(words, start, duration)
            if not text:
                continue
            score, notes = score_window(text, duration)
            writer.writerow(
                {
                    "speaker_slug": speaker,
                    "source_url": source_url,
                    "start_seconds": start,
                    "duration_seconds": duration,
                    "score": score,
                    "review_notes": notes,
                    "reference_text": text,
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtt", required=True, type=Path)
    parser.add_argument("--speaker", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--duration", type=float, default=14)
    parser.add_argument("--step", type=float, default=7)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    out = args.out or ROOT / "work" / "caption_windows" / f"{args.speaker}.csv"
    write_windows(args.vtt, out, args.speaker, args.source_url, args.duration, args.step)
    print(out)


if __name__ == "__main__":
    main()
