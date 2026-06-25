# Kokoro Fallback Voice Policy

Date: 2026-06-03

## Purpose

The preferred path is always a consented, public, natural-voice reference for
the real speaker. If no confirmed real source can be found, the KokoClone/Kokoro
comparison renderer may use a clearly marked Kokoro fallback voice so the
interview can still be rendered.

Fallback output is not a real voice clone. Manifests must record
`fallback_voice_usage` and set `not_a_real_voice_clone: true` for each fallback
speaker.

## Profile Fields

Fallbacks live in the speaker profile:

```json
"fallback_voice": {
  "enabled": true,
  "engine": "kokoro_onnx",
  "kokoro_voice": "af_aoede",
  "kokoro_lang": "en-us",
  "speed": 0.9,
  "selection_reason": "Why this fallback was selected.",
  "not_a_real_voice_clone": true
}
```

The KokoClone renderer uses the real reference when `reference_audio` exists.
It uses the fallback only when the profile is missing usable reference audio or
reference text and the fallback is explicitly enabled.

## Current Fallbacks

| Speaker | Fallback | Reason |
| --- | --- | --- |
| Cordelia Erickson-Davis | `af_aoede`, `en-us` | No confirmed public natural-voice source found after expanded audit; adult American female fallback. |
| Katrin Preller | `ff_siwis`, `en-us` | Contingency only. Primary path uses her real lecture reference. Current Kokoro v1.0 voices include no dedicated German English voice, so this is the closest available continental-European female fallback until a better German-accented sample/model is available. |

## Available Local Kokoro v1.0 Voices

The installed `voices-v1.0.bin` currently exposes:

```text
af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova
af_river af_sarah af_sky
am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa
bf_alice bf_emma bf_isabella bf_lily
bm_daniel bm_fable bm_george bm_lewis
ef_dora em_alex em_santa
ff_siwis
hf_alpha hf_beta hm_omega hm_psi
if_sara im_nicola
jf_alpha jf_gongitsune jf_nezumi jf_tebukuro jm_kumo
pf_dora pm_alex pm_santa
zf_xiaobei zf_xiaoni zf_xiaoxiao zf_xiaoyi
zm_yunjian zm_yunxi zm_yunxia zm_yunyang
```

The local `kokoro_onnx` tokenizer documents English phonemization as `en-us` or
`en-gb`. KokoClone's README lists multilingual routes for English, Hindi,
French, Japanese, Chinese, Italian, Portuguese, and Spanish, but not German.
