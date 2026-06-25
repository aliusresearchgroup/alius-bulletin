# Repeatable Voice-Cloned Interview Audio Pipeline

## Inputs

- Interview Q/A spoken text:
  `output/audio_interviews/<Issue>/<Interview>/qa_*.txt`
- Speaker profile:
  `AudioTranscription/profiles/<speaker_slug>.json`
- Interview render plan:
  `AudioTranscription/render_plans/<interview_slug>.json`
- Optional public source video/audio:
  recorded through `AudioTranscription/sources/youtube_candidates.csv`,
  `AudioTranscription/sources/youtube_candidate_ranking.csv`,
  `AudioTranscription/sources/blocked_youtube_sources.csv`, and
  `AudioTranscription/sources/download_log.csv`

## Source Audio Selection

Preferred source order:

1. Original interview source audio with the speaker.
2. Public lecture or interview audio where the speaker is dominant.
3. Existing public podcast or seminar recording.

Do not use generated audio-transcript outputs as speaker voice references by
default. Files under `output/audio_interviews/` and upload-cache exports such as
`*_outro.wav` are useful for publishing/verifying complete audio transcripts,
but they should not be used to clone a natural speaker voice unless the file is
confirmed to contain natural recorded speech from that speaker.

Reference clips should be:

- 6-11.5 seconds long. F5-TTS clips long reference audio to about 12
  seconds, so longer profile text can leak into generated speech after the
  audio prompt has already been truncated.
- Mostly one speaker
- Low background noise
- No music
- No overlap
- Pauseless enough to capture timbre and prosody
- Natural, engaged delivery when possible. For interview audio transcripts,
  prefer references where the speaker sounds clear, warm, and positively
  engaged rather than fatigued, monotone, rushed, or reading under pressure.
- Sentence-bounded, with no trailing partial phrase or handoff to another
  speaker. F5 can leak the end of the reference prompt into generated speech
  when the clip/text ends on a fragment.
- Prefer a clean breath or short silence at the end over a clipped final word.

## Text Normalization

The Q/A spoken text is lightly normalized before F5 rendering. This keeps the
published audio transcript listenable while preserving the transcript's meaning:

- Mojibake punctuation from PDF/LaTeX conversion is repaired where known.
- `ALIUS`, `A.L.I.U.S.`, and spaced letter variants are rendered as lowercase
  `alius` so the model says the association name as a word instead of spelling
  it letter by letter.
- Common formal symbols such as logical negation, arrows, inequalities, and
  multiplication are converted to short spoken forms for audio rendering.
- Selected proper names may be phonetically normalized for speech when a TTS
  voice otherwise mispronounces them; keep public titles and metadata in the
  standard written spelling.
- Bracketed stage directions, citations, or page cues should be removed during
  transcript preparation; they should not be left for TTS to interpret.

## Audio Cleanup

Use repeatable filtering, but keep it light enough to preserve the speaker.
The goal is to make the prompt clearer, not to erase identity-bearing features.
The canonical presets are documented in
`AudioTranscription/AUDIO_FILTERS.md` and defined in
`AudioTranscription/config/audio_filters.json`.

Preferred command:

```powershell
python AudioTranscription/scripts/enhance_reference_audio.py `
  --input "source.wav" `
  --output "AudioTranscription/references/<speaker>/<speaker>_ref.wav" `
  --preset speech_reference_crisp_noisy_mic `
  --start 600 `
  --duration 10
```

Always output reference WAV as 24 kHz mono PCM:

```powershell
ffmpeg -i input.wav -af "<filter>" -ar 24000 -ac 1 output_ref_enhanced.wav
```

For reviewed YouTube candidates, download native audio first and avoid full WAV
copies unless a tool needs them:

```powershell
python AudioTranscription/scripts/download_youtube_audio.py `
  --speaker "<speaker_slug>" `
  --speaker-name "<Speaker Name>" `
  --url "https://www.youtube.com/watch?v=<id>"
```

If YouTube requires authenticated cookies and local browser cookies are
accessible:

```powershell
python AudioTranscription/scripts/download_youtube_audio.py `
  --speaker "<speaker_slug>" `
  --speaker-name "<Speaker Name>" `
  --url "https://www.youtube.com/watch?v=<id>" `
  --cookies-from-browser chrome
```

If browser-cookie extraction fails, export YouTube cookies to a Netscape-format
file and retry the exact blocked candidate:

```powershell
python AudioTranscription/scripts/download_youtube_audio.py `
  --speaker "<speaker_slug>" `
  --speaker-name "<Speaker Name>" `
  --url "https://www.youtube.com/watch?v=<id>" `
  --cookies "C:\path\to\youtube-cookies.txt" `
  --extractor-args "youtube:player_client=web_embedded,android"
