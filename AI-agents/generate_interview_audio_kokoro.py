#!/usr/bin/env python3
"""Extract ALIUS interview Q/A units and optionally render them with Kokoro."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave
from typing import Iterable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "output" / "audio_interviews"
DEFAULT_SPEAKERS = REPO / "AI-agents" / "interview_audio_speaker_demographics.csv"
DEFAULT_PARTICIPANTS = REPO / "AI-agents" / "interview_audio_participants.csv"

SAMPLE_RATE = 24000
QUESTION_COLORS = {"ALIUSC1F8135", "ALIUSC1155CC", "ALIUSC1A73E8"}
ANSWER_COLORS = {"ALIUSC000000", "ALIUSC1A1718", "ALIUSC222222"}
STOP_HEADINGS = {"references", "references:", "bibliography", "acknowledgments", "acknowledgements"}

PLACED_RE = re.compile(
    r"\\ALIUSPlacedTextContent"
    r"\{(?P<x>-?\d+(?:\.\d+)?)\}"
    r"\{(?P<y>-?\d+(?:\.\d+)?)\}"
    r"\{(?P<w>-?\d+(?:\.\d+)?)\}"
    r"\{(?P<color>[^}]*)\}"
    r"\{(?P<font>[^}]*)\}"
    r"\{(?P<size>-?\d+(?:\.\d+)?)\}"
    r"\{(?P<text>.*)\}\s*;?\s*$"
)


@dataclass(frozen=True)
class Span:
    page: int
    x: float
    y: float
    color: str
    font: str
    size: float
    text: str
    role: str


@dataclass(frozen=True)
class Line:
    page: int
    y: float
    role: str
    text: str


@dataclass(frozen=True)
class QaUnit:
    interview_id: str
    source_path: str
    index: int
    question: str
    answer: str
    question_speaker: dict[str, str]
    answer_speaker: dict[str, str]
    transcript_path: str
    audio_path: str


def clean_mojibake(text: str) -> str:
    replacements = {
        "â€œ": '"',
        "â€�": '"',
        "â€˜": "'",
        "â€™": "'",
        "â€“": "-",
        "â€”": "-",
        "â€¦": "...",
        "Â°": " degrees ",
        "Â": "",
        "Ã©": "e",
        "Ã¨": "e",
        "Ãª": "e",
        "Ã¶": "o",
        "Ã¼": "u",
        "Ã": "a",
        "Ma 'hieu": "Matthieu",
        "Ma'hieu": "Matthieu",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def strip_one_arg_command(text: str, command: str) -> str:
    pattern = "\\" + command + "{"
    while pattern in text:
        start = text.find(pattern)
        arg_start = start + len(pattern)
        depth = 1
        i = arg_start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth:
            break
        text = text[:start] + text[arg_start : i - 1] + text[i:]
    return text


def replace_two_arg_command(text: str, command: str, keep: int) -> str:
    pattern = "\\" + command + "{"
    while pattern in text:
        start = text.find(pattern)
        pos = start + len(pattern)
        args: list[str] = []
        ok = True
        for _ in range(2):
            depth = 1
            arg_start = pos
            i = arg_start
            while i < len(text) and depth:
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                i += 1
            if depth:
                ok = False
                break
            args.append(text[arg_start : i - 1])
            pos = i
            if len(args) < 2:
                if pos >= len(text) or text[pos] != "{":
                    ok = False
                    break
                pos += 1
        if not ok:
            break
        text = text[:start] + args[keep] + text[pos:]
    return text


def tex_to_text(text: str) -> str:
    text = replace_two_arg_command(text, "ALIUSCitationLink", 1)
    text = replace_two_arg_command(text, "href", 1)
    text = replace_two_arg_command(text, "textcolor", 1)
    for command in ("mbox", "textit", "emph", "textbf"):
        text = strip_one_arg_command(text, command)
    replacements = {
        r"\&": "&",
        r"\%": "%",
        r"\#": "#",
        r"\_": "_",
        r"\$": "$",
        r"\{": "{",
        r"\}": "}",
        r"\textquotedblleft": '"',
        r"\textquotedblright": '"',
        r"\ALIUSPullQuoteOpen": '"',
        r"\ALIUSPullQuoteClose": '"',
        r"\par": " ",
        r"\textbackslash{}": "\\",
        r"\textasciitilde{}": "~",
        r"\textasciicircum{}": "^",
        "~": " ",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", "").replace("}", "")
    text = clean_mojibake(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def audio_friendly_text(text: str) -> str:
    """Remove visual/citation scaffolding that should not be spoken."""

    text = clean_mojibake(text)
    text = text.replace("—", ", ").replace("–", ", ").replace("…", ", ")
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", " ", text)
    text = re.sub(r"\b(?:h?ttps?://|www\.)\S+", " ", text)
    text = re.sub(r"\b(?:see\s+)?(?:fig\.?|figure|table)\s*\d+[A-Za-z]?\b", " ", text, flags=re.I)
    text = text.replace("&", " and ")
    text = text.replace("e.g.,", "for example,").replace("e.g.", "for example")
    text = text.replace("i.e.,", "that is,").replace("i.e.", "that is")

    citationish = re.compile(
        r"\d{4}|doi|https?|www\.|fig(?:ure)?|table|et al\.|"
        r"^\s*(?:for example|that is|cf\.|see|reviewed in|for a review)|"
        r"[A-Z][A-Za-z'’-]+,\s*(?:[A-Z]\.\s*)?(?:and\s+)?",
        re.I,
    )

    def parenthetical(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if not inner:
            return " "
        if citationish.search(inner):
            return " "
        return f", {inner}, "

    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\(([^()]*)\)", parenthetical, text)
    text = re.sub(r"\[[^\]]*(?:\d{4}|doi|https?|www\.|fig(?:ure)?|table|et al\.)[^\]]*\]", " ", text, flags=re.I)

    def square_bracket(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if not inner or inner in {"...", ",", ".", ";", ":"}:
            return " "
        if citationish.search(inner):
            return " "
        return inner

    text = re.sub(r"\[([^\[\]]*)\]", square_bracket, text)
    text = re.sub(
        r"\b[A-Z][A-Za-z'’-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'’-]+)?(?:\s+et al\.)?,?\s+\d{4}[a-z]?\b",
        " ",
        text,
    )
    text = re.sub(r"\b[A-Z][A-Za-z'’-]+\s+et al\.\b", " ", text)
    text = text.replace("(", " ").replace(")", " ")
    text = text.replace("[", " ").replace("]", " ").replace("{", " ").replace("}", " ")
    text = re.sub(r"\s+-\s+", ", ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:])(?:\s*\1)+", r"\1", text)
    text = re.sub(r",\s*([.;:!?])", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:")
    return text


def classify_span(color: str, font: str, size: float, text: str, x: float, y: float) -> str | None:
    low = text.strip().lower().strip(" :")
    if not text or y >= 785 or low in {"alius bulletin", "aliusresearch.org/bulletin"}:
        return None
    if low in STOP_HEADINGS:
        return "stop"
    if color in QUESTION_COLORS and "Lato" in font and size >= 11.0 and x < 540:
        if low.startswith("the video and audio version"):
            return None
        if low.startswith("ttps://") or low.startswith("https://"):
            return None
        return "question"
    if color in ANSWER_COLORS and "Cormorant" in font and size >= 12.4 and x < 540:
        return "answer"
    return None


def append_piece(parts: list[str], piece: str) -> None:
    if not piece:
        return
    if parts:
        prev = parts[-1]
        if (
            prev
            and piece
            and not prev[-1].isspace()
            and not piece[0].isspace()
            and piece[0] not in ".,;:!?)]}%"
            and prev[-1] not in "([{/`"
        ):
            parts.append(" ")
    parts.append(piece)


def combine_spans(spans: Iterable[Span]) -> str:
    parts: list[str] = []
    for span in sorted(spans, key=lambda s: s.x):
        append_piece(parts, span.text)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def join_lines(lines: list[str]) -> str:
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-") and line[:1].islower():
            out = out[:-1] + " " + line
        else:
            out += " " + line
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip()


def parse_visual_tex(path: Path) -> list[Line]:
    page = 0
    spans: list[Span] = []
    stopped = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        page_match = re.match(r"% Page (\d+)", raw)
        if page_match:
            page = int(page_match.group(1))
        match = PLACED_RE.search(raw.strip())
        if not match or stopped:
            continue
        text = tex_to_text(match.group("text"))
        role = classify_span(
            match.group("color"),
            match.group("font"),
            float(match.group("size")),
            text,
            float(match.group("x")),
            float(match.group("y")),
        )
        if role == "stop":
            stopped = True
            continue
        if role:
            spans.append(
                Span(
                    page=page,
                    x=float(match.group("x")),
                    y=float(match.group("y")),
                    color=match.group("color"),
                    font=match.group("font"),
                    size=float(match.group("size")),
                    text=text,
                    role=role,
                )
            )

    lines: list[Line] = []
    current: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.page, s.y, s.x)):
        if current and (
            span.page != current[-1].page
            or span.role != current[-1].role
            or abs(span.y - current[-1].y) > 1.2
        ):
            text = combine_spans(current)
            if text:
                lines.append(Line(current[-1].page, current[-1].y, current[-1].role, text))
            current = []
        current.append(span)
    if current:
        text = combine_spans(current)
        if text:
            lines.append(Line(current[-1].page, current[-1].y, current[-1].role, text))
    return lines


def parse_environment_tex(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    units: list[tuple[str, str]] = []
    pattern = re.compile(
        r"\\begin\{question\}(?P<q>.*?)\\end\{question\}\s*\\begin\{answer\}(?P<a>.*?)\\end\{answer\}",
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        q = tex_to_text(match.group("q"))
        a = tex_to_text(match.group("a"))
        if q and a:
            units.append((q, a))
    return units


def blocks_from_lines(lines: list[Line]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    role: str | None = None
    bucket: list[str] = []
    seen_question = False
    for line in lines:
        if line.role == "answer" and not seen_question:
            continue
        if line.role == "question":
            seen_question = True
        if role is not None and line.role != role:
            blocks.append((role, join_lines(bucket)))
            bucket = []
        role = line.role
        bucket.append(line.text)
    if role is not None and bucket:
        blocks.append((role, join_lines(bucket)))
    return [(r, t) for r, t in blocks if t]


def qa_from_blocks(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    units: list[tuple[str, str]] = []
    i = 0
    while i < len(blocks):
        role, text = blocks[i]
        if role != "question":
            i += 1
            continue
        if "?" not in text:
            i += 1
            continue
        answers: list[str] = []
        j = i + 1
        while j < len(blocks) and blocks[j][0] == "answer":
            answers.append(blocks[j][1])
            j += 1
        answer = join_lines(answers)
        if len(text) >= 20 and len(answer) >= 20:
            units.append((text, answer))
        i = max(j, i + 1)
    return units


def interview_id_for(path: Path) -> str:
    return path.parent.relative_to(REPO / "Interviews").as_posix()


def load_speakers(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {row["person"]: row for row in rows}


def load_participants(path: Path, speakers: dict[str, dict[str, str]]) -> dict[str, dict[str, list[dict[str, str]]]]:
    grouped: dict[str, dict[str, list[dict[str, str]]]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            person = row["person"]
            speaker = speakers.get(person)
            if speaker is None:
                raise KeyError(f"Missing speaker demographic row for {person}")
            interview = grouped.setdefault(row["interview_id"], {"interviewer": [], "interviewee": []})
            interview[row["role"]].append(speaker)
    return grouped


def speaker_for(participants: list[dict[str, str]], index: int) -> dict[str, str]:
    if not participants:
        return {
            "person": "ALIUS Research Group",
            "voice_gender": "unknown",
            "accent_region": "american",
            "voice": "af_heart",
            "age_group": "adult",
        }
    return participants[(index - 1) % len(participants)]


def extract_units(
    interviews_dir: Path,
    out_dir: Path,
    participants: dict[str, dict[str, list[dict[str, str]]]],
) -> list[QaUnit]:
    all_units: list[QaUnit] = []
    for path in sorted(interviews_dir.rglob("*.tex")):
        iid = interview_id_for(path)
        env_units = parse_environment_tex(path)
        raw_units = env_units or qa_from_blocks(blocks_from_lines(parse_visual_tex(path)))
        if not raw_units:
            continue
        pmap = participants.get(iid, {"interviewer": [], "interviewee": []})
        interview_out = out_dir / iid
        interview_out.mkdir(parents=True, exist_ok=True)
        for idx, (question, answer) in enumerate(raw_units, start=1):
            question = audio_friendly_text(question)
            answer = audio_friendly_text(answer)
            if not question or not answer:
                continue
            q_speaker = speaker_for(pmap.get("interviewer", []), idx)
            a_speaker = speaker_for(pmap.get("interviewee", []), idx)
            base = f"qa_{idx:03d}"
            transcript_path = interview_out / f"{base}.txt"
            audio_path = interview_out / f"{base}.wav"
            transcript = (
                f"Interview: {iid}\n"
                f"Unit: {idx:03d}\n"
                f"Question voice: {q_speaker['person']} ({q_speaker['voice']})\n"
                f"Answer voice: {a_speaker['person']} ({a_speaker['voice']})\n\n"
                f"QUESTION SPOKEN TEXT:\n{question}\n\nANSWER SPOKEN TEXT:\n{answer}\n"
            )
            transcript_path.write_text(transcript, encoding="utf-8")
            all_units.append(
                QaUnit(
                    interview_id=iid,
                    source_path=str(path.relative_to(REPO)),
                    index=idx,
                    question=question,
                    answer=answer,
                    question_speaker=q_speaker,
                    answer_speaker=a_speaker,
                    transcript_path=str(transcript_path.relative_to(REPO)),
                    audio_path=str(audio_path.relative_to(REPO)),
                )
            )
    return all_units


def write_manifest(units: list[QaUnit], out_dir: Path) -> None:
    csv_path = out_dir / "qa_manifest.csv"
    json_path = out_dir / "qa_manifest.json"
    fields = [
        "interview_id",
        "unit",
        "source_path",
        "question_speaker",
        "question_voice",
        "answer_speaker",
        "answer_voice",
        "question_chars",
        "answer_chars",
        "transcript_path",
        "audio_path",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for unit in units:
            writer.writerow(
                {
                    "interview_id": unit.interview_id,
                    "unit": unit.index,
                    "source_path": unit.source_path,
                    "question_speaker": unit.question_speaker["person"],
                    "question_voice": unit.question_speaker["voice"],
                    "answer_speaker": unit.answer_speaker["person"],
                    "answer_voice": unit.answer_speaker["voice"],
                    "question_chars": len(unit.question),
                    "answer_chars": len(unit.answer),
                    "transcript_path": unit.transcript_path,
                    "audio_path": unit.audio_path,
                }
            )
    json_path.write_text(
        json.dumps([unit_to_json(u) for u in units], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def unit_to_json(unit: QaUnit) -> dict[str, object]:
    return {
        "interview_id": unit.interview_id,
        "unit": unit.index,
        "source_path": unit.source_path,
        "question_speaker": unit.question_speaker,
        "answer_speaker": unit.answer_speaker,
        "question_chars": len(unit.question),
        "answer_chars": len(unit.answer),
        "transcript_path": unit.transcript_path,
        "audio_path": unit.audio_path,
    }


def chunk_text(text: str, max_chars: int = 950) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return [text] if text else []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i : i + max_chars].strip())
            continue
        if buf and len(buf) + 1 + len(sentence) > max_chars:
            chunks.append(buf.strip())
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
    if buf:
        chunks.append(buf.strip())
    return chunks


def voice_lang(voice: str) -> str:
    return "b" if voice.startswith(("bf_", "bm_")) else "a"


def render_units(
    units: list[QaUnit],
    overwrite: bool,
    limit_units: int | None = None,
    start_unit: int = 1,
    end_unit: int | None = None,
    torch_threads: int | None = None,
    unit_list: set[int] | None = None,
) -> None:
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from kokoro import KPipeline
    except Exception as exc:
        raise RuntimeError("Rendering requires kokoro, soundfile, numpy, and torch in this Python env") from exc

    if torch_threads:
        torch.set_num_threads(torch_threads)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipelines: dict[str, KPipeline] = {}

    def pipeline_for(lang: str) -> KPipeline:
        if lang not in pipelines:
            print(f"Initializing Kokoro pipeline lang={lang} device={device}", flush=True)
            pipelines[lang] = KPipeline(lang_code=lang, device=device, repo_id="hexgrad/Kokoro-82M")
        return pipelines[lang]

    def synth(text: str, voice: str, speed: float) -> np.ndarray:
        chunks: list[np.ndarray] = []
        pipe = pipeline_for(voice_lang(voice))
        for piece in chunk_text(text):
            for _, _, audio in pipe(piece, voice=voice, speed=speed, split_pattern=r"\n+"):
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    silence = np.zeros(math.floor(SAMPLE_RATE * 0.65), dtype=np.float32)
    selected = [
        (global_index, unit)
        for global_index, unit in enumerate(units, start=1)
        if global_index >= start_unit
        and (end_unit is None or global_index <= end_unit)
        and (unit_list is None or global_index in unit_list)
    ]
    if limit_units:
        selected = selected[:limit_units]
    total = len(selected)
    for n, (global_index, unit) in enumerate(selected, start=1):
        out_path = REPO / unit.audio_path
        if out_path.exists() and not overwrite:
            print(f"[{n}/{total}] skip existing {unit.audio_path}", flush=True)
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        q_voice = unit.question_speaker["voice"]
        a_voice = unit.answer_speaker["voice"]
        print(
            f"[{n}/{total}] render unit {global_index:03d} {unit.interview_id} qa_{unit.index:03d} "
            f"{q_voice}->{a_voice}",
            flush=True,
        )
        q_audio = synth(unit.question, q_voice, speed=0.98)
        a_speed = 0.92 if unit.answer_speaker.get("age_group") == "older" else 0.95
        a_audio = synth(unit.answer, a_voice, speed=a_speed)
        combined = np.concatenate([q_audio, silence, a_audio])
        peak = float(np.max(np.abs(combined))) if combined.size else 0.0
        if peak > 0.99:
            combined = combined / peak * 0.97
        sf.write(out_path, combined, SAMPLE_RATE)


def copy_lookup_files(out_dir: Path, speaker_csv: Path, participant_csv: Path) -> None:
    shutil.copy2(speaker_csv, out_dir / "demographic_lookup.csv")
    shutil.copy2(participant_csv, out_dir / "interview_participants.csv")


def wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as f:
        return round(f.getnframes() / f.getframerate() * 1000)


def ffmetadata_escape(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return (
        text.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
        .replace("\n", " ")
    )


def concat_escape(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


def chapter_title(unit: QaUnit) -> str:
    question = (
        unit.question.replace("“", '"')
        .replace("”", '"')
        .replace("‘", "'")
        .replace("’", "'")
        .replace("—", ", ")
        .replace("–", ", ")
    )
    question = question.encode("ascii", "ignore").decode("ascii")
    if len(question) > 86:
        question = question[:83].rsplit(" ", 1)[0] + "..."
    return f"Q&A {unit.index:03d}: {question}"


def write_silence_wav(path: Path, gap_ms: int) -> None:
    frames = round(SAMPLE_RATE * gap_ms / 1000)
    if path.exists():
        try:
            if wav_duration_ms(path) == gap_ms:
                return
        except Exception:
            pass
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(b"\x00\x00" * frames)


def write_chapter_sidecars(
    interview_id: str,
    units: list[QaUnit],
    out_dir: Path,
    chapter_gap_ms: int,
) -> tuple[Path, Path, Path]:
    interview_dir = out_dir / interview_id
    concat_path = interview_dir / "interview_concat.txt"
    metadata_path = interview_dir / "interview_chapters.ffmetadata"
    chapters_csv = interview_dir / "interview_chapters.csv"

    silence_path = out_dir / f"_silence_{chapter_gap_ms}ms.wav"
    if chapter_gap_ms > 0:
        write_silence_wav(silence_path, chapter_gap_ms)
    concat_lines: list[str] = []
    for idx, unit in enumerate(units, start=1):
        concat_lines.append(f"file '{concat_escape(REPO / unit.audio_path)}'")
        if chapter_gap_ms > 0 and idx < len(units):
            concat_lines.append(f"file '{concat_escape(silence_path)}'")
    concat_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    rows: list[dict[str, object]] = []
    metadata = [";FFMETADATA1", f"title={ffmetadata_escape(interview_id.replace('/', ' - '))}"]
    start = 0
    for unit in units:
        wav_path = REPO / unit.audio_path
        duration = wav_duration_ms(wav_path)
        end = start + duration
        title = chapter_title(unit)
        metadata.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start}",
                f"END={end}",
                f"title={ffmetadata_escape(title)}",
            ]
        )
        rows.append(
            {
                "chapter": unit.index,
                "start_ms": start,
                "end_ms": end,
                "duration_ms": duration,
                "post_chapter_gap_ms": chapter_gap_ms if unit != units[-1] else 0,
                "title": title,
                "audio_path": unit.audio_path,
            }
        )
        start = end + (chapter_gap_ms if unit != units[-1] else 0)
    metadata_path.write_text("\n".join(metadata) + "\n", encoding="utf-8")

    with chapters_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "chapter",
                "start_ms",
                "end_ms",
                "duration_ms",
                "post_chapter_gap_ms",
                "title",
                "audio_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return concat_path, metadata_path, chapters_csv


def build_interview_mp3s(
    units: list[QaUnit],
    out_dir: Path,
    overwrite: bool,
    partial: bool,
    bitrate: str,
    chapter_gap_ms: int,
) -> None:
    by_interview: dict[str, list[QaUnit]] = {}
    for unit in units:
        by_interview.setdefault(unit.interview_id, []).append(unit)

    download_rows: list[dict[str, object]] = []
    for interview_id, interview_units in sorted(by_interview.items()):
        interview_units = sorted(interview_units, key=lambda u: u.index)
        present = [u for u in interview_units if (REPO / u.audio_path).exists()]
        if not present:
            continue
        if len(present) != len(interview_units) and not partial:
            print(f"skip incomplete {interview_id}: {len(present)}/{len(interview_units)} WAVs", flush=True)
            continue
        build_units = present if partial else interview_units
        interview_dir = out_dir / interview_id
        mp3_path = interview_dir / "interview.mp3"
        if mp3_path.exists() and not overwrite:
            print(f"skip existing {mp3_path.relative_to(REPO)}", flush=True)
        else:
            concat_path, metadata_path, chapters_csv = write_chapter_sidecars(
                interview_id,
                build_units,
                out_dir,
                chapter_gap_ms,
            )
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-i",
                str(metadata_path),
                "-map_metadata",
                "1",
                "-map_chapters",
                "1",
                "-vn",
                "-c:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-id3v2_version",
                "3",
                str(mp3_path),
            ]
            print(f"build {mp3_path.relative_to(REPO)} ({len(build_units)} chapters)", flush=True)
            subprocess.run(cmd, check=True)
            print(f"wrote {mp3_path.relative_to(REPO)}", flush=True)
        download_rows.append(
            {
                "interview_id": interview_id,
                "complete": len(present) == len(interview_units),
                "chapters": len(build_units),
                "expected_chapters": len(interview_units),
                "mp3_path": str(mp3_path.relative_to(REPO)),
                "chapters_csv": str((interview_dir / "interview_chapters.csv").relative_to(REPO)),
                "chapters_ffmetadata": str((interview_dir / "interview_chapters.ffmetadata").relative_to(REPO)),
            }
        )

    with (out_dir / "download_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "interview_id",
            "complete",
            "chapters",
            "expected_chapters",
            "mp3_path",
            "chapters_csv",
            "chapters_ffmetadata",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(download_rows)


def rel_url(path: Path, base_dir: Path) -> str:
    try:
        rel = path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        rel = path.resolve()
    return rel.as_posix()


def short_text(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0] + "..."


def read_download_rows(out_dir: Path) -> list[dict[str, object]]:
    manifest = out_dir / "download_manifest.csv"
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                mp3_rel = row.get("mp3_path", "")
                if not mp3_rel:
                    continue
                mp3_path = REPO / mp3_rel
                if not mp3_path.exists():
                    continue
                interview_id = row.get("interview_id", mp3_path.parent.relative_to(out_dir).as_posix())
                seen.add(interview_id)
                rows.append(
                    {
                        "interview_id": interview_id,
                        "complete": str(row.get("complete", "")).lower() == "true",
                        "chapters": row.get("chapters", ""),
                        "expected_chapters": row.get("expected_chapters", ""),
                        "mp3_path": mp3_path,
                    }
                )
    for mp3_path in sorted(out_dir.rglob("interview.mp3")):
        interview_id = mp3_path.parent.relative_to(out_dir).as_posix()
        if interview_id in seen:
            continue
        rows.append(
            {
                "interview_id": interview_id,
                "complete": True,
                "chapters": "",
                "expected_chapters": "",
                "mp3_path": mp3_path,
            }
        )
    return sorted(rows, key=lambda r: str(r["interview_id"]))


def write_audio_index(units: list[QaUnit], out_dir: Path) -> None:
    by_interview: dict[str, list[QaUnit]] = {}
    for unit in units:
        if (REPO / unit.audio_path).exists():
            by_interview.setdefault(unit.interview_id, []).append(unit)
    for interview_units in by_interview.values():
        interview_units.sort(key=lambda u: u.index)

    whole_rows = read_download_rows(out_dir)
    total_units = sum(len(items) for items in by_interview.values())
    index_path = out_dir / "index.html"

    whole_items: list[str] = []
    for row in whole_rows:
        interview_id = str(row["interview_id"])
        href = html.escape(rel_url(row["mp3_path"], out_dir), quote=True)
        title = html.escape(interview_id.replace("/", " / "))
        chapter_count = row.get("chapters") or row.get("expected_chapters") or ""
        chapter_label = f"{chapter_count} chapters" if chapter_count else "chapters"
        status = "complete" if row.get("complete") else "partial"
        whole_items.append(
            f"""
            <article class="item">
              <div class="item-head">
                <h3>{title}</h3>
                <span class="meta">{html.escape(chapter_label)} · {status}</span>
              </div>
              <audio controls preload="none" src="{href}" aria-label="{title} full interview"></audio>
              <a class="download" href="{href}" download>Download MP3</a>
            </article>
            """
        )

    unit_sections: list[str] = []
    for interview_id, interview_units in sorted(by_interview.items()):
        title = html.escape(interview_id.replace("/", " / "))
        rows: list[str] = []
        for unit in interview_units:
            audio_href = html.escape(rel_url(REPO / unit.audio_path, out_dir), quote=True)
            transcript_href = html.escape(rel_url(REPO / unit.transcript_path, out_dir), quote=True)
            q_speaker = html.escape(unit.question_speaker["person"])
            a_speaker = html.escape(unit.answer_speaker["person"])
            q_voice = html.escape(unit.question_speaker["voice"])
            a_voice = html.escape(unit.answer_speaker["voice"])
            question = html.escape(short_text(unit.question))
            rows.append(
                f"""
                <article class="item unit">
                  <div class="item-head">
                    <h3>Q&amp;A {unit.index:03d}</h3>
                    <span class="meta">{q_speaker} ({q_voice}) · {a_speaker} ({a_voice})</span>
                  </div>
                  <p>{question}</p>
                  <audio controls preload="none" src="{audio_href}" aria-label="{title} Q and A {unit.index:03d}"></audio>
                  <a class="download" href="{audio_href}" download>Download WAV</a>
                  <a class="download secondary" href="{transcript_href}">Transcript</a>
                </article>
                """
            )
        unit_sections.append(
            f"""
            <details>
              <summary>
                <span>{title}</span>
                <span>{len(interview_units)} Q&amp;A files</span>
              </summary>
              <div class="items">
                {''.join(rows)}
              </div>
            </details>
            """
        )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ALIUS Interview Audio</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17201d;
      --muted: #5e6864;
      --line: #d8dfdc;
      --paper: #f7f8f6;
      --panel: #ffffff;
      --accent: #126c67;
      --accent-2: #8a4f18;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    header, main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    header {{
      padding: 36px 0 22px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 34px;
      line-height: 1.1;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 32px 0 14px;
      font-size: 21px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0;
      font-size: 15px;
      letter-spacing: 0;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
    }}
    .stats span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 10px;
      background: var(--panel);
    }}
    .items {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
    }}
    .item {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .item-head {{
      display: grid;
      gap: 4px;
      margin-bottom: 10px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 12px;
    }}
    .unit p {{
      min-height: 48px;
      margin: 0 0 12px;
      color: #2d3835;
      font-size: 14px;
    }}
    audio {{
      display: block;
      width: 100%;
      height: 36px;
      margin: 8px 0 10px;
    }}
    .download {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      margin-right: 8px;
      color: var(--accent);
      font-weight: 650;
      font-size: 13px;
      text-decoration: none;
    }}
    .download.secondary {{
      color: var(--accent-2);
    }}
    details {{
      border-top: 1px solid var(--line);
      padding: 8px 0;
    }}
    summary {{
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 0;
      color: var(--ink);
      font-weight: 700;
    }}
    summary span:last-child {{
      color: var(--muted);
      font-weight: 500;
      white-space: nowrap;
    }}
    @media (max-width: 640px) {{
      header, main {{
        width: min(100% - 20px, 1180px);
      }}
      h1 {{
        font-size: 27px;
      }}
      .items {{
        grid-template-columns: 1fr;
      }}
      summary {{
        align-items: flex-start;
        flex-direction: column;
        gap: 2px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>ALIUS Interview Audio</h1>
    <div class="stats">
      <span>{len(by_interview)} interviews</span>
      <span>{total_units} Q&amp;A files</span>
      <span>{len(whole_rows)} chaptered MP3s</span>
    </div>
  </header>
  <main>
    <section>
      <h2>Whole Interviews</h2>
      <div class="items">
        {''.join(whole_items) if whole_items else '<p>No chaptered MP3s have been built yet.</p>'}
      </div>
    </section>
    <section>
      <h2>Question And Answer Files</h2>
      {''.join(unit_sections) if unit_sections else '<p>No Q&amp;A audio files have been rendered yet.</p>'}
    </section>
  </main>
  <script>
    (() => {{
      document.addEventListener("play", (event) => {{
        const active = event.target;
        if (!(active instanceof HTMLAudioElement)) {{
          return;
        }}
        document.querySelectorAll("audio").forEach((audio) => {{
          if (audio === active) {{
            return;
          }}
          audio.pause();
          try {{
            audio.currentTime = 0;
          }} catch (error) {{
            // Some browsers can reject resetting unloaded media.
          }}
        }});
      }}, true);
    }})();
  </script>
</body>
</html>
"""
    index_path.write_text(html_text, encoding="utf-8")
    print(f"wrote {index_path.relative_to(REPO)}")


