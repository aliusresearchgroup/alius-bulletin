#!/usr/bin/env python3
"""Sync speaker_inventory.csv status fields from profile JSON files."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "speaker_inventory.csv"
PROFILES = ROOT / "profiles"


def main() -> None:
    with INVENTORY.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)

    changed = 0
    for row in rows:
        profile_path = PROFILES / f"{row['speaker_slug']}.json"
        if not profile_path.exists():
            continue
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        old = (
            row.get("speaker_name", ""),
            row.get("profile_status", ""),
            row.get("source_status", ""),
            row.get("youtube_query", ""),
        )
        row["speaker_name"] = profile.get("speaker_name", row.get("speaker_name", ""))
        row["profile_status"] = profile.get("profile_status", row.get("profile_status", ""))
        row["source_status"] = profile.get("source_status", row.get("source_status", ""))
        row["youtube_query"] = profile.get("youtube_query", row.get("youtube_query", ""))
        if old != (
            row["speaker_name"],
            row["profile_status"],
            row["source_status"],
            row["youtube_query"],
        ):
            changed += 1

    with INVENTORY.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"synced {changed} inventory rows")


if __name__ == "__main__":
    main()
