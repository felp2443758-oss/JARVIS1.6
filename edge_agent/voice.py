"""Microphone capture and audio playback helpers for the Edge Agent."""
from __future__ import annotations
import io
import os
import wave
import time
import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
import requests

SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))


class MicStream:
    """Continuous mic capture into a ring buffer (numpy float32, mono)."""

    def __init__(self, seconds: float = 6.0, samplerate: int = SAMPLE_RATE):
        self.samplerate = samplerate
        self.size = int(seconds * samplerate)
        self.buffer = np.zeros(self.size, dtype=np.float32)
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def _cb(self, indata, frames, time_, status):  # noqa: ANN001
        mono = indata[:, 0] if indata.ndim > 1 else indata
        with self._lock:
            n = len(mono)
            if n >= self.size:
                self.buffer = mono[-self.size:].copy()
            else:
                self.buffer = np.roll(self.buffer, -n)
                self.buffer[-n:] = mono

    def start(self):
        self._stream = sd.InputStream(
            channels=1, samplerate=self.samplerate,
            dtype="float32", callback=self._cb, blocksize=1024,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return self.buffer.copy()


def record_until_silence(max_seconds: float = 10.0, silence_threshold: float = 0.012,
                         silence_window: float = 1.2, samplerate: int = SAMPLE_RATE) -> bytes:
    """Records mic audio until a `silence_window` of low RMS, or max_seconds."""
    print("[voice] recording …")
    frames: list[np.ndarray] = []
    started = time.time()
    silence_start: Optional[float] = None
    q: queue.Queue = queue.Queue()

    def cb(indata, _frames, _time, _status):
        q.put(indata.copy())

    with sd.InputStream(channels=1, samplerate=samplerate, dtype="float32", callback=cb, blocksize=1024):
        while True:
            try:
                chunk = q.get(timeout=0.5)
            except queue.Empty:
                chunk = np.zeros((512, 1), dtype=np.float32)
            mono = chunk[:, 0]
            frames.append(mono)
            rms = float(np.sqrt(np.mean(mono ** 2)))
            now = time.time()
            if rms < silence_threshold:
                silence_start = silence_start or now
                if now - silence_start >= silence_window and now - started > 1.0:
                    break
            else:
                silence_start = None
            if now - started > max_seconds:
                break

    audio = np.concatenate(frames) if frames else np.zeros(samplerate, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, audio, samplerate, format="WAV")
    buf.seek(0)
    return buf.read()


def play_mp3_bytes(mp3_bytes: bytes):
    """Plays MP3 bytes via simpleaudio (decoded with soundfile)."""
    import simpleaudio as sa
    # Decode (requires ffmpeg/libsndfile w/ MP3 support, available on most systems).
    try:
        data, sr = sf.read(io.BytesIO(mp3_bytes), dtype="int16")
    except Exception:
        # Fallback: write tmp and use system player
        tmp = "/tmp/jarvis_tts.mp3"
        with open(tmp, "wb") as f:
            f.write(mp3_bytes)
        os.system(f"ffplay -nodisp -autoexit -loglevel quiet {tmp} >/dev/null 2>&1")
        return
    if data.ndim == 1:
        channels = 1
    else:
        channels = data.shape[1]
    play_obj = sa.play_buffer(data.tobytes(), num_channels=channels, bytes_per_sample=2, sample_rate=sr)
    play_obj.wait_done()


def tts_speak(brain_url: str, text: str, voice: str = "onyx"):
    """Calls the cloud /api/tts endpoint and plays the resulting MP3."""
    if not text:
        return
    r = requests.post(f"{brain_url}/api/tts", json={"text": text, "voice": voice, "speed": 1.05})
    r.raise_for_status()
    play_mp3_bytes(r.content)


def stt_transcribe(brain_url: str, wav_bytes: bytes) -> str:
    """POSTs WAV bytes to the cloud /api/stt (Whisper-1) and returns transcript."""
    files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
    r = requests.post(f"{brain_url}/api/stt", files=files, timeout=60)
    r.raise_for_status()
    return r.json().get("text", "")
