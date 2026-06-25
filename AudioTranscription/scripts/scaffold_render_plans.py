#!/usr/bin/env python3
"""Scaffold render plans for every real ALIUS interview with Q/A audio text."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
PARTICIPANTS = REPO / "AI-agents" / "interview_audio_participants.csv"
QA_ROOT = REPO / "output" / "audio_interviews"


def slugify(name: str) -> str:
    text = name.lower()
    text = text.replace("'", "")
    text = text.replace(".", "")
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    render_dir = ROOT / "render_plans"
    render_dir.mkdir(parents=True, exist_ok=True)

    by_interview: dict[str, dict[str, list[str]]] = {}
    for row in read_csv(PARTICIPANTS):
        interview_id = row["interview_id"]
        if interview_id.startswith("Fictional/"):
            continue
        person = row["person"].strip()
        if person == "ALIUS Research Group":
            continue
        roles = by_interview.setdefault(interview_id, {"interviewer": [], "interviewee": []})
        roles.setdefault(row["role"], []).append(person)

    rows = []
    for interview_id in sorted(by_interview):
        qa_dir = QA_ROOT / interview_id
        if not qa_dir.exists():
            continue
        interview_slug = interview_id.replace("/", "_")
        out_path = render_dir / f"{interview_slug}.json"
        if out_path.exists() and not args.overwrite:
            plan = json.loads(out_path.read_text(encoding="utf-8"))
        else:
            interviewers = by_interview[interview_id].get("interviewer", [])
            interviewees = by_interview[interview_id].get("interviewee", [])
            question = slugify(interviewers[0]) if interviewers else ""
            answer = slugify(interviewees[0]) if interviewees else question
            plan = {
                "interview_id": interview_id,
                "interview_slug": interview_slug,
                "source_qa_dir": f"output/audio_interviews/{interview_id}",
                "output_file_stem": f"{interview_slug}_clone_full_interview",
                "voices": {
                    "question": question,
                    "answer": answer,
                },
                "all_participants": {
                    "interviewers": [{"name": name, "speaker_slug": slugify(name)} for name in interviewers],
                    "interviewees": [{"name": name, "speaker_slug": slugify(name)} for name in interviewees],
                },
                "tts": {
                    "model": "F5TTS_v1_Base",
                    "nfe_step": 16,
                    "speed": 1.0,
                    "remove_silence": False,
                },
                "render_status": "needs_voice_profiles",
                "notes": "Scaffolded from participant metadata. Multi-speaker interviews may need manual per-turn speaker attribution if answer text alternates between interviewees.",
            }
            out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

        rows.append(
            {
                "interview_id": interview_id,
                "plan": str(out_path.relative_to(REPO)),
                "qa_units": len(list(qa_dir.glob("qa_*.txt"))),
                "question_voice": plan["voices"].get("question", ""),
                "answer_voice": plan["voices"].get("answer", ""),
                "status": plan.get("render_status", ""),
            }
        )

    index_path = ROOT / "render_plan_index.csv"
    with index_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"render_plans {len(rows)}")
    print(index_path)


if __name__ == "__main__":
    main()
