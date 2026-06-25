#!/usr/bin/env python3
"""Build F5-TTS input text/config from an ALIUS render plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "AudioTranscription"
MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "â€™", "â€œ", "â€")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO / path


def repair_mojibake(text: str) -> str:
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text
    return repaired if len(repaired.strip()) >= len(text.strip()) * 0.8 else text


def clean_for_tts(text: str) -> str:
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "Ä": "A",
        "Ö": "O",
        "Ü": "U",
        "ß": "ss",
    }
    replacements.update(
        {
            "\u00ac": " not ",
            "\u2227": " and ",
            "\u2228": " or ",
            "\u2192": " implies ",
            "\u2194": " if and only if ",
            "\u2264": " less than or equal to ",
            "\u2265": " greater than or equal to ",
        "\u2260": " not equal to ",
        "\u2248": " approximately ",
        "\u00d7": " times ",
        "I \u00e3N": "IJN",
        "modi fied": "modified",
        "Modi fied": "Modified",
        "modi fication": "modification",
        "Collo quium": "Colloquium",
        "collo quium": "colloquium",
        "non-pro fit": "nonprofit",
        "pro fit": "profit",
        "bi fier": "bigger",
        "sta ff": "staff",
        "di fferent": "different",
        "di fficult": "difficult",
        "differen tiate": "differentiate",
        "en tirely": "entirely",
        "scienti fic": "scientific",
        "scienti fically": "scientifically",
        "sacri fice": "sacrifice",
        "re quires": "requires",
        "re quire": "require",
        "re flect": "reflect",
        "re flection": "reflection",
        "le ft": "left",
        "de finition": "definition",
        "de finitions": "definitions",
        "de finitive": "definitive",
        "de fined": "defined",
        "de finitely": "definitely",
        "de flationist": "deflationist",
        "con figuration": "configuration",
        "recon figurations": "reconfigurations",
        "identi fiable": "identifiable",
        "o ften": "often",
        "o ftentimes": "oftentimes",
        "inade quate": "inadequate",
        "con firmed": "confirmed",
        "incogni ta": "incognita",
        "e ffort": "effort",
        "e fforts": "efforts",
        "stru filing": "struggling",
        "la fied": "lagged",
        "accep ting": "accepting",
        "objec tive": "objective",
        "objec tives": "objectives",
        "subjec tive": "subjective",
        "subjec tivity": "subjectivity",
        "alterna tive": "alternative",
        "alterna tives": "alternatives",
        "a 'ained": "attained",
        "be 'er": "better",
        "s till": "still",
        "ambi tion": "ambition",
        "ambi tions": "ambitions",
        "ques tion": "question",
        "ques tions": "questions",
        "Mar tin": "Martin",
        "mul ti-dimensional": "multidimensional",
        "mul tidimensional": "multidimensional",
        "medita tion": "meditation",
        "plas ticity": "plasticity",
        "transforma tion": "transformation",
        "transforma tive": "transformative",
        "posi tion": "position",
        "psychoac tive": "psychoactive",
        "condi tion": "condition",
        "condi tions": "conditions",
        "connec tion": "connection",
        "connec tions": "connections",
        "depic tion": "depiction",
        "ra tionale": "rationale",
        "poli tical": "political",
        "cul tivated": "cultivated",
        "ma 'er": "matter",
        ", h. The rationale": ". The rationale",
        "scien tific": "scientific",
        "scien tists": "scientists",
        "appropria tion": "appropriation",
        "ar tistic": "artistic",
        "ritualis tic": "ritualistic",
        "no tion": "notion",
        "no tions": "notions",
        "experien tial": "experiential",
        }
    )
    text = repair_mojibake(text)
    replacements.update(
        {
            "\u00c3\u00a1": "a",
            "\u00c3\u00a0": "a",
            "\u00c3\u00a2": "a",
            "\u00c3\u00a9": "e",
            "\u00c3\u00a8": "e",
            "\u00c3\u00aa": "e",
            "\u00c3\u00ad": "i",
            "\u00c3\u00ac": "i",
            "\u00c3\u00ae": "i",
            "\u00c3\u00b3": "o",
            "\u00c3\u00b2": "o",
            "\u00c3\u00b4": "o",
            "\u00c3\u00ba": "u",
            "\u00c3\u00b9": "u",
            "\u00c3\u00bb": "u",
            "\u00c3\u00b1": "n",
            "\u00c3\u00a7": "c",
        }
    )
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\[[^\]]{0,200}\]", " ", text)
    text = re.sub(
        r"\([^)]*\b(?:inaudible|unclear|laughter|laughs?|pause|crosstalk|music|audio|noise|question directed)\b[^)]*\)",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bquestions?\s+directed\s+toward\s+[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){0,3}",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"(?<![A-Za-z])A\.\s*L\.\s*I\.\s*U\.\s*S\.(?![A-Za-z])", "alius", text)
    text = re.sub(r"(?<![A-Za-z])A[\s.\-]*L[\s.\-]*I[\s.\-]*U[\s.\-]*S(?![A-Za-z])", "alius", text)
    text = re.sub(r"\bJuan\b", "Hwan", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_person_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def collect_plan_speaker_slugs(plan: dict) -> list[str]:
    slugs: list[str] = []
    slugs.extend((plan.get("voices") or {}).values())
    participants = plan.get("all_participants") or {}
    for group in ("interviewers", "interviewees"):
        for person in participants.get(group, []) or []:
            slug = person.get("speaker_slug")
            if slug:
                slugs.append(slug)
    return list(dict.fromkeys(slugs))


def collect_plan_interviewer_slugs(plan: dict) -> list[str]:
    participants = plan.get("all_participants") or {}
    return [
        person["speaker_slug"]
        for person in participants.get("interviewers", []) or []
        if person.get("speaker_slug")
    ]


def speaker_name_to_slug(plan: dict, profiles: dict[str, dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    participants = plan.get("all_participants") or {}
    for group in ("interviewers", "interviewees"):
        for person in participants.get(group, []) or []:
            slug = person.get("speaker_slug")
            name = person.get("name")
            if slug and name:
                for alias in speaker_name_aliases(str(name)):
                    mapping[normalize_person_name(alias)] = slug
    for slug, profile in profiles.items():
        name = profile.get("speaker_name")
        if name:
            for alias in speaker_name_aliases(str(name)):
                mapping.setdefault(normalize_person_name(alias), slug)
    return mapping


def speaker_name_aliases(name: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z]+", name)
    aliases = [name]
    if len(tokens) >= 2:
        surname = tokens[-1]
        initials = [token[0] for token in tokens[:-1]]
        aliases.extend(
            [
                f"{''.join(initials)} {surname}",
                f"{'.'.join(initials)}. {surname}",
                f"{'. '.join(initials)}. {surname}",
            ]
        )
    return aliases


def declared_voice_slug(raw: str, label: str, fallback_slug: str, name_map: dict[str, str]) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", raw, re.M)
    if not match:
        return fallback_slug
    name = re.sub(r"\s*\([^)]*\)\s*$", "", match.group(1)).strip()
    return name_map.get(normalize_person_name(name), fallback_slug)


def question_voice_slug(
    raw: str,
    unit_index: int,
    plan: dict,
    name_map: dict[str, str],
    interviewer_slugs: list[str],
) -> str:
    if len(interviewer_slugs) > 1:
        return interviewer_slugs[(unit_index - 1) % len(interviewer_slugs)]
    return declared_voice_slug(raw, "Question voice", plan["voices"]["question"], name_map)


INLINE_SPEAKER_RE = re.compile(r"(?<!\w)([A-Z](?:\.[A-Z])+\.?\s+[A-Z][A-Za-z'-]+):\s*")


def split_inline_speaker_segments(text: str, fallback_slug: str, name_map: dict[str, str]) -> list[tuple[str, str]]:
    matches = list(INLINE_SPEAKER_RE.finditer(text))
    if not matches:
        return [(fallback_slug, text)]

    segments: list[tuple[str, str]] = []
    prefix = text[: matches[0].start()].strip()
    if prefix:
        segments.append((fallback_slug, prefix))
    for index, match in enumerate(matches):
        label = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if not body:
            continue
        slug = name_map.get(normalize_person_name(label), fallback_slug)
        segments.append((slug, body))
    return segments


def extract_section(text: str, heading: str, next_heading: str | None = None) -> str:
    start = text.index(heading) + len(heading)
    end = text.index(next_heading, start) if next_heading else len(text)
    return clean_for_tts(text[start:end])


def profile_path(slug: str) -> Path:
    return ROOT / "profiles" / f"{slug}.json"


def rel_or_abs(path_text: str) -> str:
    path = resolve_repo_path(path_text)
    return path.as_posix()


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--max-units", type=int, help="Limit the number of qa_*.txt units included.")
    parser.add_argument("--output-file-stem", help="Override the plan output_file_stem.")
    args = parser.parse_args()

    plan_path = resolve_repo_path(str(args.plan))
    plan = read_json(plan_path)
    interview_slug = plan["interview_slug"]
    output_file_stem = args.output_file_stem or plan["output_file_stem"]
    work_dir = args.work_dir or ROOT / "work" / interview_slug
    work_dir.mkdir(parents=True, exist_ok=True)

    profile_slugs = collect_plan_speaker_slugs(plan)
    profiles = {slug: read_json(profile_path(slug)) for slug in profile_slugs}
    name_map = speaker_name_to_slug(plan, profiles)
    interviewer_slugs = collect_plan_interviewer_slugs(plan)

    qa_dir = resolve_repo_path(plan["source_qa_dir"])
    pieces: list[str] = []
    units: list[dict] = []
    qa_paths = sorted(qa_dir.glob("qa_*.txt"))
    if args.max_units is not None:
        qa_paths = qa_paths[: max(0, args.max_units)]

    for path in qa_paths:
        raw = path.read_text(encoding="utf-8")
        source_index = int(path.stem.split("_")[1])
        unit_index = len(units) + 1
        question = extract_section(raw, "QUESTION SPOKEN TEXT:", "ANSWER SPOKEN TEXT:")
        answer = extract_section(raw, "ANSWER SPOKEN TEXT:")
        question_slug = question_voice_slug(raw, unit_index, plan, name_map, interviewer_slugs)
        answer_slug = declared_voice_slug(raw, "Answer voice", plan["voices"]["answer"], name_map)
        answer_segments = split_inline_speaker_segments(answer, answer_slug, name_map)
        for voice_slug in [question_slug, *[segment_slug for segment_slug, _ in answer_segments]]:
            if voice_slug not in profiles:
                profiles[voice_slug] = read_json(profile_path(voice_slug))
        pieces.append(f"[{question_slug}] {question}")
        for segment_slug, segment_text in answer_segments:
            pieces.append(f"[{segment_slug}] {segment_text}")
        units.append(
            {
                "index": unit_index,
                "source_index": source_index,
                "source": str(path),
                "question_voice": question_slug,
                "answer_voice": answer_slug,
                "answer_voice_segments": [segment_slug for segment_slug, _ in answer_segments],
                "question_chars": len(question),
                "answer_chars": len(answer),
            }
        )

    gen_file = work_dir / "f5_gen_text.txt"
    gen_file.write_text("\n\n".join(pieces) + "\n", encoding="utf-8")

    tts = plan.get("tts", {})
    main_slug = plan["voices"]["answer"]
    main_profile = profiles[main_slug]
    lines = [
        f"model = {toml_string(tts.get('model', 'F5TTS_v1_Base'))}",
        f"ref_audio = {toml_string(rel_or_abs(main_profile['reference_audio']))}",
        f"ref_text = {toml_string(main_profile['reference_text'])}",
        'gen_text = ""',
        f"gen_file = {toml_string(gen_file.as_posix())}",
        f'remove_silence = {str(bool(tts.get("remove_silence", False))).lower()}',
        f"output_dir = {toml_string(work_dir.as_posix())}",
        f"output_file = {toml_string(output_file_stem + '.wav')}",
        f'nfe_step = {int(tts.get("nfe_step", 16))}',
        f'speed = {float(tts.get("speed", 1.0))}',
        "",
    ]
    voice_speeds = tts.get("voice_speeds", {})
    for voice_slug, profile in profiles.items():
        voice_speed = voice_speeds.get(voice_slug, tts.get("speed", 1.0))
        lines.extend(
            [
                f"[voices.{voice_slug}]",
                f"ref_audio = {toml_string(rel_or_abs(profile['reference_audio']))}",
                f"ref_text = {toml_string(profile['reference_text'])}",
                f"speed = {float(voice_speed)}",
                "",
            ]
        )

    config_path = work_dir / "f5_config.toml"
    config_path.write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "plan": str(plan_path),
        "interview_id": plan["interview_id"],
        "interview_slug": interview_slug,
        "work_dir": str(work_dir),
        "config": str(config_path),
        "gen_file": str(gen_file),
        "output_file_stem": output_file_stem,
        "units": units,
        "profiles": list(profiles.keys()),
        "question_voice_policy": "round_robin_interviewers_by_unit"
        if len(interviewer_slugs) > 1
        else "qa_header_or_plan_default",
        "text_protocol": "QUESTION/ANSWER SPOKEN TEXT from output/audio_interviews qa_*.txt; speaker labels route voices and are not spoken; bracketed/stage cues are omitted.",
        "pronunciation_protocol": "Uppercase ALIUS / A.L.I.U.S. is normalized to lowercase alius for spoken rendering; common formal symbols are converted to spoken forms; selected proper names may be phonetically normalized for speech.",
    }
    (work_dir / "input_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(config_path)


if __name__ == "__main__":
    main()