```

To retry every verified row in `sources/blocked_youtube_sources.csv`:

```powershell
python AudioTranscription/scripts/retry_blocked_youtube_sources.py `
  --cookies "C:\path\to\youtube-cookies.txt"
```

## Rendering

Before rendering, audit the voice profiles. Any profile with a missing
reference, SHA mismatch, or reference longer than 11.5 seconds blocks batch
rendering until the profile is fixed or deliberately overridden:

```powershell
python AudioTranscription/scripts/audit_voice_profiles.py
python AudioTranscription/scripts/audit_render_coverage.py
```

Generate an F5 input/config from a render plan:

```powershell
python AudioTranscription/scripts/build_f5_inputs.py `
  --plan AudioTranscription/render_plans/Issue07_Froese_Koroma.json
```

Render with F5:

```powershell
%LOCALAPPDATA%\Codex\venvs\f5-tts\Scripts\python.exe `
  AudioTranscription/scripts/run_f5_soundfile.py `
  --config AudioTranscription/work/Issue07_Froese_Koroma/f5_config.toml `
  --device cuda `
  --nfe_step 16
```

Transcode and standardize the final MP3:

```powershell
ffmpeg -i AudioTranscription/work/Issue07_Froese_Koroma/interview.wav `
  -af "loudnorm=I=-18:TP=-2:LRA=11" -ar 24000 -ac 1 `
  -codec:a libmp3lame -b:a 128k `
  AudioTranscription/renders/Issue07_Froese_Koroma/interview.mp3
```

`render_interview.py` applies final delivery shaping plus `loudnorm` by default
and records it under `audio_postprocess` in the render manifest. This keeps
published interview MP3s closer in perceived volume even when the cloned
speaker references came from very different microphones.

The default delivery preset is `engaged`, a mild presence/dynamics filter. It
can make speech feel clearer and a little more energetic, but it is not true
emotion synthesis. True positive/enthusiastic intonation mostly comes from
choosing reference clips where the speaker is already warm, lively, and
engaged. If the filter sounds too bright for a particular speaker, render with:

```powershell
python AudioTranscription/scripts/render_interview.py `
  --plan AudioTranscription/render_plans/<interview_slug>.json `
  --delivery-preset neutral
```

Talking pace should start from the default F5 speed of `1.0`. If a speaker is
consistently too fast or too slow after listening review, add a conservative
per-voice override to the render plan:

```json
"tts": {
  "model": "F5TTS_v1_Base",
  "nfe_step": 16,
  "speed": 1.0,
  "voice_speeds": {
    "speaker_slug": 0.95
  },
  "remove_silence": false
}
```

Use small adjustments first (`0.92-1.08`). Larger changes tend to make cloned
voices sound less natural. If a whole interview needs a slight final correction
without re-synthesis, `render_interview.py --transcode-only --final-tempo 0.97`
can apply ffmpeg `atempo` while preserving pitch, but re-rendering with
speaker-level speed is preferred when one speaker is the actual problem.

Render every currently renderable, not-yet-rendered plan sequentially:

```powershell
python AudioTranscription/scripts/batch_render_interviews.py
```

For a shorter smoke-test queue:

```powershell
python AudioTranscription/scripts/batch_render_interviews.py --limit 5
```

## KokoClone/Kokoro Comparison Renders

The production baseline remains F5-TTS because the current profile library and
verified renders use that engine. KokoClone/Kokoro is now supported as a
parallel comparison path, not a replacement. The KokoClone variant is written to
`AudioTranscription/renders_kokoclone/<interview_slug>/` so each interview can
carry both an F5 render and a KokoClone render with separate manifests.

KokoClone source checkout:

```powershell
git clone --depth 1 https://github.com/Ashish-Patnaik/kokoclone.git `
  AudioTranscription/tools/kokoclone
```

Run a no-model dry run to verify chunking, profile references, and text
normalization:

```powershell
python AudioTranscription/scripts/render_kokoclone_interview.py `
  --plan AudioTranscription/render_plans/Issue06_Gonzalez_Koroma.json `
  --kokoclone-dir AudioTranscription/tools/kokoclone `
  --max-units 1 `
  --dry-run `
  --force
```

The dry run should show `alius` in generated command text when the transcript
contains uppercase `ALIUS`.

Only install KokoClone dependencies when disk headroom is adequate. The current
working runtime is the existing F5 Python environment:

```powershell
C:\Users\cogpsy-vrlab\AppData\Local\Codex\venvs\f5-tts\Scripts\python.exe
```

The installed KokoClone additions are `kokoro-onnx`, `misaki[en]`,
`kanade-tokenizer`, and `onnxruntime`; Torch/Torchaudio stay on the existing
CUDA build. After installation, run a one-unit smoke render first. The default
execution mode uses the KokoClone Python API so Kanade/Kokoro are loaded once
and reused across all chunks:

