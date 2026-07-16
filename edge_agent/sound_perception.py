"""Ambient sound perception for the J.A.R.V.I.S. Edge Agent.

A lightweight, dependency-free classifier built on simple acoustic features
(RMS energy, zero-crossing rate, spectral centroid, spectral roll-off).
It is NOT as accurate as YAMNet, but it requires zero extra model files and
is more than enough to flag interesting events ("loud noise", "speech",
"silence", "music", "hand clap").

For higher accuracy, swap with TF-Lite YAMNet (model ~3.7 MB).

Usage:
    from sound_perception import AmbientListener
    AmbientListener(on_event=lambda lbl, score: print(lbl, score)).start()
"""
from __future__ import annotations
import os
import time
import threading
from typing import Callable, Optional, Dict

import numpy as np
import sounddevice as sd

SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))


def _spectral_features(frame: np.ndarray, sr: int) -> Dict[str, float]:
    win = np.hanning(len(frame))
    spec = np.abs(np.fft.rfft(frame * win))
    freqs = np.fft.rfftfreq(len(frame), 1.0 / sr)
    total = spec.sum() + 1e-9
    centroid = float((freqs * spec).sum() / total)
    cumulative = np.cumsum(spec)
    rolloff_idx = int(np.searchsorted(cumulative, 0.85 * cumulative[-1]))
    rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])
    flatness = float(np.exp(np.mean(np.log(spec + 1e-9))) / (np.mean(spec) + 1e-9))
    return {"centroid": centroid, "rolloff": rolloff, "flatness": flatness}


def classify(frame: np.ndarray, sr: int = SAMPLE_RATE) -> Dict[str, float]:
    rms = float(np.sqrt(np.mean(frame ** 2)))
    zcr = float(np.mean(np.abs(np.diff(np.sign(frame))))) / 2.0
    feats = _spectral_features(frame, sr)
    label, conf = "silence", 0.0
    if rms < 0.005:
        label, conf = "silence", 0.95
    elif rms > 0.20:
        label, conf = "loud_noise", 0.85
    elif zcr > 0.18 and rms > 0.04 and feats["centroid"] > 1800:
        label, conf = "hand_clap", 0.7
    elif feats["centroid"] > 1500 and feats["flatness"] < 0.2 and rms > 0.015:
        label, conf = "music", 0.6
    elif 80 < feats["centroid"] < 1600 and zcr > 0.04 and rms > 0.02:
        label, conf = "speech", 0.7
    else:
        label, conf = "ambient", 0.4
    return {"label": label, "confidence": conf, "rms": rms, "zcr": zcr, **feats}


class AmbientListener:
    def __init__(self, on_event: Callable[[str, float], None], window_s: float = 1.0,
                 hop_s: float = 0.5, samplerate: int = SAMPLE_RATE,
                 min_confidence: float = 0.6):
        self.on_event = on_event
        self.win = int(window_s * samplerate)
        self.hop = int(hop_s * samplerate)
        self.samplerate = samplerate
        self.min_confidence = min_confidence
        self._buf = np.zeros(self.win, dtype=np.float32)
        self._stream: Optional[sd.InputStream] = None
        self._stop = threading.Event()
        self._last_label: Optional[str] = None
        self._timer = 0

    def _cb(self, indata, frames, time_, status):  # noqa: ANN001
        mono = indata[:, 0] if indata.ndim > 1 else indata
        n = len(mono)
        if n >= self.win:
            self._buf = mono[-self.win:].copy()
        else:
            self._buf = np.roll(self._buf, -n)
            self._buf[-n:] = mono
        self._timer += n
        if self._timer >= self.hop:
            self._timer = 0
            res = classify(self._buf, self.samplerate)
            label = res["label"]
            if label != self._last_label and res["confidence"] >= self.min_confidence:
                self._last_label = label
                try:
                    self.on_event(label, res["confidence"])
                except Exception as e:
                    print(f"[ambient] handler error: {e}")

    def start(self):
        self._stream = sd.InputStream(
            channels=1, samplerate=self.samplerate, dtype="float32",
            callback=self._cb, blocksize=1024,
        )
        self._stream.start()
        print("[ambient] sound perception started")

    def stop(self):
        if self._stream:
            self._stream.stop(); self._stream.close()
            self._stream = None


if __name__ == "__main__":
    AmbientListener(on_event=lambda lbl, s: print(f">>> {lbl} ({s:.2f})")).start()
    while True:
        time.sleep(1)
