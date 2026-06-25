#!/usr/bin/env python3
"""Audit F5 voice profiles before interview rendering."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
DEFAULT_MAX_REFERENCE_SECONDS = 11.5

BLOCKING_FLAGS = {
    "missing_reference_audio",
    "missing_reference_audio_file",
    "missing_reference_text",
    "ffprobe_failed",
    "reference_too_long",
    "reference_sha_mismatch",
    "reference_review_failed",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


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


def split_flags(value: str) -> list[str]:
    return [flag for flag in value.split(";") if flag]


def blocking_flags_for_row(row: dict[str, str]) -> list[str]:
    return [flag for flag in split_flags(row.get("risk_flags", "")) if flag in BLOCKING_FLAGS]


def audit_profile(
    profile_path: Path,
    *,
    max_reference_seconds: float = DEFAULT_MAX_REFERENCE_SECONDS,
) -> dict[str, str]:
    profile = read_json(profile_path)
    risk_flags: list[str] = []
    warnings: list[str] = []

    reference_audio = str(profile.get("reference_audio") or "")
    reference_path = repo_path(reference_audio) if reference_audio else None
    declared_duration = profile.get("reference_duration_seconds")
    reference_duration = ""
    declared_duration_delta = ""
    reference_exists = "no"
    reference_sha_status = ""
    actual_sha = ""

    if not reference_audio:
        risk_flags.append("missing_reference_audio")
    elif not reference_path or not reference_path.exists():
        risk_flags.append("missing_reference_audio_file")
    else:
        reference_exists = "yes"
        try:
            duration = ffprobe_duration(reference_path)
            reference_duration = f"{duration:.3f}"
            if duration > max_reference_seconds:
                risk_flags.append("reference_too_long")
        except Exception as exc:
            risk_flags.append("ffprobe_failed")
            reference_duration = exc.__class__.__name__

        try:
            actual_sha = sha256(reference_path)
            expected_sha = str(profile.get("reference_sha256") or "").upper()
            if expected_sha:
                reference_sha_status = "ok" if expected_sha == actual_sha else "mismatch"
                if reference_sha_status == "mismatch":
                    risk_flags.append("reference_sha_mismatch")
            else:
                reference_sha_status = "unrecorded"
                warnings.append("reference_sha_unrecorded")
        except Exception as exc:
            reference_sha_status = f"sha_failed:{exc.__class__.__name__}"
            risk_flags.append("reference_sha_mismatch")

    if declared_duration not in (None, "") and reference_duration and reference_duration.replace(".", "", 1).isdigit():
        delta = abs(float(declared_duration) - float(reference_duration))
        declared_duration_delta = f"{delta:.3f}"
        if delta > 0.25:
            warnings.append("declared_duration_mismatch")

    reference_text = str(profile.get("reference_text") or "").strip()
    if not reference_text:
        risk_flags.append("missing_reference_text")
    reference_text_word_count = str(len(reference_text.split())) if reference_text else "0"

    source_audio = str(profile.get("source_audio") or "")
    if source_audio and not repo_path(source_audio).exists():
        warnings.append("source_audio_missing")
    if profile.get("source_status") == "needs_source":
        warnings.append("source_needs_research")
    if profile.get("profile_status") not in ("working", "candidate_ready"):
        warnings.append("profile_not_ready")
    review_status = str(profile.get("reference_review_status") or "")
    if "failed" in review_status:
        risk_flags.append("reference_review_failed")
    if reference_audio and "asr_spotcheck_passed" not in review_status:
        warnings.append("reference_needs_asr_or_listening_review")

    row = {
        "speaker_slug": profile.get("speaker_slug", profile_path.stem),
        "speaker_name": profile.get("speaker_name", ""),
        "profile_path": str(profile_path),
        "profile_status": profile.get("profile_status", ""),
        "source_status": profile.get("source_status", ""),
        "reference_review_status": review_status,
        "source_audio": source_audio,
        "source_url": profile.get("source_url", ""),
        "reference_audio": reference_audio,
        "reference_exists": reference_exists,
        "reference_duration_seconds": reference_duration,
        "max_reference_seconds": f"{max_reference_seconds:.3f}",
        "declared_reference_duration_seconds": str(declared_duration or ""),
        "declared_duration_delta_seconds": declared_duration_delta,
        "reference_sha_status": reference_sha_status,
        "reference_sha256": profile.get("reference_sha256", ""),
        "actual_reference_sha256": actual_sha,
        "reference_text_word_count": reference_text_word_count,
        "risk_flags": ";".join(dict.fromkeys(risk_flags)),
        "warnings": ";".join(dict.fromkeys(warnings)),
    }
    row["profile_gate"] = "fail" if blocking_flags_for_row(row) else ("warn" if warnings else "pass")
    return row


def audit_profiles(
    profiles_dir: Path,
    *,
    max_reference_seconds: float = DEFAULT_MAX_REFERENCE_SECONDS,
) -> list[dict[str, str]]:
    return [
        audit_profile(path, max_reference_seconds=max_reference_seconds)
        for path in sorted(profiles_dir.glob("*.json"))
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles-dir", type=Path, default=ROOT / "profiles")
    parser.add_argument("--out", type=Path, default=ROOT / "voice_profile_audit.csv")
    parser.add_argument("--max-reference-seconds", type=float, default=DEFAULT_MAX_REFERENCE_SECONDS)
    args = parser.parse_args()

    rows = audit_profiles(args.profiles_dir, max_reference_seconds=args.max_reference_seconds)
    fields = [
        "speaker_slug",
        "speaker_name",
        "profile_path",
        "profile_status",
        "source_status",
        "reference_review_status",
        "source_audio",
        "source_url",
        "reference_audio",
        "reference_exists",
        "reference_duration_seconds",
        "max_reference_seconds",
        "declared_reference_duration_seconds",
        "declared_duration_delta_seconds",
        "reference_sha_status",
        "reference_sha256",
        "actual_reference_sha256",
        "reference_text_word_count",
        "risk_flags",
        "warnings",
        "profile_gate",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["profile_gate"]] = counts.get(row["profile_gate"], 0) + 1
    for key, count in sorted(counts.items()):
        print(f"{key}: {count}")
    print(args.out)


if __name__ == "__main__":
    main()