def parse_unit_list(value: str | None) -> set[int] | None:
    if not value:
        return None
    units: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            units.update(range(start, end + 1))
        else:
            units.add(int(part))
    return units


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interviews-dir", type=Path, default=REPO / "Interviews")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--speaker-csv", type=Path, default=DEFAULT_SPEAKERS)
    parser.add_argument("--participant-csv", type=Path, default=DEFAULT_PARTICIPANTS)
    parser.add_argument("--render", action="store_true", help="Render WAV files with Kokoro")
    parser.add_argument("--build-mp3", action="store_true", help="Build one chaptered MP3 per complete interview")
    parser.add_argument("--build-index", action="store_true", help="Build a static audio website index")
    parser.add_argument("--partial-mp3", action="store_true", help="Allow MP3s for interviews whose WAVs are not complete")
    parser.add_argument("--mp3-bitrate", default="128k")
    parser.add_argument("--chapter-gap-ms", type=int, default=900)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit-units", type=int, default=None, help="Render only the first N units")
    parser.add_argument("--start-unit", type=int, default=1, help="1-based global unit index to start rendering")
    parser.add_argument("--end-unit", type=int, default=None, help="1-based global unit index to stop rendering")
    parser.add_argument("--unit-list", default=None, help="Comma-separated 1-based global unit IDs or ranges to render")
    parser.add_argument("--torch-threads", type=int, default=None, help="Limit PyTorch CPU threads per render process")
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    speakers = load_speakers(args.speaker_csv)
    participants = load_participants(args.participant_csv, speakers)
    copy_lookup_files(args.out_dir, args.speaker_csv, args.participant_csv)

    units = extract_units(args.interviews_dir, args.out_dir, participants)
    write_manifest(units, args.out_dir)
    interviews = sorted({u.interview_id for u in units})
    print(f"Extracted {len(units)} Q/A units from {len(interviews)} interview files.")
    print(f"Manifest: {(args.out_dir / 'qa_manifest.csv').relative_to(REPO)}")
    if args.render:
        render_units(
            units,
            overwrite=args.overwrite,
            limit_units=args.limit_units,
            start_unit=args.start_unit,
            end_unit=args.end_unit,
            torch_threads=args.torch_threads,
            unit_list=parse_unit_list(args.unit_list),
        )
    if args.build_mp3:
        build_interview_mp3s(
            units,
            out_dir=args.out_dir,
            overwrite=args.overwrite,
            partial=args.partial_mp3,
            bitrate=args.mp3_bitrate,
            chapter_gap_ms=args.chapter_gap_ms,
        )
    if args.build_index or args.build_mp3:
        write_audio_index(units, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
