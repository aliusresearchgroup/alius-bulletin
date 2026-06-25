#!/usr/bin/env python3
"""Apply reference candidates to speaker profile JSON files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
PROFILES = ROOT / "profiles"
CANDIDATES = ROOT / "sources" / "reference_candidates.csv"


def relpath(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        return value.replace("\\", "/")
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def latest_candidates(path: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            latest[row["speaker_slug"]] = row
    return latest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=CANDIDATES)
    parser.add_argument("--profiles-dir", type=Path, default=PROFILES)
    parser.add_argument("--skip-working", action="store_true")
    args = parser.parse_args()

    changed = []
    for slug, row in latest_candidates(args.candidates).items():
        profile_path = args.profiles_dir / f"{slug}.json"
        if not profile_path.exists():
            continue
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if args.skip_working and profile.get("profile_status") == "working":
            continue

        profile["profile_status"] = "candidate_ready"
        profile["source_status"] = "downloaded_reference_candidate"
        profile["source_type"] = "youtube_source_candidate"
        profile["source_audio"] = relpath(row["source_audio"])
        profile["source_url"] = row["source_url"]
        profile["source_title"] = row["source_title"]
        profile["source_channel"] = row["source_channel"]
        profile["reference_audio"] = relpath(row["reference_audio"])
        profile["reference_text"] = row["reference_text"]
        profile["reference_source_start_seconds"] = float(row["reference_source_start_seconds"])
        profile["reference_duration_seconds"] = float(row["reference_duration_seconds"])
        profile["reference_filter_preset"] = row["reference_filter_preset"]
        profile["reference_sha256"] = row["reference_sha256"]
        profile["reference_review_status"] = row["review_status"]
        profile["notes"] = (
            "YouTube source and cleaned reference candidate are present. "
            "Run listening review before marking this profile working."
        )
        profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.append(slug)

    print(f"updated {len(changed)} profiles")
    for slug in changed:
        print(slug)


if __name__ == "__main__":
    main()
