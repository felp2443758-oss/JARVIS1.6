"""Local wake-word detector using a rolling 4-second buffer + faster-whisper (tiny)."""
from __future__ import annotations
import os
import io
import time
import threading
from typing import Callable, List, Optional

import numpy as np
import soundfile as sf

from voice import MicStream, SAMPLE_RATE


class WakeWordDetector:
    def __init__(self, phrases: List[str], on_wake: Callable[[str], None],
                 model_size: Optional[str] = None, samplerate: int = SAMPLE_RATE):
        self.phrases = [p.strip().lower() for p in phrases if p.strip()]
        self.on_wake = on_wake
        self.samplerate = samplerate
        self.mic = MicStream(seconds=4.0, samplerate=samplerate)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Load faster-whisper tiny (CPU). ~75 MB, low-latency.
        from faster_whisper import WhisperModel  # local import — heavy
        self.model = WhisperModel(model_size or os.getenv("WHISPER_MODEL", "tiny"),
                                  device="cpu", compute_type="int8")

    def _loop(self):
        while not self._stop.is_set():
            time.sleep(1.4)  # check every ~1.4s
            audio = self.mic.snapshot()
            if np.max(np.abs(audio)) < 0.01:
                continue  # too quiet
            buf = io.BytesIO()
            sf.write(buf, audio, self.samplerate, format="WAV")
            buf.seek(0)
            try:
                segs, _ = self.model.transcribe(buf, language="pt", vad_filter=True, beam_size=1)
                text = " ".join(s.text for s in segs).strip().lower()
            except Exception:
                continue
            if not text:
                continue
            hit = next((p for p in self.phrases if p in text), None)
            if hit:
                # Throttle: clear buffer so we don't trigger again right away
                self.mic.buffer = np.zeros_like(self.mic.buffer)
                try:
                    self.on_wake(text)
                except Exception as e:
                    print(f"[wake] on_wake error: {e}")

    def start(self):
        self.mic.start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[wake] listening for: {' | '.join(self.phrases)}")

    def stop(self):
        self._stop.set()
        self.mic.stop()
