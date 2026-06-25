#!/usr/bin/env python3
"""Run F5-TTS inference with soundfile-backed WAV loading on Windows.

The current torchaudio release routes audio loading through torchcodec, which
requires shared FFmpeg DLLs. The local FFmpeg install is static, but the
reference clips for this project are ordinary WAV files. This wrapper keeps the
F5-TTS CLI behavior while replacing only torchaudio.load with soundfile.
"""

from __future__ import annotations

import runpy
import sys

import numpy as np
import soundfile as sf
import torch
import torchaudio


def soundfile_load(path: str, *args, **kwargs):
    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    tensor = torch.from_numpy(np.ascontiguousarray(data.T))
    return tensor, sample_rate


torchaudio.load = soundfile_load
sys.argv[0] = "f5-tts_infer-cli"
runpy.run_module("f5_tts.infer.infer_cli", run_name="__main__")
