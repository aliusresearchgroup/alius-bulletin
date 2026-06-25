#!/usr/bin/env python3
"""Run F5-TTS with soundfile-backed WAV loading on Windows.

F5-TTS calls torchaudio.load. Recent torchaudio versions use TorchCodec for
audio decoding, which expects shared FFmpeg DLLs on Windows. This project uses
24 kHz mono WAV reference clips, so soundfile is sufficient and more reliable.
"""

from __future__ import annotations

import runpy
import sys
import concurrent.futures

import numpy as np
import soundfile as sf
import torch
import torchaudio


def soundfile_load(path: str, *args, **kwargs):
    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    tensor = torch.from_numpy(np.ascontiguousarray(data.T))
    return tensor, sample_rate


class _ImmediateFuture:
    def __init__(self, fn, args, kwargs):
        self._exception = None
        self._result = None
        try:
            self._result = fn(*args, **kwargs)
        except BaseException as exc:
            self._exception = exc

    def result(self):
        if self._exception is not None:
            raise self._exception
        return self._result


class _SerialThreadPoolExecutor:
    """Keep F5 chunk inference serial so long batches do not overcommit GPU RAM."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def submit(self, fn, *args, **kwargs):
        return _ImmediateFuture(fn, args, kwargs)


torchaudio.load = soundfile_load
concurrent.futures.ThreadPoolExecutor = _SerialThreadPoolExecutor
sys.argv[0] = "f5-tts_infer-cli"
runpy.run_module("f5_tts.infer.infer_cli", run_name="__main__")