```powershell
$py = "C:\Users\cogpsy-vrlab\AppData\Local\Codex\venvs\f5-tts\Scripts\python.exe"
& $py AudioTranscription/scripts/render_kokoclone_interview.py `
  --plan AudioTranscription/render_plans/<interview_slug>.json `
  --kokoclone-dir AudioTranscription/tools/kokoclone `
  --kokoclone-python $py `
  --max-units 1 `
  --force
```

`--force` rebuilds the final WAV/MP3/manifest from existing chunk WAVs.
Use `--force-chunks` only when the KokoClone synthesis chunks themselves should
be regenerated.

Audit KokoClone coverage:

```powershell
& $py AudioTranscription/scripts/audit_kokoclone_coverage.py
```

KokoClone coverage is fallback-aware. Profiles with missing natural references
remain blocked for F5 voice cloning, but can be renderable for KokoClone/Kokoro
when the profile contains an explicit `fallback_voice` block. See
`KOKORO_FALLBACK_VOICES.md`.

Render the KokoClone queue, shortest eligible interviews first:

```powershell
& $py AudioTranscription/scripts/batch_render_kokoclone_interviews.py
```

For a controlled smoke queue:

```powershell
& $py AudioTranscription/scripts/batch_render_kokoclone_interviews.py `
  --limit 3 `
  --max-qa-count 12 `
  --max-units 1
```

Before using KokoClone output publicly, compare it against the corresponding
F5 render for speaker similarity, intelligibility, pronunciation, pace, noise,
and chapter alignment. Promote only the better verified MP3 to the website
export.

If F5 completed a WAV but MP3 transcoding failed, rebuild the MP3 and manifest
without another synthesis pass:

```powershell
python AudioTranscription/scripts/render_interview.py `
  --plan AudioTranscription/render_plans/<interview_slug>.json `
  --transcode-only `
  --force
```

## Verification

Minimum checks:

- `ffprobe` confirms duration, codec, sample rate, and mono/stereo.
- SHA256 is recorded in the render manifest.
- A short Whisper pass confirms the generated speech follows the intended text.
- The Whisper sample should be checked for prompt-tail leakage: repeated words
  from the reference clip, outro phrases, names from a previous speaker, or
  malformed first words usually mean the reference clip/text needs to be cut
  again.
- Human listening check before publishing.

Pace/loudness checks:

```powershell
python AudioTranscription/scripts/audit_render_pace.py
```

The pace audit estimates words per minute from the source Q/A text and MP3
duration. It is a triage tool, not a substitute for listening, because pauses
and turn-taking affect perceived pace.

Disk pressure is expected during source downloads and long renders. See
`DISK_CLEANUP.md` for what is safe to remove after reference clips and final
MP3s are produced.
and paragraph boundaries are intentional. Treat `fast` or `slow` rows as
candidates for plan-level `voice_speeds` tuning or a final `--final-tempo`
correction.

## Website Export

Finished renders need the website audio-player shape used by
`aliusresearch.org/bulletin/`:

- `docs/media/audio/bulletin/kokoro/<Issue>/<Interview>/interview.mp3`
- `docs/media/audio/bulletin/kokoro/<Issue>/<Interview>/interview_chapters.json`
- `docs/media/audio/bulletin/kokoro/<Issue>/<Interview>/interview_manifest.json`
- matching source copies under `site-src/static/media/audio/bulletin/...`
- `docs/media/audio/bulletin/transcripts/index.json` metadata linking the card
  id to the MP3, download URL, chapters, SHA, engine, and ASR status.

Export a verified F5 render:

```powershell
python AudioTranscription/scripts/export_render_to_website.py `
  --interview-slug Issue05_Schmidt_Fejer `
  --card-id bulletin-schmidt-phenomenoconnectomics
```

The exporter refuses manifests without `asr_spotcheck.result=passed`. After
exporting, add or confirm the corresponding bulletin card has either an entry in
the public transcript index or a fallback `data-audio-src` attribute. Then serve
the website locally and check:

```powershell
python -m http.server 8090 --bind 127.0.0.1 -d ..\aliusresearch.org\docs
curl.exe -I http://127.0.0.1:8090/media/audio/bulletin/kokoro/Issue05/Schmidt_Fejer/interview.mp3
```

## Disk Cleanup

Full WAV renders under `AudioTranscription/work/` are intermediate files. Once
an MP3 render has a manifest and `asr_spotcheck.result` is `passed`, the WAV can
be regenerated from the same plan and profiles if needed.

Preview removable verified work WAVs:

```powershell
python AudioTranscription/scripts/cleanup_verified_work_wavs.py
```

Remove them and mark the render manifests accordingly:

```powershell
python AudioTranscription/scripts/cleanup_verified_work_wavs.py --apply
```

This cleanup does not delete source audio, reference WAVs, render manifests, or
final MP3 files.
