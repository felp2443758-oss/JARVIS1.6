"""J.A.R.V.I.S. backend integration tests."""
import os
import json
import struct
import wave
import math
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://jarvis-ai-1054.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    return s


def _make_wav(path="/tmp/t.wav", freq=440, duration_s=1, rate=16000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for i in range(int(rate * duration_s)):
            sample = int(32767 * 0.2 * math.sin(2 * math.pi * freq * i / rate))
            w.writeframes(struct.pack("<h", sample))
    return path


# --- system status ---
def test_system_status(session):
    r = session.get(f"{API}/system/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["brain"] == "online"
    assert d["llm_provider"] == "gemini-2.5-flash"
    assert d["tts_provider"] == "openai-tts-1"
    assert d["stt_provider"] == "whisper-1"
    assert "edge_agents_connected" in d


# --- chat send (non-streaming) ---
@pytest.fixture(scope="module")
def chat_send_result(session):
    payload = {"message": "Diga apenas: ok", "user_id": "owner"}
    r = session.post(f"{API}/chat/send", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "session_id" in d and isinstance(d["session_id"], str)
    assert "text" in d and len(d["text"]) > 0
    return d


def test_chat_send(chat_send_result):
    assert chat_send_result["text"]


# --- chat stream (SSE) ---
def test_chat_stream(session):
    payload = {"message": "Diga apenas: ok", "user_id": "owner"}
    deltas = 0
    done_text = None
    meta_seen = False
    with session.post(f"{API}/chat/stream", json=payload, stream=True, timeout=90) as r:
        assert r.status_code == 200
        buf = ""
        for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                evt, data = "message", ""
                for ln in block.split("\n"):
                    if ln.startswith("event:"):
                        evt = ln[6:].strip()
                    elif ln.startswith("data:"):
                        data += ln[5:].strip()
                if not data:
                    continue
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                if evt == "meta":
                    meta_seen = True
                    assert "session_id" in j
                elif evt == "delta":
                    deltas += 1
                elif evt == "done":
                    done_text = j.get("text", "")
                    break
            if done_text is not None:
                break
    assert meta_seen
    assert deltas >= 1, "no deltas received"
    assert done_text and len(done_text) > 0


# --- sessions list / messages ---
def test_sessions_list_and_messages(session, chat_send_result):
    r = session.get(f"{API}/chat/sessions", params={"user_id": "owner"}, timeout=15)
    assert r.status_code == 200
    sessions = r.json()
    assert isinstance(sessions, list) and len(sessions) >= 1
    sid = chat_send_result["session_id"]
    r2 = session.get(f"{API}/chat/messages/{sid}", timeout=15)
    assert r2.status_code == 200
    msgs = r2.json()
    assert isinstance(msgs, list)
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles


# --- TTS ---
def test_tts(session):
    payload = {"text": "Bom dia, Senhor.", "voice": "onyx"}
    r = session.post(f"{API}/tts", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    data = r.content
    assert len(data) > 100
    # MP3 frame sync 0xFFFB / 0xFFF3 / 0xFFF2 or ID3 header
    head = data[:3]
    assert head[:3] == b"ID3" or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0), f"Bad MP3 header: {head.hex()}"


# --- STT ---
def test_stt(session):
    path = _make_wav()
    with open(path, "rb") as f:
        files = {"file": ("t.wav", f, "audio/wav")}
        r = session.post(f"{API}/stt", files=files, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "text" in d  # may be empty for silence/tone


# --- Face register / profiles / auth ---
@pytest.fixture(scope="module")
def face_embedding():
    # deterministic 128-d
    return [((i * 0.01) % 1.0) for i in range(128)]


def test_face_register(session, face_embedding):
    r = session.post(f"{API}/face/register", json={
        "user_id": "owner", "name": "Felipe Stark", "embedding": face_embedding
    }, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["name"] == "Felipe Stark"


def test_face_profiles_list(session):
    r = session.get(f"{API}/face/profiles", timeout=15)
    assert r.status_code == 200
    profiles = r.json()
    assert any(p["user_id"] == "owner" for p in profiles)


def test_face_auth_match(session, face_embedding):
    r = session.post(f"{API}/face/auth", json={"embedding": face_embedding, "threshold": 0.6}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["authenticated"] is True
    assert d["name"] == "Felipe Stark"


def test_face_auth_nomatch(session, face_embedding):
    different = [v + 0.5 for v in face_embedding]
    r = session.post(f"{API}/face/auth", json={"embedding": different, "threshold": 0.6}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["authenticated"] is False


# --- Activation & morning report ---
def test_activation(session):
    r = session.post(f"{API}/activation", json={"user_id": "owner", "transcript": "Bom dia, Jarvis"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["greeting"]
    assert any(g in d["greeting"] for g in ("Bom dia", "Boa tarde", "Boa noite"))
    # morning_report should be present at least the first time today
    assert "first_today" in d


def test_morning_report(session):
    r = session.get(f"{API}/morning-report", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "weather" in d and "agenda" in d and "summary" in d
    assert isinstance(d["agenda"], list)


# --- Integrations ---
def test_weather(session):
    r = session.get(f"{API}/integrations/weather", params={"city": "Rio de Janeiro"}, timeout=20)
    assert r.status_code == 200
    d = r.json()
    # required schema
    for k in ("city", "temp_c", "feels_like_c", "humidity", "description", "wind_kmh", "source"):
        assert k in d, f"missing key {k}: {d}"
    assert d["source"] in ("google_weather_api", "mock")
    if d["source"] == "mock":
        assert "fallback_reason" in d


def test_calendar(session):
    r = session.get(f"{API}/integrations/calendar/today", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "date" in d and "events" in d
    assert isinstance(d["events"], list) and len(d["events"]) >= 1


# --- iteration 2: music (YouTube data API v3, graceful fallback) ---
def test_music_search(session):
    r = session.get(f"{API}/integrations/music/search", params={"q": "Iron Man"}, timeout=20)
    assert r.status_code == 200
    d = r.json()
    for k in ("query", "embed_url", "search_url", "watch_url", "source"):
        assert k in d, f"missing {k}: {d}"
    assert d["query"] == "Iron Man"
    assert d["source"] in ("youtube_data_api_v3", "fallback_search")
    if d["source"] == "fallback_search":
        assert d.get("video_id") is None


# --- iteration 2: Google OAuth login / status / disconnect ---
def test_google_login(session):
    r = session.get(f"{API}/auth/google/login", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "auth_url" in d and "state" in d
    assert "accounts.google.com" in d["auth_url"]


def test_google_disconnect_then_status(session):
    # Ensure clean state -> disconnect first
    r = session.post(f"{API}/auth/google/disconnect", timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True
    r2 = session.get(f"{API}/auth/google/status", timeout=15)
    assert r2.status_code == 200
    d = r2.json()
    assert d.get("connected") is False


# --- iteration 2: memory profile / compact / clear ---
def test_memory_profile_shape(session):
    r = session.get(f"{API}/memory/profile", params={"user_id": "owner"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("preferences", "people", "topics", "active_tasks", "summary"):
        assert k in d, f"missing key {k}: {d}"


def test_memory_compact_endpoint(session, chat_send_result):
    # chat_send_result fixture ensures at least one message exists
    r = session.post(f"{API}/memory/compact", params={"user_id": "owner"}, timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert "ok" in d
    assert "profile" in d
    # Verify GET profile shape after compact
    r2 = session.get(f"{API}/memory/profile", params={"user_id": "owner"}, timeout=15)
    assert r2.status_code == 200
    p = r2.json()
    for k in ("preferences", "people", "topics", "active_tasks", "summary"):
        assert k in p


def test_memory_clear(session):
    r = session.delete(f"{API}/memory/profile", params={"user_id": "owner"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True
