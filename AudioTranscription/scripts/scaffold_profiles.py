#!/usr/bin/env python3
"""Scaffold speaker inventory and F5 voice profile JSON files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
PARTICIPANTS = REPO / "AI-agents" / "interview_audio_participants.csv"
DEMOGRAPHICS = REPO / "AI-agents" / "interview_audio_speaker_demographics.csv"


def slugify(name: str) -> str:
    text = name.lower()
    text = text.replace("'", "")
    text = text.replace(".", "")
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    profile_dir = ROOT / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = ROOT / "speaker_inventory.csv"

    participants = read_csv(PARTICIPANTS)
    demographics = {row["person"]: row for row in read_csv(DEMOGRAPHICS)}

    people: dict[str, dict] = {}
    for row in participants:
        interview_id = row["interview_id"]
        person = row["person"].strip()
        if interview_id.startswith("Fictional/"):
            continue
        if person == "ALIUS Research Group":
            continue
        slug = slugify(person)
        entry = people.setdefault(
            person,
            {
                "speaker_slug": slug,
                "speaker_name": person,
                "roles": set(),
                "interviews": set(),
                "demographics": demographics.get(person, {}),
            },
        )
        entry["roles"].add(row["role"])
        entry["interviews"].add(interview_id)

    inventory_rows = []
    for person in sorted(people):
        entry = people[person]
        profile_path = profile_dir / f"{entry['speaker_slug']}.json"
        existing = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
        status = existing.get("profile_status", "needs_source")
        source_status = "ready" if existing.get("reference_audio") else "needs_source"
        query = f"{person} lecture interview consciousness neuroscience"
        inventory_rows.append(
            {
                "speaker_slug": entry["speaker_slug"],
                "speaker_name": person,
                "roles": ";".join(sorted(entry["roles"])),
                "interviews": ";".join(sorted(entry["interviews"])),
                "profile_status": status,
                "source_status": source_status,
                "youtube_query": existing.get("youtube_query", query),
                "profile_path": str(profile_path.relative_to(REPO)),
            }
        )

        if profile_path.exists() and not args.overwrite:
            continue

        profile = {
            "speaker_slug": entry["speaker_slug"],
            "speaker_name": person,
            "consent": "confirmed",
            "profile_status": status,
            "source_status": source_status,
            "voice_engine": existing.get("voice_engine", "F5TTS_v1_Base"),
            "roles": sorted(entry["roles"]),
            "interviews": sorted(entry["interviews"]),
            "youtube_query": existing.get("youtube_query", query),
            "source_type": existing.get("source_type", "pending_public_or_local_source"),
            "source_audio": existing.get("source_audio", ""),
            "reference_audio": existing.get("reference_audio", ""),
            "reference_text": existing.get("reference_text", ""),
            "reference_source_start_seconds": existing.get("reference_source_start_seconds", None),
            "reference_duration_seconds": existing.get("reference_duration_seconds", None),
            "demographics": entry["demographics"],
            "notes": existing.get("notes", "Scaffolded profile; source audio and reference clip still need review."),
        }
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    with inventory_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(inventory_rows[0]))
        writer.writeheader()
        writer.writerows(inventory_rows)

    print(f"speakers {len(inventory_rows)}")
    print(inventory_path)


if __name__ == "__main__":
    main()
