#!/usr/bin/env python3
"""Generate F5-compatible reference WAVs for Kokoro fallback voices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
DEFAULT_MODEL = ROOT / "tools" / "kokoclone" / "model" / "kokoro.onnx"
DEFAULT_VOICES = ROOT / "tools" / "kokoclone" / "voice" / "voices-v1.0.bin"
DEFAULT_REFERENCE_TEXT = (
    "This interview explores perception, experience, and consciousness "
    "through careful questions and an open, steady conversation."
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
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


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, help="Speaker slug, for example cordelia_erickson_davis.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--voices", type=Path, default=DEFAULT_VOICES)
    parser.add_argument("--reference-text", default=DEFAULT_REFERENCE_TEXT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    profile_path = ROOT / "profiles" / f"{args.profile}.json"
    profile = read_json(profile_path)
    fallback = profile.get("fallback_voice") or {}
    if not fallback.get("enabled"):
        raise SystemExit(f"Profile has no enabled fallback_voice: {profile_path}")
    if fallback.get("engine") != "kokoro_onnx":
        raise SystemExit(f"Unsupported fallback engine for this materializer: {fallback.get('engine')}")

    voice = str(fallback["kokoro_voice"])
    lang = str(fallback.get("kokoro_lang") or "en-us")
    speed = float(fallback.get("speed") or 1.0)
    out_dir = ROOT / "references" / "fallback" / args.profile
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.profile}_kokoro_{voice}_ref.wav"
    if out_path.exists() and not args.force:
        raise SystemExit(f"exists: {out_path}")

    from kokoro_onnx import Kokoro
    import soundfile as sf

    kokoro = Kokoro(str(args.model), str(args.voices))
    audio, sample_rate = kokoro.create(
        args.reference_text,
        voice=voice,
        speed=speed,
        lang=lang,
        trim=True,
    )
    sf.write(out_path, audio, sample_rate)

    duration = round(ffprobe_duration(out_path), 3)
    if duration > 11.5:
        raise SystemExit(f"Fallback reference is too long for F5 profile gate: {duration}s")

    fallback_reference = {
        "generated": True,
        "engine": "kokoro_onnx",
        "kokoro_voice": voice,
        "kokoro_lang": lang,
        "speed": speed,
        "not_a_real_voice_clone": True,
        "selection_reason": fallback.get("selection_reason", ""),
    }
    profile.update(
        {
            "profile_status": "candidate_ready",
            "source_status": "kokoro_fallback_reference_generated",
            "source_type": "kokoro_fallback_reference",
            "source_audio": repo_relative(out_path),
            "reference_audio": repo_relative(out_path),
            "reference_text": args.reference_text,
            "reference_source_start_seconds": 0,
            "reference_duration_seconds": duration,
            "reference_sha256": sha256(out_path),
            "reference_review_status": "kokoro_fallback_generated_not_real_voice_clone",
            "fallback_reference": fallback_reference,
        }
    )
    write_json(profile_path, profile)
    print(out_path)


if __name__ == "__main__":
    main()
