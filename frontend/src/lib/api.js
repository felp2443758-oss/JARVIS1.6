// API client helpers for the JARVIS dashboard.
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API });

/** Open an SSE stream against /api/chat/stream using fetch + ReadableStream
 *  Calls handlers with {sessionId}, {delta}, {text}, {error}.
 */
export async function streamChat({ message, sessionId, userId, lat, lng, onMeta, onDelta, onDone, onError }) {
  const ctrl = new AbortController();
  try {
    const resp = await fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId, user_id: userId || "owner", lat, lng }),
      signal: ctrl.signal,
    });
    if (!resp.ok || !resp.body) {
      onError && onError(`HTTP ${resp.status}`);
      return ctrl;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\n\n/);
      buffer = events.pop();
      for (const block of events) {
        if (!block.trim()) continue;
        const lines = block.split("\n");
        let evt = "message";
        let data = "";
        for (const ln of lines) {
          if (ln.startsWith("event:")) evt = ln.slice(6).trim();
          else if (ln.startsWith("data:")) data += ln.slice(5).trim();
        }
        try {
          const json = JSON.parse(data || "{}");
          if (evt === "meta") onMeta && onMeta(json);
          else if (evt === "delta") onDelta && onDelta(json.delta);
          else if (evt === "done") onDone && onDone(json);
          else if (evt === "error") onError && onError(json.error);
        } catch (_) { /* skip malformed sse */ }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") onError && onError(e.message);
  }
  return ctrl;
}

