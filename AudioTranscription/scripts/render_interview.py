#!/usr/bin/env python3
"""Build, render, transcode, and manifest one F5-TTS interview plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from build_f5_inputs import collect_plan_speaker_slugs
from audit_voice_profiles import (
    DEFAULT_MAX_REFERENCE_SECONDS,
    audit_profile,
    blocking_flags_for_row,
)


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
DEFAULT_F5_PYTHON = Path(os.environ.get("LOCALAPPDATA", "")) / "Codex" / "venvs" / "f5-tts" / "Scripts" / "python.exe"
DEFAULT_FINAL_AUDIO_FILTER = "loudnorm=I=-18:TP=-2:LRA=11"
DEFAULT_DELIVERY_PRESET = "engaged"
DELIVERY_PRESETS = {
    "neutral": "",
    # Mild broadcast-style presence and dynamics. This is not emotion synthesis;
    # reference selection is still the main way to inherit engaged intonation.
    "engaged": (
        "equalizer=f=3200:t=q:w=1.1:g=1.2,"
        "equalizer=f=6500:t=q:w=1.4:g=0.6,"
        "acompressor=threshold=-22dB:ratio=1.4:attack=5:release=90:makeup=1.0"
    ),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def run(cmd: list[str], *, dry_run: bool = False) -> None:
    print(" ".join(cmd), file=sys.stderr)
    if dry_run:
        return
    subprocess.run(cmd, cwd=REPO, check=True)


def ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,bit_rate:stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "duration_seconds": round(float(fmt.get("duration", 0.0)), 3),
        "codec": stream.get("codec_name", ""),
        "sample_rate_hz": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
        "channels": stream.get("channels"),
        "bit_rate_bps": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def tempo_filters(value: float) -> list[str]:
    """Build ffmpeg atempo filters, which only accept values in [0.5, 2.0]."""
    if value <= 0:
        raise ValueError("--final-tempo must be positive")
    filters: list[str] = []
    remaining = value
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    if abs(remaining - 1.0) > 0.001:
        filters.append(f"atempo={remaining:.6g}")
    return filters


def audit_plan_voice_profiles(plan: dict, *, max_reference_seconds: float) -> tuple[list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    failures: list[str] = []
    for slug in collect_plan_speaker_slugs(plan):
        profile_path = ROOT / "profiles" / f"{slug}.json"
        if not profile_path.exists():
            failures.append(f"{slug}: missing_profile")
            rows.append(
                {
                    "speaker_slug": slug,
                    "profile_path": str(profile_path),
                    "profile_gate": "fail",
                    "risk_flags": "missing_profile",
                }
            )
            continue
        row = audit_profile(profile_path, max_reference_seconds=max_reference_seconds)
        rows.append(row)
        blocking = blocking_flags_for_row(row)
        if blocking:
            failures.append(f"{slug}: {', '.join(blocking)}")
    return rows, failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--nfe-step", type=int, default=16)
    parser.add_argument("--f5-python", type=Path, default=DEFAULT_F5_PYTHON)
    parser.add_argument("--mp3-bitrate", default="128k")
    parser.add_argument(
        "--final-audio-filter",
        default=DEFAULT_FINAL_AUDIO_FILTER,
        help="ffmpeg -af filter applied while exporting the final MP3. Default standardizes loudness.",
    )
    parser.add_argument(
        "--delivery-preset",
        choices=sorted(DELIVERY_PRESETS),
        default=DEFAULT_DELIVERY_PRESET,
        help="Optional mild final-delivery shaping. Use engaged for a brighter, more energetic export.",
    )
    parser.add_argument(
        "--final-tempo",
        type=float,
        default=1.0,
        help="Optional final tempo multiplier for whole-interview pace correction. 1.0 leaves timing unchanged.",
    )
    parser.add_argument("--max-units", type=int, help="Limit the number of qa_*.txt units for smoke-test renders.")
    parser.add_argument("--output-suffix", default="", help="Append a suffix to the plan output_file_stem.")
    parser.add_argument("--max-reference-seconds", type=float, default=DEFAULT_MAX_REFERENCE_SECONDS)
    parser.add_argument("--skip-profile-audit", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--transcode-only",
        action="store_true",
        help="Skip F5 synthesis and rebuild the MP3/manifest from the existing work WAV.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    plan_path = repo_path(args.plan)
    plan = read_json(plan_path)
    voice_profile_audit, voice_profile_failures = audit_plan_voice_profiles(
        plan,
        max_reference_seconds=args.max_reference_seconds,
    )
    if voice_profile_failures and not args.skip_profile_audit and not args.transcode_only:
        details = "\n  ".join(voice_profile_failures)
        raise SystemExit(f"Voice profile audit failed:\n  {details}")

    slug = plan["interview_slug"]
    stem = plan["output_file_stem"] + args.output_suffix
    work_dir = ROOT / "work" / slug
    render_dir = ROOT / "renders" / slug
    render_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = render_dir / f"{stem}.mp3"
    if mp3_path.exists() and not args.force:
        print(f"exists: {mp3_path}")
        return

    config_path = work_dir / "f5_config.toml"
    wav_path = work_dir / f"{stem}.wav"

    if not args.transcode_only:
        build_cmd = [
            sys.executable,
            str(ROOT / "scripts" / "build_f5_inputs.py"),
            "--plan",
            str(plan_path),
            "--work-dir",
            str(work_dir),
        ]
        if args.max_units is not None:
            build_cmd.extend(["--max-units", str(args.max_units)])
        if args.output_suffix:
            build_cmd.extend(["--output-file-stem", stem])
        run(build_cmd, dry_run=args.dry_run)

        f5_cmd = [
            str(args.f5_python),
            str(ROOT / "scripts" / "run_f5_soundfile.py"),
            "--config",
            str(config_path),
            "--device",
            args.device,
            "--nfe_step",
            str(args.nfe_step),
        ]
        run(f5_cmd, dry_run=args.dry_run)
    if args.dry_run:
        return
    if not wav_path.exists():
        raise SystemExit(f"Expected WAV missing after render: {wav_path}")

    input_manifest_path = work_dir / "input_manifest.json"
    input_manifest = read_json(input_manifest_path) if input_manifest_path.exists() else {}

    final_filters = []
    delivery_filter = DELIVERY_PRESETS[args.delivery_preset]
    if delivery_filter:
        final_filters.append(delivery_filter)
    if args.final_audio_filter:
        final_filters.append(args.final_audio_filter)
    final_filters.extend(tempo_filters(args.final_tempo))

    ffmpeg_cmd = [
        "ffmpeg",
        "-y" if args.force else "-n",
        "-i",
        str(wav_path),
    ]
    if final_filters:
        ffmpeg_cmd.extend(["-af", ",".join(final_filters)])
    ffmpeg_cmd.extend(
        [
            "-ar",
            "24000",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            args.mp3_bitrate,
            str(mp3_path),
        ]
    )
    run(ffmpeg_cmd)

    manifest = {
        "interview_id": plan["interview_id"],
        "interview_slug": slug,
        "status": "rendered",
        "engine": plan.get("tts", {}).get("model", "F5TTS_v1_Base"),
        "device": args.device,
        "nfe_step": args.nfe_step,
        "tts_speed": float(plan.get("tts", {}).get("speed", 1.0)),
        "tts_voice_speeds": plan.get("tts", {}).get("voice_speeds", {}),
        "audio_postprocess": {
            "delivery_preset": args.delivery_preset,
            "delivery_filter": delivery_filter,
            "final_audio_filter": args.final_audio_filter,
            "final_tempo": args.final_tempo,
            "ffmpeg_filter_chain": ",".join(final_filters),
            "target_sample_rate_hz": 24000,
            "target_channels": 1,
        },
        "text_protocol": "output/audio_interviews qa_*.txt QUESTION/ANSWER SPOKEN TEXT",
        "pronunciation_protocol": "Uppercase ALIUS / A.L.I.U.S. is normalized to lowercase alius for spoken rendering; common formal symbols are converted to spoken forms; selected proper names may be phonetically normalized for speech.",
        "question_voice_policy": input_manifest.get("question_voice_policy"),
        "unit_voice_routing": [
            {
                "unit": unit.get("index"),
                "question_voice": unit.get("question_voice"),
                "answer_voice": unit.get("answer_voice"),
                "answer_voice_segments": unit.get("answer_voice_segments", []),
            }
            for unit in input_manifest.get("units", [])
        ],
        "max_units": args.max_units,
        "config": str(config_path),
        "wav": {"path": str(wav_path), **ffprobe(wav_path), "sha256": sha256(wav_path)},
        "mp3": {"path": str(mp3_path), **ffprobe(mp3_path), "sha256": sha256(mp3_path)},
        "voice_profiles": [str(ROOT / "profiles" / f"{slug}.json") for slug in collect_plan_speaker_slugs(plan)],
        "voice_profile_audit": voice_profile_audit,
        "human_listening_check": "pending",
    }
    manifest_name = f"render_manifest{args.output_suffix}.json" if args.output_suffix else "render_manifest.json"
    manifest_path = render_dir / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(mp3_path)


if __name__ == "__main__":
    main()
