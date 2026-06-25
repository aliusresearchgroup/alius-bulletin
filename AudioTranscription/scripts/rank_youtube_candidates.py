#!/usr/bin/env python3
"""Rank YouTube candidates for voice-source review."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "speaker_inventory.csv"
CANDIDATES = ROOT / "sources" / "youtube_candidates.csv"

FIELDS = [
    "speaker_slug",
    "speaker_name",
    "score",
    "decision",
    "url",
    "title",
    "channel",
    "duration",
    "view_count",
    "upload_date",
    "query",
    "review_notes",
]

NEGATIVE_TITLE_TERMS = {
    "playlist",
    "mix",
    "shorts",
    "trailer",
    "highlights",
    "compilation",
    "full album",
}
POSITIVE_TITLE_TERMS = {
    "lecture",
    "talk",
    "seminar",
    "interview",
    "conversation",
    "keynote",
    "colloquium",
    "webinar",
    "conference",
    "presentation",
    "podcast",
    "q&a",
}


def normalize(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def speaker_tokens(name: str) -> list[str]:
    tokens = [token for token in normalize(name).split() if len(token) > 1]
    return tokens


def score_candidate(row: dict, speaker_name: str) -> tuple[int, str, str]:
    title = row.get("title", "")
    channel = row.get("channel", "")
    title_norm = normalize(title)
    channel_norm = normalize(channel)
    text_norm = f"{title_norm} {channel_norm}"
    tokens = speaker_tokens(speaker_name)
    notes: list[str] = []
    score = 0

    if tokens and all(token in text_norm for token in tokens):
        score += 70
        notes.append("full_name_match")
    elif tokens and tokens[-1] in text_norm:
        score += 35
        notes.append("surname_match")

    if any(term in title_norm for term in POSITIVE_TITLE_TERMS):
        score += 25
        notes.append("source_format_match")
    if "youtube" in row.get("url", ""):
        score += 5

    try:
        duration = float(row.get("duration") or 0)
    except ValueError:
        duration = 0
    if 420 <= duration <= 7200:
        score += 20
        notes.append("lecture_length")
    elif 120 <= duration < 420:
        score += 5
        notes.append("short_source")
    elif duration > 7200:
        score -= 15
        notes.append("very_long_possible_panel")

    if any(term in title_norm for term in NEGATIVE_TITLE_TERMS):
        score -= 30
        notes.append("negative_title_term")

    if not title or not row.get("url"):
        score -= 100
        notes.append("missing_title_or_url")

    if score >= 85:
        decision = "download_review"
    elif score >= 55:
        decision = "manual_review"
    else:
        decision = "low_priority"

    return score, decision, ";".join(notes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=CANDIDATES)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--out", type=Path, default=ROOT / "sources" / "youtube_candidate_ranking.csv")
    args = parser.parse_args()

    inventory = {}
    with args.inventory.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            inventory[row["speaker_slug"]] = row["speaker_name"]

    rows: list[dict] = []
    with args.candidates.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            speaker_name = row.get("speaker_name") or inventory.get(row.get("speaker_slug", ""), "")
            score, decision, notes = score_candidate(row, speaker_name)
            rows.append(
                {
                    "speaker_slug": row.get("speaker_slug", ""),
                    "speaker_name": speaker_name,
                    "score": score,
                    "decision": decision,
                    "url": row.get("url", ""),
                    "title": row.get("title", ""),
                    "channel": row.get("channel", ""),
                    "duration": row.get("duration", ""),
                    "view_count": row.get("view_count", ""),
                    "upload_date": row.get("upload_date", ""),
                    "query": row.get("query", ""),
                    "review_notes": notes,
                }
            )

    rows.sort(key=lambda row: (row["speaker_slug"], -int(row["score"]), row["title"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(args.out)


if __name__ == "__main__":
    main()
