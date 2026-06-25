#!/usr/bin/env python3
"""Remove regenerable work WAVs after verified MP3 renders.

This never deletes source audio, references, or final MP3 renders. It only
touches WAV files under AudioTranscription/work when the corresponding render
manifest has an ASR spot check marked as passed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
WORK_ROOT = (ROOT / "work").resolve()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def is_under_work(path: Path) -> bool:
    try:
        path.resolve().relative_to(WORK_ROOT)
        return True
    except ValueError:
        return False


def mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete files and update manifests.")
    parser.add_argument(
        "--renders-dir",
        type=Path,
        default=ROOT / "renders",
        help="Directory containing per-interview render manifests.",
    )
    args = parser.parse_args()

    candidates: list[tuple[Path, Path, dict]] = []
    for manifest_path in sorted(args.renders_dir.glob("*/render_manifest.json")):
        manifest = read_json(manifest_path)
        if (manifest.get("asr_spotcheck") or {}).get("result") != "passed":
            continue
        wav_info = manifest.get("wav") or {}
        wav_path_text = wav_info.get("path")
        if not wav_path_text:
            continue
        wav_path = repo_path(wav_path_text)
        if wav_path.exists() and is_under_work(wav_path):
            candidates.append((manifest_path, wav_path, manifest))

    total_mb = sum(mb(wav_path) for _, wav_path, _ in candidates)
    action = "delete" if args.apply else "would delete"
    print(f"{action}: {len(candidates)} WAV files, {total_mb:.1f} MB")
    for _, wav_path, _ in candidates:
        print(f"{mb(wav_path):8.1f} MB  {wav_path.relative_to(REPO)}")

    if not args.apply:
        print("dry-run only; pass --apply to remove these regenerable work WAVs")
        return

    for manifest_path, wav_path, manifest in candidates:
        wav_path.unlink()
        wav_info = manifest.setdefault("wav", {})
        wav_info["retained"] = False
        wav_info["cleanup_note"] = (
            "Intermediate work WAV removed after verified MP3 render. "
            "Regenerate with render_interview.py --force if needed."
        )
        write_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
