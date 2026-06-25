#!/usr/bin/env python3
"""Export a verified interview render into the aliusresearch.org audio shape."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from build_f5_inputs import clean_for_tts


BULLETIN_REPO = Path(__file__).resolve().parents[2]
ROOT = BULLETIN_REPO / "AudioTranscription"
DEFAULT_WEBSITE = BULLETIN_REPO.parent / "aliusresearch.org"


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BULLETIN_REPO / path


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", text)


def qa_title(path: Path, unit: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"QUESTION SPOKEN TEXT:\s*(.+?)(?:\n\s*\n|ANSWER SPOKEN TEXT:)", text, re.S)
    question = clean_for_tts(match.group(1) if match else text)
    question = re.sub(r"\bHwan\b", "Juan", question)
    question = re.sub(r"\balius\b", "ALIUS", question)
    question = " ".join(question.split())
    if len(question) > 82:
        question = question[:79].rstrip() + "..."
    return f"Q&A {unit:03d}: {question}"


def proportional_chapters(plan: dict, duration_ms: int) -> list[dict]:
    qa_dir = repo_path(plan["source_qa_dir"])
    qa_paths = sorted(qa_dir.glob("qa_*.txt"))
    weights = [max(1, len(words(path.read_text(encoding="utf-8", errors="replace")))) for path in qa_paths]
    total = sum(weights) or len(qa_paths) or 1
    chapters: list[dict] = []
    cursor = 0
    for index, path in enumerate(qa_paths):
        unit = index + 1
        if index == len(qa_paths) - 1:
            end = duration_ms
        else:
            end = int(round(duration_ms * sum(weights[: index + 1]) / total))
        chapters.append(
            {
                "unit": unit,
                "start_ms": cursor,
                "end_ms": end,
                "duration_ms": max(0, end - cursor),
                "title": qa_title(path, unit),
            }
        )
        cursor = end
    return chapters


def scaled_or_generated_chapters(chapter_path: Path, plan: dict, duration_ms: int) -> list[dict]:
    if not chapter_path.exists():
        return proportional_chapters(plan, duration_ms)
    old = read_json(chapter_path)
    if not isinstance(old, list) or not old:
        return proportional_chapters(plan, duration_ms)
    old_total = max(int(chapter.get("end_ms") or 0) for chapter in old) or duration_ms
    scale = duration_ms / old_total
    chapters: list[dict] = []
    for index, chapter in enumerate(old):
        start = 0 if index == 0 else int(round(int(chapter["start_ms"]) * scale))
        end = duration_ms if index == len(old) - 1 else int(round(int(chapter["end_ms"]) * scale))
        chapters.append(
            {
                "unit": int(chapter.get("unit") or index + 1),
                "start_ms": start,
                "end_ms": end,
                "duration_ms": max(0, end - start),
                "title": chapter.get("title") or f"Q&A {index + 1:03d}",
            }
        )
    return chapters


def find_card_id(index: dict, interview_id: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for card_id, entry in index.items():
        if isinstance(entry, dict) and entry.get("source_interview_id") == interview_id:
            return card_id
    return None


def public_manifest(manifest: dict, audio_url: str, chapters_url: str) -> dict:
    mp3 = manifest["mp3"]
    post = manifest.get("audio_postprocess") or {}
    return {
        "interview_id": manifest["interview_id"],
        "interview_slug": manifest["interview_slug"],
        "audio": audio_url,
        "chapters": chapters_url,
        "engine": manifest.get("engine"),
        "delivery_preset": post.get("delivery_preset"),
        "final_filter_chain": post.get("ffmpeg_filter_chain"),
        "pronunciation_protocol": manifest.get("pronunciation_protocol"),
        "question_voice_policy": manifest.get("question_voice_policy"),
        "unit_voice_routing": manifest.get("unit_voice_routing", []),
        "duration_seconds": mp3.get("duration_seconds"),
        "codec": mp3.get("codec"),
        "sample_rate_hz": mp3.get("sample_rate_hz"),
        "channels": mp3.get("channels"),
        "bit_rate_bps": mp3.get("bit_rate_bps"),
        "sha256": mp3.get("sha256"),
        "asr_spotcheck": manifest.get("asr_spotcheck"),
        "voice_profiles": [
            {
                "speaker_slug": item.get("speaker_slug"),
                "speaker_name": item.get("speaker_name"),
                "source_url": item.get("source_url"),
                "reference_review_status": item.get("reference_review_status"),
                "profile_gate": item.get("profile_gate"),
            }
            for item in manifest.get("voice_profile_audit", [])
        ],
    }


def export_base(
    base: Path,
    plan: dict,
    manifest: dict,
    card_id: str | None,
    *,
    asset_family: str,
    audio_source: str,
) -> list[Path]:
    issue, interview = manifest["interview_id"].split("/", 1)
    asset_dir = base / asset_family / issue / interview
    audio_url = f"/media/audio/bulletin/{asset_family}/{issue}/{interview}/interview.mp3"
    chapters_url = f"/media/audio/bulletin/{asset_family}/{issue}/{interview}/interview_chapters.json"
    manifest_url = f"/media/audio/bulletin/{asset_family}/{issue}/{interview}/interview_manifest.json"
    duration_ms = int(round(float(manifest["mp3"]["duration_seconds"]) * 1000))

    asset_dir.mkdir(parents=True, exist_ok=True)
    mp3_src = repo_path(manifest["mp3"]["path"])
    mp3_target = asset_dir / "interview.mp3"
    shutil.copy2(mp3_src, mp3_target)
    actual_sha = sha256(mp3_target)
    if manifest["mp3"].get("sha256") and actual_sha != manifest["mp3"]["sha256"]:
        raise RuntimeError(f"SHA mismatch after copy: {mp3_target}")

    chapter_path = asset_dir / "interview_chapters.json"
    chapters = scaled_or_generated_chapters(chapter_path, plan, duration_ms)
    write_json(chapter_path, chapters)

    manifest_path = asset_dir / "interview_manifest.json"
    write_json(manifest_path, public_manifest(manifest, audio_url, chapters_url))

    changed = [mp3_target, chapter_path, manifest_path]
    index_path = base / "transcripts" / "index.json"
    if index_path.exists():
        index = read_json(index_path)
        if not isinstance(index, dict):
            raise RuntimeError(f"Expected object in {index_path}")
        resolved_card_id = find_card_id(index, manifest["interview_id"], card_id)
        if resolved_card_id:
            entry = index.setdefault(resolved_card_id, {})
            entry.update(
                {
                    "unit_count": len(chapters),
                    "source_interview_id": manifest["interview_id"],
                    "audio": audio_url,
                    "audio_download": audio_url,
                    "audio_source": audio_source,
                    "audio_manifest": manifest_url,
                    "audio_chapter_count": len(chapters),
                    "audio_chapters": chapters,
                    "audio_duration_seconds": manifest["mp3"].get("duration_seconds"),
                    "audio_sha256": manifest["mp3"].get("sha256"),
                    "audio_codec": manifest["mp3"].get("codec"),
                    "audio_bit_rate_bps": manifest["mp3"].get("bit_rate_bps"),
                    "audio_sample_rate_hz": manifest["mp3"].get("sample_rate_hz"),
                    "audio_channels": manifest["mp3"].get("channels"),
                    "tts_engine": manifest.get("engine"),
                    "tts_delivery_preset": (manifest.get("audio_postprocess") or {}).get("delivery_preset"),
                    "tts_final_filter_chain": (manifest.get("audio_postprocess") or {}).get("ffmpeg_filter_chain"),
                    "pronunciation_protocol": manifest.get("pronunciation_protocol"),
                    "question_voice_policy": manifest.get("question_voice_policy"),
                    "unit_voice_routing": manifest.get("unit_voice_routing", []),
                    "asr_spotcheck_result": (manifest.get("asr_spotcheck") or {}).get("result"),
                }
            )
            write_json(index_path, index)
            changed.append(index_path)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interview-slug", required=True)
    parser.add_argument("--website-root", type=Path, default=DEFAULT_WEBSITE)
    parser.add_argument("--card-id")
    parser.add_argument(
        "--asset-family",
        default="kokoro",
        help="Public media family directory under /media/audio/bulletin. Use a new value to avoid overwriting older audio.",
    )
    parser.add_argument("--audio-source", default="f5-voice-clone-engaged")
    args = parser.parse_args()

    render_dir = ROOT / "renders" / args.interview_slug
    manifest = read_json(render_dir / "render_manifest.json")
    if not isinstance(manifest, dict):
        raise RuntimeError("render_manifest.json must be an object")
    if (manifest.get("asr_spotcheck") or {}).get("result") != "passed":
        raise RuntimeError("Refusing to export render without asr_spotcheck.result=passed")
    plan = read_json(ROOT / "render_plans" / f"{args.interview_slug}.json")
    if not isinstance(plan, dict):
        raise RuntimeError("render plan must be an object")

    website = args.website_root.resolve()
    bases = [
        website / "docs" / "media" / "audio" / "bulletin",
        website / "site-src" / "static" / "media" / "audio" / "bulletin",
    ]
    changed: list[Path] = []
    for base in bases:
        changed.extend(
            export_base(
                base,
                plan,
                manifest,
                args.card_id,
                asset_family=args.asset_family,
                audio_source=args.audio_source,
            )
        )
    for path in changed:
        print(path)


if __name__ == "__main__":
    main()
