#!/usr/bin/env python3
"""Render every currently renderable interview plan in a controlled sequence."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    print(" ".join(cmd), flush=True)
    if not dry_run:
        subprocess.run(cmd, cwd=REPO, check=True)


def coverage_rows(coverage_path: Path, *, refresh: bool, dry_run: bool) -> list[dict[str, str]]:
    if refresh:
        run([sys.executable, str(ROOT / "scripts" / "audit_render_coverage.py"), "--out", str(coverage_path)], dry_run=dry_run)
    if dry_run and not coverage_path.exists():
        return []
    with coverage_path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, default=ROOT / "render_coverage.csv")
    parser.add_argument("--limit", type=int, help="Render at most this many interviews.")
    parser.add_argument("--max-qa-count", type=int, help="Only render interviews with this many QA files or fewer.")
    parser.add_argument("--include-rendered", action="store_true", help="Include already-rendered interviews.")
    parser.add_argument("--refresh-coverage", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--nfe-step", type=int, default=16)
    parser.add_argument("--mp3-bitrate", default="128k")
    parser.add_argument("--delivery-preset", choices=["engaged", "neutral"], default="engaged")
    parser.add_argument("--final-tempo", type=float, default=1.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rows = coverage_rows(args.coverage, refresh=args.refresh_coverage, dry_run=args.dry_run)
    queue: list[dict[str, str]] = []
    for row in rows:
        if row.get("renderable") != "yes":
            continue
        if not args.include_rendered and row.get("rendered_mp3") == "yes":
            continue
        if args.max_qa_count is not None and int(row.get("qa_count") or 0) > args.max_qa_count:
            continue
        queue.append(row)

    queue.sort(key=lambda row: (int(row.get("qa_count") or 0), row["interview_slug"]))
    if args.limit is not None:
        queue = queue[: args.limit]

    for index, row in enumerate(queue, start=1):
        slug = row["interview_slug"]
        plan_path = ROOT / "render_plans" / f"{slug}.json"
        print(f"[{index}/{len(queue)}] {slug} ({row.get('qa_count')} QA)", flush=True)
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "render_interview.py"),
            "--plan",
            str(plan_path),
            "--device",
            args.device,
            "--nfe-step",
            str(args.nfe_step),
            "--mp3-bitrate",
            args.mp3_bitrate,
            "--delivery-preset",
            args.delivery_preset,
            "--final-tempo",
            str(args.final_tempo),
        ]
        if args.force:
            cmd.append("--force")
        run(cmd, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