/** Fetches TTS for `text` and returns an HTMLAudioElement that's ready to play. */
export async function fetchTtsAudio(text, voice = "onyx") {
  const resp = await fetch(`${API}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice, speed: 1.05, model: "tts-1" }),
  });
  if (!resp.ok) throw new Error(`TTS HTTP ${resp.status}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio._jarvisUrl = url;
  return audio;
}

/** Chunked TTS player: queue sentences as they stream in from the LLM
 *  and play them back-to-back. Drastically reduces time-to-first-audio. */
export function createChunkedTtsPlayer({ voice = "onyx", onStart, onEnd } = {}) {
  let queue = [];           // queued (audio-promise or audio-element)
  let playing = false;
  let stopped = false;
  let buffer = "";          // partial text waiting for a sentence boundary
  let firstChunkSpoken = false;

  async function flushOne() {
    if (playing || queue.length === 0 || stopped) return;
    playing = true;
    if (!firstChunkSpoken) { firstChunkSpoken = true; onStart && onStart(); }
    const slot = queue.shift();
    try {
      const audio = await slot;
      if (stopped) return;
      await new Promise((resolve) => {
        audio.onended = () => { URL.revokeObjectURL(audio._jarvisUrl); resolve(); };
        audio.onerror = () => { URL.revokeObjectURL(audio._jarvisUrl); resolve(); };
        audio.play().catch(() => resolve());
      });
    } catch (_) { /* skip failed chunk */ }
    playing = false;
    if (queue.length > 0) flushOne();
    else if (stopped || isClosed) onEnd && onEnd();
  }

  let isClosed = false;

  function enqueueChunk(chunkText) {
    if (!chunkText || stopped) return;
    // Pre-fetch the audio in parallel (don't wait for current one to finish)
    queue.push(fetchTtsAudio(chunkText, voice));
    flushOne();
  }

  function feed(delta) {
    if (stopped) return;
    buffer += delta;
    // Sentence boundary: . ! ? ; \n followed by whitespace or end.
    const re = /([\s\S]*?[\.\!\?…]+|\n+)/;
    let m;
    while ((m = buffer.match(re))) {
      const sentence = m[0].trim();
      buffer = buffer.slice(m[0].length);
      if (sentence.length >= 3) enqueueChunk(sentence);
    }
    // Force-flush if buffer grows too large (rare)
    if (buffer.length > 200) { enqueueChunk(buffer.trim()); buffer = ""; }
  }

  function close() {
    isClosed = true;
    const tail = buffer.trim();
    buffer = "";
    if (tail) enqueueChunk(tail);
    // If nothing was queued at all, fire onEnd so caller can clean up.
    if (queue.length === 0 && !playing) onEnd && onEnd();
  }

  function stop() {
    stopped = true;
    queue = [];
  }

  return { feed, close, stop };
}

/** Simple non-chunked play (used for short greetings). */
export async function speak(text, voice = "onyx") {
  if (!text) return;
  try {
    const audio = await fetchTtsAudio(text, voice);
    await new Promise((res) => {
      audio.onended = () => { URL.revokeObjectURL(audio._jarvisUrl); res(); };
      audio.onerror = () => { URL.revokeObjectURL(audio._jarvisUrl); res(); };
      audio.play().catch(() => res());
    });
  } catch (_) { /* tts best-effort */ }
}

export async function transcribeAudio(blob) {
  const form = new FormData();
  form.append("file", blob, "speech.webm");
  const resp = await fetch(`${API}/stt`, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`STT failed (${resp.status})`);
  const data = await resp.json();
  return data.text;
}

// Detect a "play music X" command in Portuguese and return the search term, or null.
export function detectMusicCommand(text) {
  if (!text) return null;
  const t = text.toLowerCase();
  // Tocar / coloque / coloca / toca a música X / coloca X no youtube
  const patterns = [
    /(?:toque|toca|tocar|colo[qc]ue?|colo[qc]a)\s+(?:a\s+)?(?:m[úu]sica\s+)?(?:do\s+|da\s+|de\s+)?(.+?)(?:\s+no\s+(?:youtube|spotify))?$/i,
    /(?:play|put on)\s+(.+)/i,
  ];
  for (const re of patterns) {
    const m = text.match(re);
    if (m && m[1] && m[1].length >= 2) return m[1].replace(/[.?!]+$/, "").trim();
  }
  if (/\b(youtube|música|musica|song|track)\b/.test(t)) return text.replace(/^.*?(youtube|música|musica)\s*/i, "").trim() || null;
  return null;
}

// ============ Edge Agent Tools ============
export async function webSearch(query, { deep = false, maxResults = 6 } = {}) {
  const r = await api.post("/agent/search", { query, deep, max_results: maxResults });
  return r.data;
}

export async function imageSearchWeb(query, maxResults = 8) {
  const r = await api.post("/agent/image-search", { query, max_results: maxResults });
  return r.data;
}

export async function analyzeImageUrl(url, question) {
  const r = await api.post("/agent/vision/url", { url, question });
  return r.data;
}

export async function analyzeImageUpload(file, question) {
  const form = new FormData();
  form.append("file", file);
  const url = question ? `${API}/agent/vision/upload?question=${encodeURIComponent(question)}` : `${API}/agent/vision/upload`;
  const resp = await fetch(url, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`Vision HTTP ${resp.status}`);
  return await resp.json();
}

export async function convertFileUpload(file, question) {
  const form = new FormData();
  form.append("file", file);
  const url = question ? `${API}/agent/files/convert?question=${encodeURIComponent(question)}` : `${API}/agent/files/convert`;
  const resp = await fetch(url, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`Convert HTTP ${resp.status}`);
  return await resp.json();
}

export async function generateImage(prompt, { provider = "gpt-image", n = 1, size = "1024x1024" } = {}) {
  const r = await api.post("/agent/image/generate", { prompt, provider, n, size }, { timeout: 120000 });
  return r.data;
}

export async function generateVideo(prompt, { model = "veo3-fast", duration = 8, aspect_ratio = "16:9" } = {}) {
  const r = await api.post("/agent/video/generate", { prompt, model, duration, aspect_ratio }, { timeout: 300000 });
  return r.data;
}

export async function getToolHistory(type, limit = 30) {
  const r = await api.get("/agent/history", { params: { type, limit } });
  return r.data;
}
export async function deleteToolHistoryItem(id) {
  const r = await api.delete(`/agent/history/${id}`);
  return r.data;
}
export async function clearToolHistory(type) {
  const r = await api.delete("/agent/history", { params: { type } });
  return r.data;
}

/** Build a stable URL to a GridFS-stored image asset (image_gen history). */
export function toolAssetUrl(assetId) {
  if (!assetId) return null;
  return `${API}/agent/history/asset/${assetId}`;
}

// ============ Geolocation helper ============
export function getBrowserLocation(timeoutMs = 5000) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    const t = setTimeout(() => resolve(null), timeoutMs);
    navigator.geolocation.getCurrentPosition(
      (pos) => { clearTimeout(t); resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }); },
      () => { clearTimeout(t); resolve(null); },
      { timeout: timeoutMs, maximumAge: 600000, enableHighAccuracy: false },
    );
  });
}

