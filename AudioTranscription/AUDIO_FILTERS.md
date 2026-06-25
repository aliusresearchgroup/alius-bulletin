# Audio Filter Presets

The voice-clone reference clip should be clear, dry speech. The filters here
make rough microphones more usable without trying to create a different voice.

Presets are defined in `config/audio_filters.json` and executed through
`scripts/enhance_reference_audio.py`.

## Preset Policy

- Start with `lecture_cleanup` for public lecture/podcast sources.
- Use `speech_reference_crisp_noisy_mic` for local interview recordings, laptop
  microphones, or muffled headset audio.
- Use `speech_reference_light` when the source is already clean.
- Use `aggressive_noisy_mic` only when the other presets leave speech hard to
  understand; it can introduce denoising artifacts.
- Prefer a cleaner public lecture/interview source over aggressive processing
  of a poor original recording. Better source audio usually gives a more
  natural clone than stronger denoising.
- Prefer reference moments with engaged, positive delivery when the final
  interview should sound warm or enthusiastic. The clone inherits more affect
  from the reference clip than from any downstream EQ/compression preset.
- Keep reference clips 6-11.5 seconds long. F5-TTS truncates longer prompts at
  about 12 seconds, which can make the unspoken tail of `reference_text` leak
  into generated interview audio.
- Keep reference clips sentence-bounded. Do not end on a partial word, a list of
  names, an outro, or a transition to another speaker. A short clean pause after
  the final word is safer than a clipped tail.

## Command

```powershell
python AudioTranscription/scripts/enhance_reference_audio.py `
  --input "source.wav" `
  --output "AudioTranscription/references/<speaker>/<speaker>_ref.wav" `
  --preset speech_reference_crisp_noisy_mic `
  --start 600 `
  --duration 10
```

The output is always 24 kHz mono WAV, suitable as an F5-TTS reference prompt.
The script rejects references longer than 11.5 seconds unless
`--allow-long-reference` is passed for a controlled experiment.

After creating a reference, run a short ASR/listening check on the reference
itself. The transcript should match the profile `reference_text` and should not
include bracketed stage directions, captions, music cues, or another speaker.

## Why These Filters

- `highpass` removes rumble and plosives below speech fundamentals.
- `lowpass` removes hiss and brittle high-frequency artifacts.
- `afftdn` reduces stationary broadband noise.
- `equalizer` adds intelligibility around the speech presence band.
- `acompressor` evens out inconsistent microphone distance.
- `loudnorm` gives repeatable reference loudness for clone prompting.

The manifest written beside each output records the preset and exact FFmpeg
filter chain, so reference generation is auditable and repeatable.

Final MP3 renders use a separate, mild `engaged` delivery preset by default.
That preset adds presence and smooths dynamics; it should not be treated as a
replacement for selecting lively, clean reference speech.
