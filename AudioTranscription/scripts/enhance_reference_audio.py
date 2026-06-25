#!/usr/bin/env python3
"""Enhance and trim speaker reference audio for F5-TTS voice profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FILTERS = ROOT / "config" / "audio_filters.json"
DEFAULT_MAX_REFERENCE_SECONDS = 11.5


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size,bit_rate:stream=codec_name,channels,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preset", default="speech_reference_crisp_noisy_mic")
    parser.add_argument("--start", type=float)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--max-reference-seconds", type=float, default=DEFAULT_MAX_REFERENCE_SECONDS)
    parser.add_argument(
        "--allow-long-reference",
        action="store_true",
        help="Allow references longer than the F5-safe default for controlled experiments only.",
    )
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    presets = json.loads(FILTERS.read_text(encoding="utf-8"))
    if args.preset not in presets:
        raise SystemExit(f"Unknown preset {args.preset}. Available: {', '.join(sorted(presets))}")

    preset = presets[args.preset]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.allow_long_reference:
        if args.duration is None:
            raise SystemExit(
                "Reference creation requires --duration so F5 does not receive an overlong prompt. "
                "Use --allow-long-reference only for controlled experiments."
            )
        if args.duration > args.max_reference_seconds:
            raise SystemExit(
                f"Reference duration {args.duration}s exceeds the F5-safe limit "
                f"of {args.max_reference_seconds}s."
            )

    cmd = ["ffmpeg", "-hide_banner", "-y"]
    if args.start is not None:
        cmd.extend(["-ss", str(args.start)])
    if args.duration is not None:
        cmd.extend(["-t", str(args.duration)])
    cmd.extend(
        [
            "-i",
            str(args.input),
            "-vn",
            "-af",
            preset["ffmpeg_filter"],
            "-ar",
            str(preset["sample_rate_hz"]),
            "-ac",
            str(preset["channels"]),
            str(args.output),
        ]
    )
    subprocess.run(cmd, check=True)

    output_probe = ffprobe(args.output)
    output_duration = float((output_probe.get("format") or {}).get("duration") or 0.0)
    if output_duration > args.max_reference_seconds and not args.allow_long_reference:
        raise SystemExit(
            f"Created reference is {output_duration:.3f}s, above the F5-safe limit "
            f"of {args.max_reference_seconds}s."
        )

    manifest_path = args.manifest or args.output.with_suffix(args.output.suffix + ".manifest.json")
    manifest = {
        "input": str(args.input),
        "output": str(args.output),
        "preset": args.preset,
        "preset_description": preset["description"],
        "ffmpeg_filter": preset["ffmpeg_filter"],
        "start_seconds": args.start,
        "duration_seconds": args.duration,
        "max_reference_seconds": args.max_reference_seconds,
        "allow_long_reference": args.allow_long_reference,
        "output_probe": output_probe,
        "input_sha256": sha256(args.input) if args.input.exists() else "",
        "output_sha256": sha256(args.output),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(args.output)
    print(manifest_path)


if __name__ == "__main__":
    main()
