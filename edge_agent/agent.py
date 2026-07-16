"""
J.A.R.V.I.S. Edge Agent — main loop.

Flow:
  1) On boot: load .env, open WebSocket to the Cloud Brain.
  2) Start local wake-word detector (faster-whisper, tiny model, CPU).
  3) When a wake-word is heard:
       a) Try face authentication via webcam (face_recognition embedding).
       b) Call /api/activation to fetch a personalized greeting + morning report.
       c) Speak the greeting using cloud TTS (OpenAI tts-1, voice=onyx).
       d) Enter "conversation mode": record_until_silence → /api/stt → /api/chat/send → /api/tts.
       e) Loop until user says "obrigado, jarvis" / "encerrar" / 60s silence.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import sys
import time
import threading
from typing import Optional

import requests
import websockets
from dotenv import load_dotenv

from voice import record_until_silence, tts_speak, stt_transcribe
from wake_word import WakeWordDetector
from vision import capture_embedding
from actions import dispatch as action_dispatch

# Optional modules (loaded lazily so the agent still runs if MediaPipe isn't installed)
try:
    from gestures import GestureController
    GESTURES_AVAILABLE = True
except Exception:
    GESTURES_AVAILABLE = False
try:
    from sound_perception import AmbientListener
    AMBIENT_AVAILABLE = True
except Exception:
    AMBIENT_AVAILABLE = False

load_dotenv()

BRAIN_URL = os.getenv("BRAIN_URL", "").rstrip("/")
AGENT_ID = os.getenv("AGENT_ID", "edge-agent")
OWNER_NAME = os.getenv("OWNER_NAME", "Felipe Stark")
WAKE_WORDS = [w.strip().lower() for w in os.getenv(
    "WAKE_WORDS", "bom dia jarvis,boa tarde jarvis,boa noite jarvis,jarvis"
).split(",") if w.strip()]


# ---------- WS bridge ----------
class BrainBridge:
    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def _run(self):
        wsurl = BRAIN_URL.replace("http", "ws") + f"/api/ws/agent/{AGENT_ID}"
        while True:
            try:
                async with websockets.connect(wsurl, ping_interval=20) as ws:
                    self.ws = ws
                    print(f"[bridge] connected to {wsurl}")
                    await ws.send(json.dumps({"type": "status", "data": {"online": True}}))
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        # Brain → Agent commands (e.g. forced wake)
                        if data.get("type") == "command":
                            print(f"[bridge] command: {data}")
            except Exception as e:
                print(f"[bridge] disconnected ({e}); retrying in 3s")
                await asyncio.sleep(3)

    def start(self):
        def _runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._run())
        threading.Thread(target=_runner, daemon=True).start()

    def emit(self, payload: dict):
        if not self.ws or not self._loop:
            return
        async def _send():
            try:
                await self.ws.send(json.dumps(payload))
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(_send(), self._loop)


# ---------- Auth ----------
def try_face_auth() -> Optional[dict]:
    print("[auth] capturing face for authentication…")
    emb = capture_embedding(0)
    if not emb:
        print("[auth] no face detected — continuing as guest")
        return None
    try:
        r = requests.post(f"{BRAIN_URL}/api/face/auth",
                          json={"embedding": emb, "threshold": 0.6}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("authenticated"):
            print(f"[auth] OK — {data['name']}")
            return data
        print(f"[auth] no match (distance={data.get('distance')})")
    except Exception as e:
        print(f"[auth] error: {e}")
    return None


# ---------- Conversation ----------
EXIT_WORDS = ("obrigado jarvis", "obrigada jarvis", "encerrar", "tchau jarvis", "desligar")


def converse(bridge: BrainBridge, session_id: Optional[str] = None):
    """Conversation loop: STT → Brain chat → TTS, until exit word or 60s silence."""
    idle_start = time.time()
    while True:
        if time.time() - idle_start > 60:
            print("[conv] idle 60s — leaving conversation mode")
            return session_id
        try:
            wav = record_until_silence(max_seconds=12.0)
        except Exception as e:
            print(f"[conv] mic error: {e}")
            return session_id
        text = ""
        try:
            text = stt_transcribe(BRAIN_URL, wav).strip()
        except Exception as e:
            print(f"[conv] STT error: {e}")
            continue
        if not text:
            continue
        print(f"[user] {text}")
        bridge.emit({"type": "transcript", "role": "user", "text": text})
        if any(w in text.lower() for w in EXIT_WORDS):
            tts_speak(BRAIN_URL, "Às ordens. Encerrando o modo de conversa.")
            return session_id
        try:
            r = requests.post(f"{BRAIN_URL}/api/chat/send",
                              json={"message": text, "session_id": session_id, "user_id": "owner"},
                              timeout=60)
            r.raise_for_status()
            data = r.json()
            session_id = data["session_id"]
            reply = data["text"]
        except Exception as e:
            print(f"[conv] chat error: {e}")
            continue
        print(f"[JARVIS] {reply}")
        bridge.emit({"type": "transcript", "role": "assistant", "text": reply})
        try:
            tts_speak(BRAIN_URL, reply)
        except Exception as e:
            print(f"[conv] TTS error: {e}")
        idle_start = time.time()
        # Crude local action trigger
        low = reply.lower()
        if "abrir spotify" in low or "tocar" in low:
            action_dispatch("open_app", name="spotify")


# ---------- Wake handler ----------
def on_wake(bridge: BrainBridge, transcript: str):
    print(f"\n[WAKE] '{transcript}'")
    bridge.emit({"type": "wake", "transcript": transcript})

    # 1) Face auth
    profile = try_face_auth()
    user_id = (profile or {}).get("user_id", "owner")

    # 2) Activation → greeting + morning report
    try:
        r = requests.post(f"{BRAIN_URL}/api/activation",
                          json={"user_id": user_id, "transcript": transcript}, timeout=20)
        r.raise_for_status()
        data = r.json()
        greeting = data["greeting"]
        mr = data.get("morning_report")
        full = greeting + (f" {mr['summary']}" if mr else "")
    except Exception as e:
        full = f"Olá. (Erro ao contatar o cérebro: {e})"
    print(f"[JARVIS] {full}")
    bridge.emit({"type": "transcript", "role": "assistant", "text": full})
    try:
        tts_speak(BRAIN_URL, full)
    except Exception as e:
        print(f"[wake] TTS error: {e}")

    # 3) Conversation mode
    converse(bridge)


# ---------- Entrypoint ----------
def main():
    if not BRAIN_URL:
        print("ERRO: defina BRAIN_URL em .env"); sys.exit(2)
    print(f"[J.A.R.V.I.S. Edge Agent] connecting to brain at {BRAIN_URL}")
    bridge = BrainBridge()
    bridge.start()
    detector = WakeWordDetector(WAKE_WORDS, on_wake=lambda t: on_wake(bridge, t))
    detector.start()

    # Optional: gestures + ambient sound perception
    gesture_ctrl = None
    if os.getenv("ENABLE_GESTURES", "0") == "1" and GESTURES_AVAILABLE:
        def on_gesture(g: str):
            print(f"[gesture] {g}")
            bridge.emit({"type": "agent_status", "data": {"gesture": g}})
            if g == "OPEN_PALM":
                # request brain to stop / cancel
                bridge.emit({"type": "transcript", "role": "user", "text": "(gesto: parar)"})
            elif g == "POINTING_UP":
                on_wake(bridge, "(gesto: ativar)")
        gesture_ctrl = GestureController(on_gesture=on_gesture)
        gesture_ctrl.start()

    ambient = None
    if os.getenv("ENABLE_AMBIENT", "0") == "1" and AMBIENT_AVAILABLE:
        def on_event(lbl: str, score: float):
            bridge.emit({"type": "agent_status", "data": {"ambient": lbl, "confidence": score}})
        ambient = AmbientListener(on_event=on_event)
        ambient.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[exit] shutting down")
        detector.stop()
        if gesture_ctrl: gesture_ctrl.stop()
        if ambient: ambient.stop()


if __name__ == "__main__":
    main()
