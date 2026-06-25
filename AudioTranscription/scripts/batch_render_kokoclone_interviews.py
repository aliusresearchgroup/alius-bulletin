#!/usr/bin/env python3
"""Render KokoClone/Kokoro comparison variants for renderable interview plans."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
DEFAULT_KOKOCLONE_PYTHON = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Codex"
    / "venvs"
    / "f5-tts"
    / "Scripts"
    / "python.exe"
)


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    print(" ".join(cmd), flush=True)
    if not dry_run:
        subprocess.run(cmd, cwd=REPO, check=True)


def coverage_rows(coverage_path: Path, *, refresh: bool, dry_run: bool) -> list[dict[str, str]]:
    if refresh:
        run([sys.executable, str(ROOT / "scripts" / "audit_kokoclone_coverage.py"), "--out", str(coverage_path)], dry_run=dry_run)
    if dry_run and not coverage_path.exists():
        return []
    with coverage_path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, default=ROOT / "kokoclone_coverage.csv")
    parser.add_argument("--kokoclone-dir", type=Path, default=ROOT / "tools" / "kokoclone")
    parser.add_argument("--kokoclone-python", type=Path, default=DEFAULT_KOKOCLONE_PYTHON)
    parser.add_argument("--execution-mode", choices=["api", "cli"], default="api")
    parser.add_argument("--limit", type=int, help="Render at most this many interviews.")
    parser.add_argument("--max-qa-count", type=int, help="Only render interviews with this many QA files or fewer.")
    parser.add_argument("--max-units", type=int, help="Smoke-test limit passed to the renderer.")
    parser.add_argument("--max-chars", type=int, default=320)
    parser.add_argument("--include-rendered", action="store_true", help="Include already-rendered KokoClone interviews.")
    parser.add_argument("--refresh-coverage", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mp3-bitrate", default="128k")
    parser.add_argument("--delivery-preset", choices=["engaged", "neutral"], default="engaged")
    parser.add_argument("--final-tempo", type=float, default=1.0)
    parser.add_argument("--force", action="store_true", help="Rebuild final WAV/MP3/manifest from existing chunks.")
    parser.add_argument("--force-chunks", action="store_true", help="Regenerate chunk WAVs too.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.kokoclone_python.exists() and not args.dry_run:
        raise SystemExit(f"KokoClone Python not found: {args.kokoclone_python}")

    rows = coverage_rows(args.coverage, refresh=args.refresh_coverage, dry_run=args.dry_run)
    queue: list[dict[str, str]] = []
    for row in rows:
        if row.get("renderable") != "yes":
            continue
        if not args.include_rendered and row.get("kokoclone_rendered_mp3") == "yes":
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
            str(args.kokoclone_python),
            str(ROOT / "scripts" / "render_kokoclone_interview.py"),
            "--plan",
            str(plan_path),
            "--kokoclone-dir",
            str(args.kokoclone_dir),
            "--kokoclone-python",
            str(args.kokoclone_python),
            "--execution-mode",
            args.execution_mode,
            "--max-chars",
            str(args.max_chars),
            "--mp3-bitrate",
            args.mp3_bitrate,
            "--delivery-preset",
            args.delivery_preset,
            "--final-tempo",
            str(args.final_tempo),
        ]
        if args.max_units is not None:
            cmd.extend(["--max-units", str(args.max_units)])
        if args.force:
            cmd.append("--force")
        if args.force_chunks:
            cmd.append("--force-chunks")
        run(cmd, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
