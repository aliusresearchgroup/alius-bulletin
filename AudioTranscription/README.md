# ALIUS AudioTranscription

This folder standardizes a repeatable pipeline for turning ALIUS interview text
into speaker-matched audio where consent and suitable source audio are available.

## Current Status

- First reviewed working profile pair: `Issue07/Froese_Koroma`
- Additional speaker profiles are staged as `candidate_ready` when a public or
  local natural-voice reference candidate exists and still needs listening
  review.
- `blocked_youtube_source` means an exact public YouTube source has been found
  but yt-dlp currently needs exported YouTube cookies before it can download
  the original audio.
- Voice sources: reviewed local/original audio where available, otherwise
  public lecture/interview audio downloaded as native YouTube audio.
- TTS engine: F5-TTS zero-shot voice cloning
- Rendered outputs:
  - `renders/Issue07_Froese_Koroma/froese_clone_full_interview.mp3`
  - `renders/Issue07_Froese_Koroma/froese_clone_full_interview_youtube_refs.mp3`
- Text source: `output/audio_interviews/**/qa_*.txt`, using the existing
  `QUESTION SPOKEN TEXT` and `ANSWER SPOKEN TEXT` protocol that strips layout,
  citations, brackets, URLs, and visual-only material.

## Pipeline

1. Build or update a voice profile in `profiles/`.
2. Use source audio listed in `sources/` or download a consented public lecture
   source into `sources/raw/`.
3. Extract a clean 8-20 second reference clip per speaker.
4. Enhance the reference clip lightly for intelligibility.
5. Generate F5-TTS input text/config from `qa_*.txt`.
6. Render WAV, transcode to MP3, then verify duration and intelligibility.

## Ethical Gate

Do not render a speaker profile unless the consent field is explicitly marked
`confirmed`. Synthetic interview audio should be labeled as synthetic in
downstream publishing metadata.

Generated audio transcripts in `output/audio_interviews/` or upload caches are
not treated as natural voice-reference sources unless a profile explicitly marks
them as such. They are complete audio-transcript outputs, not proof of speaker
identity for voice cloning.

## Local Runtime

The current working runtime is:

- Python venv: `%LOCALAPPDATA%\Codex\venvs\f5-tts`
- CUDA PyTorch: `torch==2.5.1+cu121`
- GPU used in testing: NVIDIA GeForce RTX 3060 Laptop GPU

The wrapper `scripts/run_f5_soundfile.py` bypasses Windows TorchCodec/FFmpeg DLL
issues by loading WAV references through `soundfile`.

When YouTube blocks anonymous extraction, `scripts/download_youtube_audio.py`
records the failed attempt in `sources/download_log.csv`. A cookie-backed retry
can be attempted with `--cookies-from-browser chrome` or
`--cookies-from-browser edge` when the local browser cookies are accessible.
If browser-cookie extraction fails because the database is locked or DPAPI cannot
decrypt it, export a Netscape-format cookies file from the browser and pass it
with `--cookies path\to\youtube-cookies.txt`.
