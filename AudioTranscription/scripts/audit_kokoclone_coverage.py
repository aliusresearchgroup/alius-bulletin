#!/usr/bin/env python3
"""Audit KokoClone/Kokoro comparison renders for ALIUS interview plans."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from audit_render_coverage import (
    REPO,
    ROOT,
    asr_status,
    ffprobe_duration,
    profile_ok,
    read_json,
    repo_path,
    sha256,
)
from audit_voice_profiles import (
    DEFAULT_MAX_REFERENCE_SECONDS,
    audit_profile,
    blocking_flags_for_row,
)
from render_kokoclone_interview import can_use_fallback, fallback_config


def kokoclone_render_status(
    mp3_path: Path,
    manifest_path: Path,
    plan: dict,
    *,
    max_reference_seconds: float,
) -> tuple[str, str]:
    if not mp3_path.exists():
        return "no", "missing_mp3"
    try:
        duration = ffprobe_duration(mp3_path)
    except Exception as exc:
        return "no", f"ffprobe_failed:{exc.__class__.__name__}"
    if duration <= 0:
        return "no", "invalid_duration"
    if not manifest_path.exists():
        return "no", "missing_manifest"
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        return "no", f"manifest_read_failed:{exc.__class__.__name__}"
    mp3_manifest = manifest.get("mp3") or {}
    expected_sha = mp3_manifest.get("sha256")
    if expected_sha and expected_sha != sha256(mp3_path):
        return "no", "manifest_sha_mismatch"
    expected_duration = float(mp3_manifest.get("duration_seconds") or 0.0)
    if expected_duration and abs(expected_duration - duration) > 1.0:
        return "no", "manifest_duration_mismatch"
    manifest_profile_audit = manifest.get("voice_profile_audit") or []
    if not manifest_profile_audit:
        return "no", "missing_voice_profile_audit"
    manifest_profiles = {
        row.get("speaker_slug"): row
        for row in manifest_profile_audit
        if isinstance(row, dict) and row.get("speaker_slug")
    }
    for slug in dict.fromkeys(plan["voices"].values()):
        profile_path = ROOT / "profiles" / f"{slug}.json"
        if not profile_path.exists():
            return "no", f"current_profile_missing:{slug}"
        profile = read_json(profile_path)
        current = audit_profile(profile_path, max_reference_seconds=max_reference_seconds)
        current_blocking = blocking_flags_for_row(current)
        fallback_allowed = current_blocking and can_use_fallback(profile, current_blocking)
        if current_blocking and not fallback_allowed:
            return "no", f"current_profile_failed:{slug}:{','.join(current_blocking)}"
        previous = manifest_profiles.get(slug)
        if not previous:
            return "no", f"manifest_missing_profile_audit:{slug}"
        if fallback_allowed:
            fallback = fallback_config(profile)
            manifest_fallback = (manifest.get("fallback_voice_usage") or {}).get(slug)
            if not manifest_fallback:
                return "no", f"manifest_missing_fallback_usage:{slug}"
            if manifest_fallback.get("kokoro_voice") != fallback.get("kokoro_voice"):
                return "no", f"fallback_voice_changed:{slug}"
            continue
        for key in ("reference_audio", "actual_reference_sha256"):
            if previous.get(key) != current.get(key):
                return "no", f"voice_profile_changed:{slug}:{key}"
    return "yes", "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "kokoclone_coverage.csv")
    parser.add_argument("--max-reference-seconds", type=float, default=DEFAULT_MAX_REFERENCE_SECONDS)
    args = parser.parse_args()

    profiles = {path.stem: read_json(path) for path in (ROOT / "profiles").glob("*.json")}
    rows: list[dict[str, str | int]] = []
    for plan_path in sorted((ROOT / "render_plans").glob("*.json")):
        plan = read_json(plan_path)
        voice_slugs = list(dict.fromkeys(plan["voices"].values()))
        voice_statuses: list[str] = []
        missing: list[str] = []
        profile_reference_failures: list[str] = []
        candidate_only: list[str] = []
        for slug in voice_slugs:
            profile = profiles.get(slug)
            if not profile:
                voice_statuses.append(f"{slug}:missing_profile")
                missing.append(slug)
                profile_reference_failures.append(f"{slug}:missing_profile")
                continue
            profile_audit = audit_profile(
                ROOT / "profiles" / f"{slug}.json",
                max_reference_seconds=args.max_reference_seconds,
            )
            blocking = blocking_flags_for_row(profile_audit)
            fallback = fallback_config(profile)
            voice_statuses.append(
                f"{slug}:{profile.get('profile_status', '')}/{profile.get('source_status', '')}/"
                f"gate={profile_audit['profile_gate']}/ref={'yes' if profile_ok(profile) else 'no'}"
                f"/fallback={'yes' if fallback else 'no'}"
            )
            if blocking:
                if can_use_fallback(profile, blocking):
                    candidate_only.append(f"{slug}:kokoro_fallback:{fallback.get('kokoro_voice', '')}")
                else:
                    profile_reference_failures.append(f"{slug}:{','.join(blocking)}")
                    missing.append(slug)
            elif profile.get("profile_status") != "working":
                candidate_only.append(slug)

        qa_dir = repo_path(plan["source_qa_dir"])
        qa_count = len(list(qa_dir.glob("qa_*.txt"))) if qa_dir.exists() else 0
        render_mp3 = ROOT / "renders_kokoclone" / plan["interview_slug"] / f"{plan['output_file_stem']}_kokoclone.mp3"
        manifest_path = ROOT / "renders_kokoclone" / plan["interview_slug"] / "render_manifest.json"
        rendered_mp3, render_probe_status = kokoclone_render_status(
            render_mp3,
            manifest_path,
            plan,
            max_reference_seconds=args.max_reference_seconds,
        )
        rows.append(
            {
                "interview_slug": plan["interview_slug"],
                "interview_id": plan["interview_id"],
                "qa_count": qa_count,
                "renderable": "yes" if not missing and qa_count else "no",
                "candidate_only_profiles": ";".join(candidate_only),
                "missing_profiles": ";".join(missing),
                "profile_reference_failures": ";".join(profile_reference_failures),
                "kokoclone_rendered_mp3": rendered_mp3,
                "kokoclone_probe_status": render_probe_status,
                "kokoclone_asr_spotcheck_result": asr_status(manifest_path),
                "voices": "; ".join(voice_statuses),
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "interview_slug",
        "interview_id",
        "qa_count",
        "renderable",
        "candidate_only_profiles",
        "missing_profiles",
        "profile_reference_failures",
        "kokoclone_rendered_mp3",
        "kokoclone_probe_status",
        "kokoclone_asr_spotcheck_result",
        "voices",
    ]
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['renderable']}/{row['kokoclone_rendered_mp3']}"
        counts[key] = counts.get(key, 0) + 1
    for key, count in sorted(counts.items()):
        print(f"{key}: {count}")
    print(args.out)


if __name__ == "__main__":
    main()
