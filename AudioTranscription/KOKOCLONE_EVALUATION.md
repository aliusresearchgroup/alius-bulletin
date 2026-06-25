# KokoClone Evaluation

Date: 2026-06-03

## Summary

KokoClone is now installed and wired in as a parallel comparison engine, but it
should not replace the current F5-TTS rendering pipeline mid-run.

The project describes itself as a fast multilingual voice-cloning system built on Kokoro-ONNX, taking a short 3-10 second reference clip and generating cloned speech from typed text. It also appears to use a Kanade voice-conversion stage on top of Kokoro-generated base speech.

Relevant links:

- GitHub: https://github.com/Ashish-Patnaik/kokoclone
- Hugging Face mirror/README: https://huggingface.co/PatnaikAshish/kokoclone
- Requirements snapshot: https://huggingface.co/PatnaikAshish/kokoclone/blob/main/requirements.txt

## Current Local Result

- KokoClone checkout: `AudioTranscription/tools/kokoclone`
- Runtime Python: `C:\Users\cogpsy-vrlab\AppData\Local\Codex\venvs\f5-tts\Scripts\python.exe`
- Installed without replacing Torch/Torchaudio; Torch remains `2.5.1+cu121`
  with CUDA available.
- First smoke render: `Issue05_Schmidt_Fejer`, `--max-units 1`,
  API execution mode.
- Output MP3:
  `AudioTranscription/renders_kokoclone/Issue05_Schmidt_Fejer/Issue05_Schmidt_Fejer_clone_full_interview_kokoclone.mp3`
- Duration: 295.256 seconds.
- Loudness check: mean volume about `-17.9 dB`, max volume about `-2.4 dB`.
- First full interview render: `Issue03_Dienes_Martin`.
- Full render output:
  `AudioTranscription/renders_kokoclone/Issue03_Dienes_Martin/Issue03_Dienes_Martin_clone_full_interview_kokoclone.mp3`
- Full render duration: 1070.656 seconds.
- Full render loudness check: mean volume about `-18.8 dB`, max volume about
  `-2.4 dB`.
- KokoClone coverage audit: `yes/yes: 2`, `yes/no: 31`.

The first attempt used one CLI call per chunk and was too slow because it
reloaded Kanade/Kokoro repeatedly. The renderer now defaults to KokoClone's
Python API, which loads the models once per interview and reuses them.

## Why Not Switch Now

- The current F5 pipeline already has 56 passing speaker profiles and verified full-interview renders.
- KokoClone introduces another model stack (`kokoro-onnx`, Kanade tokenizer/conversion dependencies).
- Disk remains tight after model installation, so full batches need cleanup between runs.
- Its voice conversion path may be useful for speed, but it needs an A/B test against F5 before production use.

## Where It Could Help

- Fast CPU-friendly smoke tests before expensive F5 renders.
- Audio-to-audio conversion from a neutral Kokoro render into a target speaker voice, if it proves stable.
- Possibly better throughput for long interview drafts once dependency size and quality are measured.

## Test Gate Before Adoption

Before using KokoClone for production bulletin audio:

1. Render one short Q&A for a speaker already validated in F5. Done for
   `Issue05_Schmidt_Fejer`.
2. Compare speaker similarity, intelligibility, prosody, noise, pace, and
   pronunciation of `ALIUS`.
3. Confirm it can batch-render long interviews without drift or chapter-boundary
   issues. First full render completed for `Issue03_Dienes_Martin`.
4. Add ASR and human listening checks before any KokoClone MP3 is promoted to
   website export.

Decision for now: continue F5 for production renders, and generate KokoClone
variants as controlled A/B tests. Use the better verified MP3 for website
export.
