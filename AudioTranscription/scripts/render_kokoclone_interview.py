#!/usr/bin/env python3
"""Render an ALIUS interview plan through KokoClone/Kokoro as a comparison engine."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from build_f5_inputs import clean_for_tts, extract_section, read_json, resolve_repo_path
from render_interview import (
    DEFAULT_DELIVERY_PRESET,
    DEFAULT_FINAL_AUDIO_FILTER,
    DELIVERY_PRESETS,
    tempo_filters,
)
from audit_voice_profiles import DEFAULT_MAX_REFERENCE_SECONDS, audit_profile, blocking_flags_for_row


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
SAMPLE_RATE = 24000
FALLBACK_ALLOWED_BLOCKING_FLAGS = {
    "missing_reference_audio",
    "missing_reference_audio_file",
    "missing_reference_text",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


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
    result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "duration_seconds": round(float(fmt.get("duration") or 0.0), 3),
        "codec": stream.get("codec_name", ""),
        "sample_rate_hz": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "bit_rate_bps": int(float(fmt.get("bit_rate") or 0)),
        "sha256": sha256(path),
    }


def profile_path(slug: str) -> Path:
    return ROOT / "profiles" / f"{slug}.json"


def fallback_config(profile: dict) -> dict:
    fallback = profile.get("fallback_voice") or {}
    return fallback if isinstance(fallback, dict) and fallback.get("enabled") else {}


def can_use_fallback(profile: dict, blocking: list[str]) -> bool:
    return bool(fallback_config(profile)) and set(blocking).issubset(FALLBACK_ALLOWED_BLOCKING_FLAGS)


def reference_audio_path(profile: dict) -> Path | None:
    value = str(profile.get("reference_audio") or "")
    if not value:
        return None
    path = resolve_repo_path(value)
    return path if path.exists() else None


def audit_plan_voice_profiles_for_kokoclone(
    plan: dict,
    *,
    max_reference_seconds: float,
) -> tuple[list[dict[str, str]], list[str], dict[str, dict]]:
    rows: list[dict[str, str]] = []
    failures: list[str] = []
    fallbacks: dict[str, dict] = {}
    for slug in dict.fromkeys(plan["voices"].values()):
        path = profile_path(slug)
        if not path.exists():
            failures.append(f"{slug}: missing_profile")
            rows.append(
                {
                    "speaker_slug": slug,
                    "profile_path": str(path),
                    "profile_gate": "fail",
                    "risk_flags": "missing_profile",
                }
            )
            continue
        profile = read_json(path)
        row = audit_profile(path, max_reference_seconds=max_reference_seconds)
        blocking = blocking_flags_for_row(row)
        if blocking and can_use_fallback(profile, blocking):
            fallback = fallback_config(profile)
            fallbacks[slug] = fallback
            row["profile_gate"] = "fallback"
            row["fallback_engine"] = str(fallback.get("engine", "kokoro_onnx"))
            row["fallback_voice"] = str(fallback.get("kokoro_voice", ""))
            row["fallback_lang"] = str(fallback.get("kokoro_lang", "en-us"))
            warnings = [flag for flag in row.get("warnings", "").split(";") if flag]
            warnings.extend(["using_kokoro_fallback_voice", "not_a_real_voice_clone"])
            row["warnings"] = ";".join(dict.fromkeys(warnings))
        elif blocking:
            failures.append(f"{slug}: {', '.join(blocking)}")
        rows.append(row)
    return rows, failures, fallbacks


def split_text(text: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""

    def split_long_sentence(sentence: str) -> list[str]:
        parts: list[str] = []
        current = ""
        for word in sentence.split():
            if current and len(current) + 1 + len(word) > max_chars:
                parts.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            parts.append(current)
        return parts

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(split_long_sentence(sentence))
            continue
        if buf and len(buf) + 1 + len(sentence) > max_chars:
            chunks.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def quoted(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")


def run(cmd: list[str], *, dry_run: bool, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    prefix = f"[cwd={cwd}] " if cwd else ""
    print(prefix + " ".join(str(part) for part in cmd), flush=True)
    if not dry_run:
        subprocess.run(cmd, check=True, cwd=str(cwd) if cwd else None, env=env)


@contextmanager
def pushd(path: Path):
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


class KokoCloneApiRenderer:
    def __init__(self, kokoclone_dir: Path, env: dict[str, str]) -> None:
        self.kokoclone_dir = kokoclone_dir
        self.env = env
        self._cloner = None

    def _load(self):
        if self._cloner is None:
            old_env = os.environ.copy()
            os.environ.update(self.env)
            sys.path.insert(0, str(self.kokoclone_dir))
            try:
                with pushd(self.kokoclone_dir):
                    from core.cloner import KokoClone

                    self._cloner = KokoClone()
            finally:
                os.environ.clear()
                os.environ.update(old_env)
        return self._cloner

    def generate(self, text: str, lang: str, reference_audio: Path, output_path: Path, *, dry_run: bool) -> None:
        print(
            f"[api cwd={self.kokoclone_dir}] KokoClone.generate --lang {lang} "
            f"--ref {reference_audio} --out {output_path} --text {text[:80]!r}",
            flush=True,
        )
        if dry_run:
            return
        old_env = os.environ.copy()
        os.environ.update(self.env)
        try:
            with pushd(self.kokoclone_dir):
                self._load().generate(
                    text=text,
                    lang=lang,
                    reference_audio=str(reference_audio),
                    output_path=str(output_path),
                )
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def generate_kokoro(self, text: str, fallback: dict, output_path: Path, *, dry_run: bool) -> None:
        voice = str(fallback.get("kokoro_voice") or "af_aoede")
        lang = str(fallback.get("kokoro_lang") or "en-us")
        speed = float(fallback.get("speed") or 0.9)
        print(
            f"[api cwd={self.kokoclone_dir}] Kokoro.fallback --voice {voice} --lang {lang} "
            f"--out {output_path} --text {text[:80]!r}",
            flush=True,
        )
        if dry_run:
            return
        old_env = os.environ.copy()
        os.environ.update(self.env)
        try:
            with pushd(self.kokoclone_dir):
                cloner = self._load()
                model_file = cloner._ensure_file("model", "kokoro.onnx")
                voices_file = cloner._ensure_file("voice", "voices-v1.0.bin")
                if model_file not in cloner.kokoro_cache:
                    from kokoro_onnx import Kokoro

                    cloner.kokoro_cache[model_file] = cloner._patch_kokoro_compat(Kokoro(model_file, voices_file))
                samples, sr = cloner.kokoro_cache[model_file].create(text, voice=voice, speed=speed, lang=lang)
                import soundfile as sf

                sf.write(str(output_path), samples, sr)
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def make_silence(path: Path, seconds: float, *, dry_run: bool) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={SAMPLE_RATE}:cl=mono",
        "-t",
        f"{seconds:.3f}",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "1",
        str(path),
    ]
    run(cmd, dry_run=dry_run)


def concat_wavs(inputs: list[Path], output: Path, *, dry_run: bool) -> None:
    concat_file = output.with_suffix(".concat.txt")
    concat_file.write_text(
        "\n".join(f"file '{quoted(path.resolve())}'" for path in inputs) + "\n",
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        "1",
        str(output),
    ]
    run(cmd, dry_run=dry_run)


def filter_chain(delivery_preset: str, final_audio_filter: str, final_tempo: float) -> str:
    filters: list[str] = []
    delivery = DELIVERY_PRESETS.get(delivery_preset, "")
    if delivery:
        filters.append(delivery)
    if final_audio_filter:
        filters.append(final_audio_filter)
    filters.extend(tempo_filters(final_tempo))
    return ",".join(filters)


def transcode_mp3(wav: Path, mp3: Path, filter_text: str, bitrate: str, *, dry_run: bool) -> None:
    cmd = ["ffmpeg", "-y", "-i", str(wav)]
    if filter_text:
        cmd.extend(["-af", filter_text])
    cmd.extend(["-ar", str(SAMPLE_RATE), "-ac", "1", "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3)])
    run(cmd, dry_run=dry_run)


def kokoclone_cli(kokoclone_dir: Path) -> Path:
    cli = kokoclone_dir / "cli.py"
    if not cli.exists():
        raise FileNotFoundError(f"KokoClone cli.py not found: {cli}")
    return cli


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--kokoclone-dir", type=Path, default=os.environ.get("KOKOCLONE_DIR"))
    parser.add_argument("--kokoclone-python", default=sys.executable)
    parser.add_argument("--hf-home", type=Path, default=ROOT / "cache" / "huggingface")
    parser.add_argument("--execution-mode", choices=["api", "cli"], default="api")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--max-units", type=int)
    parser.add_argument("--max-chars", type=int, default=700)
    parser.add_argument("--mp3-bitrate", default="128k")
    parser.add_argument("--delivery-preset", choices=sorted(DELIVERY_PRESETS), default=DEFAULT_DELIVERY_PRESET)
    parser.add_argument("--final-audio-filter", default=DEFAULT_FINAL_AUDIO_FILTER)
    parser.add_argument("--final-tempo", type=float, default=1.0)
    parser.add_argument("--max-reference-seconds", type=float, default=DEFAULT_MAX_REFERENCE_SECONDS)
    parser.add_argument("--skip-profile-audit", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-chunks", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.kokoclone_dir:
        raise SystemExit("Pass --kokoclone-dir or set KOKOCLONE_DIR to a KokoClone checkout.")

    plan_path = resolve_repo_path(str(args.plan))
    plan = read_json(plan_path)
    voice_profile_audit, voice_profile_failures, fallback_by_slug = audit_plan_voice_profiles_for_kokoclone(
        plan,
        max_reference_seconds=args.max_reference_seconds,
    )
    if voice_profile_failures and not args.skip_profile_audit:
        details = "\n  ".join(voice_profile_failures)
        raise SystemExit(f"Voice profile audit failed:\n  {details}")

    slug = plan["interview_slug"]
    render_dir = ROOT / "renders_kokoclone" / slug
    work_dir = ROOT / "work" / "kokoclone" / slug
    render_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    output_stem = f"{plan['output_file_stem']}_kokoclone"
    full_wav = work_dir / f"{output_stem}.wav"
    full_mp3 = render_dir / f"{output_stem}.mp3"
    if full_mp3.exists() and not args.force:
        print(f"exists: {full_mp3}")
        return

    kokoclone_dir = args.kokoclone_dir.resolve()
    cli_path = kokoclone_cli(kokoclone_dir)
    hf_home = resolve_repo_path(str(args.hf_home))
    hf_home.mkdir(parents=True, exist_ok=True)
    kokoclone_env = os.environ.copy()
    kokoclone_env.setdefault("HF_HOME", str(hf_home.resolve()))
    api_renderer = KokoCloneApiRenderer(kokoclone_dir, kokoclone_env) if args.execution_mode == "api" else None
    profiles = {slug_: read_json(profile_path(slug_)) for slug_ in dict.fromkeys(plan["voices"].values())}
    qa_paths = sorted(resolve_repo_path(plan["source_qa_dir"]).glob("qa_*.txt"))
    if args.max_units is not None:
        qa_paths = qa_paths[: max(0, args.max_units)]

    silence_short = work_dir / "silence_250ms.wav"
    silence_turn = work_dir / "silence_650ms.wav"
    if args.force_chunks or not silence_short.exists():
        make_silence(silence_short, 0.25, dry_run=args.dry_run)
    if args.force_chunks or not silence_turn.exists():
        make_silence(silence_turn, 0.65, dry_run=args.dry_run)

    concat_inputs: list[Path] = []
    units: list[dict] = []
    fallback_usage: dict[str, dict] = {}
    for unit_number, qa_path in enumerate(qa_paths, start=1):
        raw = qa_path.read_text(encoding="utf-8")
        sections = [
            ("question", plan["voices"]["question"], extract_section(raw, "QUESTION SPOKEN TEXT:", "ANSWER SPOKEN TEXT:")),
            ("answer", plan["voices"]["answer"], extract_section(raw, "ANSWER SPOKEN TEXT:")),
        ]
        unit_chunks = 0
        for role, voice_slug, text in sections:
            profile = profiles[voice_slug]
            ref_audio = reference_audio_path(profile)
            fallback = fallback_by_slug.get(voice_slug)
            if fallback and args.execution_mode != "api":
                raise SystemExit("Kokoro fallback voices require --execution-mode api")
            for chunk_index, chunk in enumerate(split_text(clean_for_tts(text), args.max_chars), start=1):
                unit_chunks += 1
                out = work_dir / f"qa_{unit_number:03d}_{role}_{chunk_index:03d}.wav"
                if args.force_chunks or not out.exists():
                    if fallback and api_renderer:
                        api_renderer.generate_kokoro(chunk, fallback, out, dry_run=args.dry_run)
                        fallback_usage[voice_slug] = fallback
                    elif api_renderer and ref_audio:
                        api_renderer.generate(chunk, args.lang, ref_audio, out, dry_run=args.dry_run)
                    elif not ref_audio:
                        raise SystemExit(f"No reference audio or fallback voice for profile: {voice_slug}")
                    else:
                        cmd = [
                            args.kokoclone_python,
                            str(cli_path),
                            "--mode",
                            "tts",
                            "--text",
                            chunk,
                            "--lang",
                            args.lang,
                            "--ref",
                            str(ref_audio),
                            "--out",
                            str(out),
                        ]
                        run(cmd, dry_run=args.dry_run, cwd=kokoclone_dir, env=kokoclone_env)
                concat_inputs.append(out)
                concat_inputs.append(silence_short)
            concat_inputs.append(silence_turn)
        units.append({"index": unit_number, "source": str(qa_path), "chunks": unit_chunks})

    if concat_inputs and concat_inputs[-1] == silence_turn:
        concat_inputs.pop()
    concat_wavs(concat_inputs, full_wav, dry_run=args.dry_run)
    filters = filter_chain(args.delivery_preset, args.final_audio_filter, args.final_tempo)
    transcode_mp3(full_wav, full_mp3, filters, args.mp3_bitrate, dry_run=args.dry_run)

    manifest = {
        "interview_id": plan["interview_id"],
        "interview_slug": slug,
        "status": "dry_run" if args.dry_run else "rendered",
        "engine": "KokoClone_Kokoro_ONNX_Kanade",
        "mode": "tts_then_voice_conversion",
        "execution_mode": args.execution_mode,
        "kokoclone_dir": str(kokoclone_dir),
        "kokoclone_cwd": str(kokoclone_dir),
        "kokoclone_cli": str(cli_path),
        "hf_home": str(hf_home.resolve()),
        "lang": args.lang,
        "max_chars": args.max_chars,
        "units": units,
        "audio_postprocess": {
            "delivery_preset": args.delivery_preset,
            "delivery_filter": DELIVERY_PRESETS.get(args.delivery_preset, ""),
            "final_audio_filter": args.final_audio_filter,
            "final_tempo": args.final_tempo,
            "ffmpeg_filter_chain": filters,
            "target_sample_rate_hz": SAMPLE_RATE,
            "target_channels": 1,
        },
        "text_protocol": "output/audio_interviews qa_*.txt QUESTION/ANSWER SPOKEN TEXT",
        "pronunciation_protocol": "Uppercase ALIUS / A.L.I.U.S. is normalized to lowercase alius for spoken rendering.",
        "max_units": args.max_units,
        "voice_profiles": [str(profile_path(slug_)) for slug_ in profiles],
        "voice_profile_audit": voice_profile_audit,
        "fallback_voice_usage": {
            slug: {
                "engine": fallback.get("engine", "kokoro_onnx"),
                "kokoro_voice": fallback.get("kokoro_voice"),
                "kokoro_lang": fallback.get("kokoro_lang", "en-us"),
                "selection_reason": fallback.get("selection_reason", ""),
                "not_a_real_voice_clone": True,
            }
            for slug, fallback in sorted(fallback_usage.items())
        },
        "human_listening_check": "pending",
    }
    if not args.dry_run:
        manifest["wav"] = {"path": str(full_wav), **ffprobe(full_wav)}
        manifest["mp3"] = {"path": str(full_mp3), **ffprobe(full_mp3)}
    (render_dir / "render_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(full_mp3)


if __name__ == "__main__":
    main()
