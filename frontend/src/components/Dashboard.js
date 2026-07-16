import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, MicOff, Radio, Sun, Moon, Sunrise, ScanFace, Activity, Cpu, Cloud, Calendar, Music2, Globe, Power, Eye, Wifi, WifiOff, Brain, Link2, X, Youtube, Search, Image as ImageIcon, FileText, Sparkles, MapPin, Hammer } from "lucide-react";
import { api, streamChat, speak, transcribeAudio, createChunkedTtsPlayer, detectMusicCommand, API, getBrowserLocation } from "@/lib/api";
import EdgeConsole from "@/components/EdgeConsole";
import BuilderWorkspace from "@/components/BuilderWorkspace";
import CredentialVault from "@/components/CredentialVault";
import OperatorPanel from "@/components/OperatorPanel";
import { logout } from "@/lib/auth";
import { KeyRound, Terminal, LogOut } from "lucide-react";

// ============ small helpers ============
function partOfDay() {
  const h = new Date().getHours();
  if (h < 12) return { label: "Bom dia", icon: Sunrise };
  if (h < 18) return { label: "Boa tarde", icon: Sun };
  return { label: "Boa noite", icon: Moon };
}

// ============ ArcReactor ============
function ArcReactor({ state = "idle" }) {
  // state: idle | listening | speaking
  return (
    <div className={`arc-reactor ${state}`} data-testid="arc-reactor">
      <div className="arc-ring outer" />
      <div className="arc-ring mid" />
      <div className="arc-ring inner" />
      <div className="arc-core" />
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="text-center">
          <div className="font-heading text-white/90 tracking-[0.4em] text-xs">J.A.R.V.I.S.</div>
          <div className="font-data text-cyan-300 text-[10px] mt-1 uppercase">
            {state === "listening" ? "Ouvindo" : state === "speaking" ? "Falando" : "Standby"}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Waveform ============
function Waveform({ active }) {
  const bars = 18;
  return (
    <div className={`waveform ${active ? "" : "idle"}`} data-testid="voice-waveform">
      {Array.from({ length: bars }).map((_, i) => (
        <div key={i} className="bar" style={{ animationDelay: `${(i % 6) * 80}ms` }} />
      ))}
    </div>
  );
}

// ============ SystemStatus ============
function StatusRow({ ok, label, testid, IconOn, IconOff }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-cyan-500/10 last:border-b-0">
      <div className="flex items-center gap-2 text-slate-300">
        {ok ? <IconOn size={14} className="text-cyan-300" /> : <IconOff size={14} className="text-slate-500" />}
        <span className="font-data uppercase text-xs tracking-widest">{label}</span>
      </div>
      <div className="flex items-center gap-2" data-testid={testid}>
        <span className={`pulse-dot ${ok ? "" : "off"}`} />
        <span className={`text-[10px] font-data uppercase ${ok ? "text-emerald-300" : "text-slate-500"}`}>{ok ? "Online" : "Offline"}</span>
      </div>
    </div>
  );
}

function SystemStatus({ brainOnline, edgeConnected, micOk, camOk }) {
  return (
    <div className="hud-panel h-full" data-testid="system-status-panel">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between shrink-0">
        <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">Sistema</h3>
        <Activity size={14} className="text-cyan-400" />
      </div>
      <div className="hud-body px-4 pb-4">
        <StatusRow ok={brainOnline} label="Brain (Cloud)" testid="status-brain" IconOn={Cpu} IconOff={Cpu} />
        <StatusRow ok={edgeConnected} label="Edge Agent" testid="status-edge" IconOn={Wifi} IconOff={WifiOff} />
        <StatusRow ok={micOk} label="Microfone" testid="status-mic" IconOn={Mic} IconOff={MicOff} />
        <StatusRow ok={camOk} label="Câmera" testid="status-cam" IconOn={Eye} IconOff={Eye} />

        <div className="mt-4 grid grid-cols-2 gap-2 text-[10px] font-data">
          <div className="border border-cyan-500/20 rounded p-2">
            <div className="text-cyan-400 uppercase tracking-widest">LLM</div>
            <div className="text-white mt-0.5">Gemini 2.5 Flash</div>
          </div>
          <div className="border border-cyan-500/20 rounded p-2">
            <div className="text-cyan-400 uppercase tracking-widest">Voz</div>
            <div className="text-white mt-0.5">OpenAI tts-1</div>
          </div>
          <div className="border border-cyan-500/20 rounded p-2">
            <div className="text-cyan-400 uppercase tracking-widest">STT</div>
            <div className="text-white mt-0.5">Whisper-1</div>
          </div>
          <div className="border border-cyan-500/20 rounded p-2">
            <div className="text-cyan-400 uppercase tracking-widest">UTC</div>
            <div className="text-white mt-0.5">{new Date().toUTCString().slice(17, 25)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Morning Report ============
function MorningReport({ data }) {
  return (
    <div className="hud-panel h-full relative" data-testid="morning-report-panel">
      <div className="scanline" />
      <div className="px-4 pt-4 pb-2 flex items-center justify-between shrink-0">
        <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">Relatório</h3>
        <Sun size={14} className="text-cyan-400" />
      </div>
      <div className="hud-body px-4 pb-4">
        {!data && <div className="text-slate-400 text-xs font-data">Aguardando dados…</div>}
        {data && (
          <div className="space-y-3">
            <div className="flex items-center gap-3 border border-cyan-500/20 rounded p-3 bg-cyan-500/5">
              <Cloud className="text-cyan-300" size={28} />
              <div>
                <div className="font-heading text-xl text-white">{data.weather.temp_c}°C</div>
                <div className="text-[11px] font-data text-slate-300 capitalize">{data.weather.description}</div>
                <div className="text-[10px] font-data text-cyan-400 uppercase tracking-widest">{data.weather.city}</div>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 text-cyan-300 mb-1">
                <Calendar size={12} />
                <span className="text-[10px] font-data uppercase tracking-widest">Agenda Hoje</span>
              </div>
              <ul className="space-y-1.5 pr-1" data-testid="morning-agenda">
                {data.agenda.map((ev, i) => (
                  <li key={i} className="text-xs font-data text-slate-200 flex gap-2">
                    <span className="text-cyan-400 w-12 shrink-0">{ev.time}</span>
                    <span className="truncate">{ev.title}</span>
                  </li>
                ))}
                {data.agenda.length === 0 && (
                  <li className="text-[11px] font-data text-cyan-700 italic">{data.calendar_connected ? "Sem compromissos." : "Conecte o Google Calendar."}</li>
                )}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============ FaceID Panel ============
function FaceIDPanel({ profile, onRegister, onAuth, status }) {
  const videoRef = useRef(null);
  const [streaming, setStreaming] = useState(false);
  const [name, setName] = useState("Felipe Stark");

  async function startCam() {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
      if (videoRef.current) videoRef.current.srcObject = s;
      setStreaming(true);
    } catch (_) { setStreaming(false); }
  }
  function stopCam() {
    const v = videoRef.current; if (v && v.srcObject) { v.srcObject.getTracks().forEach(t => t.stop()); v.srcObject = null; }
    setStreaming(false);
  }

  async function snapshotEmbedding() {
    // Lightweight pseudo-embedding from current frame pixel data (no face_recognition in browser).
    // The Edge Agent provides real face_recognition embeddings; here we just produce a stable
    // 128-d vector from the frame so the cloud-side flow can be demonstrated end-to-end.
    const v = videoRef.current;
    if (!v) return null;
    const c = document.createElement("canvas");
    c.width = 160; c.height = 120;
    const ctx = c.getContext("2d");
    ctx.drawImage(v, 0, 0, c.width, c.height);
    const data = ctx.getImageData(0, 0, c.width, c.height).data;
    const vec = new Array(128).fill(0);
    for (let i = 0; i < data.length; i += 4) {
      const idx = i % 128;
      vec[idx] += (data[i] * 0.3 + data[i + 1] * 0.59 + data[i + 2] * 0.11) / 255;
    }
    const len = data.length / 4;
    return vec.map(x => x / (len / 128));
  }

  return (
    <div className="hud-panel h-full relative" data-testid="faceid-panel">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between shrink-0">
        <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">Identificação</h3>
        <ScanFace size={14} className="text-cyan-400" />
      </div>
      <div className="hud-body px-4 pb-4">
        <div className="relative w-full aspect-[4/3] border border-cyan-500/30 rounded overflow-hidden bg-black/60 mb-3">
          {streaming ? (
            <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" data-testid="faceid-video" />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-[10px] font-data uppercase tracking-widest">Câmera Inativa</div>
          )}
          <div className="scanline" />
          <div className="absolute inset-0 pointer-events-none border border-cyan-500/20 m-3 rounded" />
          <div className="absolute top-2 left-2 text-[9px] font-data text-cyan-300/70 uppercase tracking-widest">{status || "STANDBY"}</div>
        </div>
        <div className="space-y-2">
          <input
            value={name} onChange={e => setName(e.target.value)}
            className="w-full bg-black/40 border border-cyan-500/30 rounded px-2 py-1 text-xs text-cyan-100 font-data outline-none focus:border-cyan-400"
            data-testid="faceid-name-input"
            placeholder="Nome do proprietário"
          />
          <div className="grid grid-cols-2 gap-2">
            {!streaming ? (
              <button className="glass-btn" onClick={startCam} data-testid="faceid-start-cam">Ativar Cam</button>
            ) : (
              <button className="glass-btn danger" onClick={stopCam} data-testid="faceid-stop-cam">Parar</button>
            )}
            <button
              className="glass-btn" disabled={!streaming}
              onClick={async () => { const v = await snapshotEmbedding(); if (v) onRegister(name, v); }}
              data-testid="faceid-register"
            >Registrar</button>
            <button
              className="glass-btn col-span-2" disabled={!streaming}
              onClick={async () => { const v = await snapshotEmbedding(); if (v) onAuth(v); }}
              data-testid="faceid-auth"
            >Autenticar Rosto</button>
          </div>
          {profile && (
            <div className="text-[11px] font-data text-emerald-300 text-center pt-1" data-testid="faceid-current-profile">
              Proprietário: <span className="text-white">{profile.name}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============ Transcript ============
function Transcript({ messages, streamingText }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages, streamingText]);
  return (
    <div className="hud-panel h-full" data-testid="transcript-panel">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between shrink-0">
        <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">Transcrição</h3>
        <Radio size={14} className="text-cyan-400" />
      </div>
      <div ref={ref} className="hud-body px-4 pb-4 space-y-2" data-testid="transcript-messages">
        {messages.length === 0 && !streamingText && (
          <div className="text-slate-500 text-xs font-data">
            <span className="text-cyan-400">$</span> aguardando comando do operador…<span className="caret" />
          </div>
        )}
        {messages.map((m, i) => (
          <div key={m.id ?? `${m.role}-${m.ts ?? i}-${i}`} className="term-line text-xs font-data leading-relaxed">
            <span className={`mr-2 ${m.role === "user" ? "text-cyan-400" : "text-emerald-300"}`}>
              {m.role === "user" ? "USR>" : "JVS>"}
            </span>
            <span className="text-slate-200 whitespace-pre-wrap">{m.content}</span>
            {m.linkUrl && (
              <a
                href={m.linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 inline-flex items-center gap-1 text-cyan-300 hover:text-cyan-100 underline-offset-2 hover:underline"
                data-testid="chat-open-link"
              >
                <Link2 size={12} /> {m.linkLabel || "Abrir"}
              </a>
            )}
          </div>
        ))}
        {streamingText ? (
          <div key="__stream__" className="text-xs font-data leading-relaxed">
            <span className="mr-2 text-emerald-300">JVS&gt;</span>
            <span className="text-slate-100 whitespace-pre-wrap">{streamingText}</span>
            <span className="caret" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ============ QuickActions ============
function QuickActions({ onAction, onMusic, googleConnected, onConnectGoogle, onShowMemory, onShowConsole, onShowBuilder, onShowVault, onShowOperator }) {
  const actions = [
    { id: "weather", label: "Clima", icon: Cloud, prompt: "Qual o clima atual aqui?" },
    { id: "agenda", label: "Agenda", icon: Calendar, prompt: "Me mostre minha agenda de hoje." },
  ];
  return (
    <div className="hud-panel h-full" data-testid="quick-actions-panel">
      <div className="px-4 pt-4 pb-2 flex items-center justify-between shrink-0">
        <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">Ações Rápidas</h3>
        <Power size={14} className="text-cyan-400" />
      </div>
      <div className="hud-body px-4 pb-4">
        <div className="grid grid-cols-2 gap-2">
          {actions.map(a => (
            <button
              key={a.id}
              data-testid={`quick-action-${a.id}`}
              className="glass-btn justify-start"
              onClick={() => onAction(a.prompt)}
            >
              <a.icon size={14} /> {a.label}
            </button>
          ))}
          <button
            data-testid="quick-action-builder"
            className="glass-btn justify-start col-span-2"
            onClick={onShowBuilder}
            title="Builder Mode — construa apps via chat"
            style={{ borderColor: "rgba(0, 255, 157, 0.5)", color: "#00FF9D" }}
          >
            <Hammer size={14} /> Builder Mode
          </button>
          <button
            data-testid="quick-action-console"
            className="glass-btn justify-start col-span-2"
            onClick={onShowConsole}
            title="Edge Agent: pesquisa, visão, arquivos"
          >
            <Sparkles size={14} /> Edge Console
          </button>
          <button
            data-testid="quick-action-music"
            className="glass-btn justify-start"
            onClick={() => onMusic()}
          >
            <Youtube size={14} /> Música
          </button>
          <button
            data-testid="quick-action-memory"
            className="glass-btn justify-start"
            onClick={onShowMemory}
          >
            <Brain size={14} /> Memória
          </button>
          <button
            data-testid="quick-action-operator"
            className="glass-btn justify-start col-span-2"
            onClick={onShowOperator}
            title="Operador Remoto — controle seu PC via Edge Agent"
            style={{ borderColor: "rgba(56, 189, 248, 0.5)", color: "#7dd3fc" }}
          >
            <Terminal size={14} /> Operador Remoto
          </button>
          <button
            data-testid="quick-action-vault"
            className="glass-btn justify-start col-span-2"
            onClick={onShowVault}
            title="Cofre de credenciais de sites"
          >
            <KeyRound size={14} /> Cofre de Credenciais
          </button>
          <button
            data-testid="quick-action-google"
            className="glass-btn justify-start col-span-2"
            onClick={onConnectGoogle}
            title={googleConnected ? "Google Calendar conectado" : "Conectar Google Calendar"}
          >
            <Link2 size={14} /> {googleConnected ? "Google Calendar ✓" : "Conectar Google Calendar"}
          </button>
        </div>
        <div className="mt-4 border-t border-cyan-500/10 pt-3">
          <div className="text-[10px] font-data uppercase text-cyan-400 tracking-widest mb-1">Wake Words</div>
          <div className="space-y-1 text-[11px] font-data text-slate-300">
            <div>• {`"Bom dia, Jarvis"`}</div>
            <div>• {`"Boa tarde, Jarvis"`}</div>
            <div>• {`"Boa noite, Jarvis"`}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Music Player Modal (YouTube) ============
function MusicPlayer({ initialQuery, onClose }) {
  const [query, setQuery] = useState(initialQuery || "");
  const [embedUrl, setEmbedUrl] = useState(null);
  const [searchUrl, setSearchUrl] = useState(null);
  const [meta, setMeta] = useState({ title: null, channel: null, source: null });
  const [loading, setLoading] = useState(false);

  async function play(q) {
    if (!q || !q.trim()) return;
    setLoading(true);
    try {
      const r = await api.get("/integrations/music/search", { params: { q } });
      setMeta({ title: r.data.title, channel: r.data.channel, source: r.data.source });
      setSearchUrl(r.data.search_url || null);
      if (r.data.video_id) {
        setEmbedUrl(r.data.embed_url);
      } else {
        // Fallback: open YouTube search in a new tab automatically.
        setEmbedUrl(null);
        window.open(r.data.search_url, "_blank", "noopener");
      }
    } catch (_) { /* keep prev */ }
    setLoading(false);
  }

  useEffect(() => { if (initialQuery) play(initialQuery); }, [initialQuery]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur" data-testid="music-modal">
      <div className="hud-panel w-[720px] max-w-[95vw] p-5 relative">
        <button className="absolute top-3 right-3 text-cyan-300 hover:text-white" onClick={onClose} data-testid="music-close">
          <X size={18} />
        </button>
        <div className="flex items-center gap-2 mb-4">
          <Youtube className="text-red-400" size={20} />
          <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-sm">Player de Música</h3>
        </div>
        <div className="flex gap-2 mb-4">
          <input
            value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && play(query)}
            className="flex-1 bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
            placeholder="Buscar música ou artista…"
            data-testid="music-query"
          />
          <button className="glass-btn" onClick={() => play(query)} data-testid="music-play">
            {loading ? "…" : "Tocar"}
          </button>
        </div>
        <div className="aspect-video bg-black/60 border border-cyan-500/20 rounded overflow-hidden">
          {embedUrl ? (
            <iframe
              key={embedUrl}
              src={embedUrl}
              title="YouTube player"
              className="w-full h-full"
              allow="autoplay; encrypted-media"
              allowFullScreen
              data-testid="music-iframe"
            />
          ) : searchUrl ? (
            <div className="flex flex-col h-full items-center justify-center text-center text-cyan-200 text-xs font-data gap-3 p-6" data-testid="music-fallback">
              <Youtube className="text-red-400" size={40} />
              <div>Abri a busca do YouTube em uma nova aba.</div>
              <div className="text-cyan-700">
                Para tocar dentro do painel, habilite a <span className="text-cyan-300">YouTube Data API v3</span> em<br />
                <span className="text-cyan-400">console.developers.google.com/apis/api/youtube.googleapis.com</span>
              </div>
              <a href={searchUrl} target="_blank" rel="noopener noreferrer" className="glass-btn" data-testid="music-open-tab">
                Abrir no YouTube
              </a>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-cyan-700 text-xs font-data uppercase tracking-widest">
              Digite uma música e pressione Tocar
            </div>
          )}
        </div>
        {meta.title && (
          <div className="mt-2 text-[11px] font-data text-cyan-200" data-testid="music-meta">
            <span className="text-cyan-400 uppercase tracking-widest">Tocando:</span> {meta.title} <span className="text-cyan-700">— {meta.channel}</span>
          </div>
        )}
        <div className="mt-3 text-[10px] font-data text-cyan-700 uppercase tracking-widest text-center">
          Powered by YouTube • Comandos: {`"Toque X"`}, {`"Coloca a música Y"`}
        </div>
      </div>
    </div>
  );
}

// ============ Memory Profile Modal ============
function MemoryPanel({ onClose }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const r = await api.get("/memory/profile", { params: { user_id: "owner" } });
      setProfile(r.data);
    } catch (_) { /* ignore */ }
    setLoading(false);
  }
  async function recompact() {
    setLoading(true);
    try {
      const r = await api.post("/memory/compact", null, { params: { user_id: "owner" } });
      if (r.data?.profile) setProfile(r.data.profile);
    } catch (_) { /* ignore */ }
    setLoading(false);
  }
  async function clearMem() {
    if (!window.confirm("Apagar perfil persistente do operador?")) return;
    try { await api.delete("/memory/profile", { params: { user_id: "owner" } }); await load(); } catch (_) { /* ignore */ }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur" data-testid="memory-modal">
      <div className="hud-panel w-[640px] max-w-[95vw] p-5 relative">
        <button className="absolute top-3 right-3 text-cyan-300 hover:text-white" onClick={onClose} data-testid="memory-close">
          <X size={18} />
        </button>
        <div className="flex items-center gap-2 mb-3">
          <Brain className="text-cyan-300" size={20} />
          <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-sm">Perfil Cognitivo</h3>
        </div>
        {loading && <div className="text-slate-400 text-xs font-data">Sincronizando memória de longo prazo…</div>}
        {!loading && profile && (
          <div className="space-y-3 text-xs font-data text-slate-200" data-testid="memory-content">
            <div>
              <div className="text-cyan-400 uppercase tracking-widest text-[10px] mb-1">Resumo</div>
              <div className="text-white">{profile.summary || "(perfil ainda em formação — converse mais com o JARVIS)"}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-cyan-400 uppercase tracking-widest text-[10px] mb-1">Preferências</div>
                <ul className="space-y-1">{(profile.preferences || []).map((p, i) => <li key={i}>• {p}</li>)}{(profile.preferences||[]).length===0 && <li className="text-slate-500">—</li>}</ul>
              </div>
              <div>
                <div className="text-cyan-400 uppercase tracking-widest text-[10px] mb-1">Tópicos Recorrentes</div>
                <ul className="space-y-1">{(profile.topics || []).map((p, i) => <li key={i}>• {p}</li>)}{(profile.topics||[]).length===0 && <li className="text-slate-500">—</li>}</ul>
              </div>
              <div>
                <div className="text-cyan-400 uppercase tracking-widest text-[10px] mb-1">Pessoas</div>
                <ul className="space-y-1">{(profile.people || []).map((p, i) => <li key={i}>• <span className="text-white">{p.name}</span> <span className="text-cyan-700">({p.relation})</span></li>)}{(profile.people||[]).length===0 && <li className="text-slate-500">—</li>}</ul>
              </div>
              <div>
                <div className="text-cyan-400 uppercase tracking-widest text-[10px] mb-1">Tarefas Ativas</div>
                <ul className="space-y-1">{(profile.active_tasks || []).map((p, i) => <li key={i}>• {p}</li>)}{(profile.active_tasks||[]).length===0 && <li className="text-slate-500">—</li>}</ul>
              </div>
            </div>
          </div>
        )}
        <div className="mt-4 flex gap-2">
          <button className="glass-btn" onClick={recompact} data-testid="memory-recompact">Atualizar Memória</button>
          <button className="glass-btn danger" onClick={clearMem} data-testid="memory-clear">Apagar Perfil</button>
        </div>
        <div className="mt-2 text-[10px] font-data text-cyan-700 uppercase tracking-widest">
          A memória é atualizada automaticamente a cada 6 turnos da conversa.
        </div>
      </div>
    </div>
  );
}

// ============ Recording hook (MediaRecorder + STT) ============
function useVoiceRecorder() {
  const [recording, setRecording] = useState(false);
  const [supported, setSupported] = useState(true);
  const mrRef = useRef(null);
  const chunksRef = useRef([]);
  const startedAtRef = useRef(0);

  useEffect(() => {
    setSupported(!!(navigator.mediaDevices && window.MediaRecorder));
  }, []);

  async function start() {
    chunksRef.current = [];
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
    mr.start();
    mrRef.current = mr;
    startedAtRef.current = performance.now();
    setRecording(true);
  }
  async function stop() {
    return new Promise((resolve) => {
      const mr = mrRef.current;
      if (!mr) return resolve(null);
      mr.onstop = () => {
        const durationMs = performance.now() - startedAtRef.current;
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        try { mr.stream.getTracks().forEach(t => t.stop()); } catch (_) {}
        setRecording(false);
        // Attach duration to blob for callers
        blob._durationMs = durationMs;
        resolve(blob);
      };
      try { mr.stop(); } catch (_) { resolve(null); }
    });
  }
  return { recording, supported, start, stop };
}

// ============ Dashboard ============
export default function Dashboard({ user }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState("");
  const [reactorState, setReactorState] = useState("idle");
  const [textInput, setTextInput] = useState("");
  const [brainOnline, setBrainOnline] = useState(false);
  const [edgeConnected, setEdgeConnected] = useState(false);
  const [profile, setProfile] = useState(null);
  const [morning, setMorning] = useState(null);
  const [authStatus, setAuthStatus] = useState("STANDBY");
  const [micOk, setMicOk] = useState(false);
  const [camOk, setCamOk] = useState(false);
  const [activated, setActivated] = useState(false);
  const [musicOpen, setMusicOpen] = useState(false);
  const [musicQuery, setMusicQuery] = useState("");
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [consoleInitial, setConsoleInitial] = useState(null); // {tab, prompt, autoRun, ...}
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderInitial, setBuilderInitial] = useState(null); // {prompt, autoCreate}
  const [googleConnected, setGoogleConnected] = useState(false);
  const [coords, setCoords] = useState(null); // { lat, lng } from browser geolocation
  const [vaultOpen, setVaultOpen] = useState(false);
  const [operatorOpen, setOperatorOpen] = useState(false);
  const recorder = useVoiceRecorder();
  const wsRef = useRef(null);

  const part = useMemo(() => partOfDay(), []);
  const PartIcon = part.icon;

  // initial health + profile + dashboard ws + permission probe
  useEffect(() => {
    (async () => {
      try {
        const s = await api.get("/system/status");
        setBrainOnline(s.data.brain === "online");
        setEdgeConnected((s.data.edge_agents_connected || 0) > 0);
      } catch (_) { setBrainOnline(false); }
      try {
        const p = await api.get("/face/profiles");
        if (p.data && p.data.length > 0) setProfile(p.data[0]);
      } catch (_) { /* no profile yet */ }
      // probe permissions (non-blocking)
      try {
        const mic = await navigator.permissions.query({ name: "microphone" });
        setMicOk(mic.state !== "denied");
      } catch (_) { setMicOk(true); }
      try {
        const cam = await navigator.permissions.query({ name: "camera" });
        setCamOk(cam.state !== "denied");
      } catch (_) { setCamOk(true); }
      // Google connect status
      try {
        const g = await api.get("/auth/google/status");
        setGoogleConnected(!!g.data.connected);
      } catch (_) { /* ignore */ }
      // Browser geolocation (non-blocking; falls back to Belo Horizonte server-side)
      try {
        const c = await getBrowserLocation(4000);
        if (c) setCoords(c);
      } catch (_) { /* ignore */ }
    })();
    // Detect ?google=connected from OAuth callback
    if (window.location.search.includes("google=connected")) {
      setGoogleConnected(true);
      window.history.replaceState({}, "", window.location.pathname);
    }
    // Dashboard WS
    try {
      const wsUrl = (process.env.REACT_APP_BACKEND_URL || "").replace(/^http/, "ws") + "/api/ws/dashboard";
      const ws = new WebSocket(wsUrl);
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === "agent_status") setEdgeConnected(true);
          if (data.type === "transcript" && data.text) {
            setMessages((prev) => [...prev, { role: data.role || "user", content: data.text }]);
          }
        } catch (_) { /* ignore bad frames */ }
      };
      ws.onclose = () => { /* keep silent */ };
      wsRef.current = ws;
    } catch (_) { /* dashboard ws optional */ }
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);

  async function activate() {
    setReactorState("speaking");
    try {
      const resp = await api.post("/activation", {
        user_id: profile?.user_id || "owner",
        transcript: `${part.label}, Jarvis`,
        lat: coords?.lat, lng: coords?.lng,
      });
      const greeting = resp.data.greeting;
      setMessages((prev) => [...prev, { role: "assistant", content: greeting }]);
      if (resp.data.morning_report) {
        setMorning(resp.data.morning_report);
        setMessages((prev) => [...prev, { role: "assistant", content: resp.data.morning_report.summary }]);
      } else {
        try {
          const m = await api.get("/morning-report", { params: { user_id: profile?.user_id || "owner", lat: coords?.lat, lng: coords?.lng } });
          setMorning(m.data);
        } catch (_) { /* no morning report */ }
      }
      setActivated(true);
      const full = (resp.data.morning_report?.summary ? `${greeting} ${resp.data.morning_report.summary}` : greeting);
      await speak(full);
    } catch (e) {
      console.error("activation error", e);
    }
    setReactorState("idle");
  }

  async function sendMessage(text) {
    if (!text || !text.trim()) return;
    // Intercept music commands → open the YouTube player directly
    const musicQ = detectMusicCommand(text);
    if (musicQ) {
      setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: `Tocando "${musicQ}" no YouTube.` }]);
      setMusicQuery(musicQ);
      setMusicOpen(true);
      // Optional brief vocal confirmation
      speak(`Tocando ${musicQ}.`);
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setStreaming("");
    setReactorState("listening");
    let acc = "";
    const player = createChunkedTtsPlayer({
      voice: "onyx",
      onStart: () => setReactorState("speaking"),
      onEnd: () => setReactorState("idle"),
    });
    await streamChat({
      message: text,
      sessionId,
      lat: coords?.lat, lng: coords?.lng,
      onMeta: ({ session_id, actions }) => {
        setSessionId(session_id);
        // Auto-execute high-level actions via Edge Console / Builder / Browser (visual feedback)
        if (Array.isArray(actions) && actions.length > 0) {
          const a = actions[0];
          if (a.type === "open_url") {
            // Try to open in a new tab synchronously (same user-gesture chain).
            // If the popup is blocked, append a clickable fallback link to the chat.
            let opened = null;
            try { opened = window.open(a.url, "_blank", "noopener,noreferrer"); } catch (_) { opened = null; }
            if (!opened) {
              setMessages((prev) => [...prev, {
                role: "assistant",
                content: `🔗 ${a.label || a.url}`,
                linkUrl: a.url,
                linkLabel: a.label || a.url,
              }]);
            }
            return;
          }
          if (a.type === "build_site") {
            // Open Builder Mode and auto-create a project from the prompt
            setBuilderInitial({ prompt: a.prompt || a.raw || "", autoCreate: true });
            setBuilderOpen(true);
            return;
          }
          const map = {
            generate_image: { tab: "genimg", autoRun: true, prompt: a.prompt, provider: a.provider || "gpt-image" },
            generate_video: { tab: "genvid", autoRun: true, prompt: a.prompt, model: a.model || "veo3-fast" },
            image_search: { tab: "images", autoRun: true, query: a.query },
            web_search: { tab: "search", autoRun: true, query: a.query },
          };
          const init = map[a.type];
          if (init) {
            setConsoleInitial(init);
            setConsoleOpen(true);
          }
        }
      },
      onDelta: (d) => { acc += d; setStreaming(acc); player.feed(d); },
      onDone: ({ text: full }) => {
        setMessages((prev) => [...prev, { role: "assistant", content: full || acc }]);
        setStreaming("");
        player.close();
      },
      onError: (err) => {
        console.error("stream error", err);
        setStreaming("");
        player.stop();
        setReactorState("idle");
      },
    });
  }

  async function handleVoicePress() {
    if (recorder.recording) {
      setReactorState("idle");
      let blob = null;
      try { blob = await recorder.stop(); } catch (e) { console.warn("stop error", e); }
      if (!blob) return;
      // Guard: reject audio shorter than ~600ms (Whisper hallucinates on silence)
      const durMs = blob._durationMs || 0;
      if (durMs < 600 || blob.size < 4096) {
        console.info(`[voice] audio muito curto (${Math.round(durMs)}ms, ${blob.size}B) — ignorando`);
        return;
      }
      try {
        const text = await transcribeAudio(blob);
        if (!text || !text.trim()) {
          console.info("[voice] transcrição vazia ou filtrada (silêncio/ruído)");
          return;
        }
        const t = text.toLowerCase();
        if (!activated && /(bom dia|boa tarde|boa noite).*jarvis/.test(t)) {
          await activate();
          return;
        }
        await sendMessage(text);
      } catch (e) {
        console.error("[voice] erro:", e);
      }
    } else {
      try {
        await recorder.start();
        setReactorState("listening");
      } catch (e) {
        console.error("[voice] start error:", e);
        alert("Não foi possível acessar o microfone. Verifique as permissões.");
      }
    }
  }

  async function registerFace(name, embedding) {
    try {
      const r = await api.post("/face/register", { user_id: "owner", name, embedding });
      setProfile({ user_id: r.data.user_id, name: r.data.name });
      setAuthStatus("REGISTRADO");
      setTimeout(() => setAuthStatus("STANDBY"), 1500);
    } catch (e) {
      setAuthStatus("ERRO");
    }
  }

  async function authenticateFace(embedding) {
    try {
      const r = await api.post("/face/auth", { embedding, threshold: 0.8 });
      if (r.data.authenticated) {
        setAuthStatus(`ACESSO OK: ${r.data.name}`);
        setTimeout(() => setAuthStatus("STANDBY"), 1800);
      } else {
        setAuthStatus("ACESSO NEGADO");
        setTimeout(() => setAuthStatus("STANDBY"), 1800);
      }
    } catch (_) {
      setAuthStatus("ERRO");
    }
  }

  async function connectGoogle() {
    try {
      const r = await api.get("/auth/google/login");
      if (r.data?.auth_url) {
        window.location.href = r.data.auth_url;
      }
    } catch (_) { /* ignore */ }
  }

  return (
    <div className="h-full w-full hex-accent" data-testid="dashboard-root">
      {musicOpen && <MusicPlayer initialQuery={musicQuery} onClose={() => setMusicOpen(false)} />}
      {memoryOpen && <MemoryPanel onClose={() => setMemoryOpen(false)} />}
      {consoleOpen && (
        <EdgeConsole
          initial={consoleInitial}
          onClose={() => { setConsoleOpen(false); setConsoleInitial(null); }}
          onSendToChat={(t) => { setConsoleOpen(false); setConsoleInitial(null); sendMessage(t); }}
        />
      )}
      {builderOpen && <BuilderWorkspace initial={builderInitial} onClose={() => { setBuilderOpen(false); setBuilderInitial(null); }} />}
      {/* Top bar */}
      <div className="px-6 py-3 flex items-center justify-between border-b border-cyan-500/20 bg-black/30 backdrop-blur" data-testid="topbar">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_10px_#00E5FF]" />
          <span className="font-heading text-cyan-300 tracking-[0.4em] text-sm">J.A.R.V.I.S.</span>
          <span className="font-data text-[10px] text-slate-400 uppercase">v1.0 — Just A Rather Very Intelligent System</span>
        </div>
        <div className="flex items-center gap-3">
          {coords && (
            <div className="flex items-center gap-1.5 text-cyan-400 text-[10px] font-data uppercase tracking-widest" title={`Lat ${coords.lat.toFixed(3)}, Lng ${coords.lng.toFixed(3)}`}>
              <MapPin size={12} /> Geo OK
            </div>
          )}
          <div className="flex items-center gap-2 text-cyan-300">
            <PartIcon size={14} />
            <span className="font-data text-[11px] uppercase tracking-widest">{part.label}</span>
          </div>
          <button
            className="glass-btn"
            onClick={activate}
            data-testid="activate-btn"
          >
            <Power size={14} /> Ativar
          </button>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 md:grid-rows-3 gap-4 p-4 md:p-5 h-[calc(100vh-52px)]">
        {/* Left column */}
        <div className="md:col-span-1 md:row-span-2">
          <SystemStatus brainOnline={brainOnline} edgeConnected={edgeConnected} micOk={micOk} camOk={camOk} />
        </div>

        {/* Center: Arc Reactor */}
        <div className="md:col-span-2 md:row-span-2 hud-panel flex flex-col items-center justify-center p-6 relative overflow-hidden" data-testid="central-panel">
          <div className="absolute top-3 left-4 text-[10px] font-data uppercase tracking-widest text-cyan-400/70">// NÚCLEO COGNITIVO</div>
          <div className="absolute top-3 right-4 text-[10px] font-data uppercase tracking-widest text-cyan-400/70">FREQ 60Hz</div>
          <ArcReactor state={reactorState} />
          <div className="mt-6 w-full max-w-md">
            <Waveform active={reactorState !== "idle"} />
          </div>
          <div className="mt-4 w-full max-w-xl">
            <div className="flex gap-2">
              <input
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && textInput.trim()) {
                    const t = textInput.trim(); setTextInput("");
                    const low = t.toLowerCase();
                    if (!activated && /(bom dia|boa tarde|boa noite).*jarvis/.test(low)) {
                      activate();
                    } else { sendMessage(t); }
                  }
                }}
                placeholder='Diga "Bom dia, Jarvis" ou digite seu comando…'
                className="flex-1 bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400 placeholder:text-cyan-700"
                data-testid="command-input"
              />
              <button
                onClick={handleVoicePress}
                className={`glass-btn ${recorder.recording ? "danger" : ""}`}
                data-testid="voice-toggle"
                disabled={!recorder.supported}
              >
                {recorder.recording ? <MicOff size={14} /> : <Mic size={14} />}
                {recorder.recording ? "Parar" : "Voz"}
              </button>
              <button
                onClick={() => { const t = textInput.trim(); if (t) { setTextInput(""); sendMessage(t); } }}
                className="glass-btn"
                data-testid="send-btn"
              >
                Enviar
              </button>
            </div>
            <div className="mt-2 text-center text-[10px] font-data text-cyan-700 uppercase tracking-widest">
              {recorder.recording ? "Gravando… clique em Parar para enviar" : "Pressione Voz para falar"}
            </div>
          </div>
        </div>

        {/* Right top: Morning Report */}
        <div className="md:col-span-1 md:row-span-1">
          <MorningReport data={morning} />
        </div>

        {/* Right middle: FaceID */}
        <div className="md:col-span-1 md:row-span-1">
          <FaceIDPanel profile={profile} onRegister={registerFace} onAuth={authenticateFace} status={authStatus} />
        </div>

        {/* Bottom row: Transcript + QuickActions */}
        <div className="md:col-span-3 md:row-span-1">
          <Transcript messages={messages} streamingText={streaming} />
        </div>
        <div className="md:col-span-1 md:row-span-1">
          <QuickActions
            onAction={(prompt) => sendMessage(prompt)}
            onMusic={() => { setMusicQuery(""); setMusicOpen(true); }}
            googleConnected={googleConnected}
            onConnectGoogle={connectGoogle}
            onShowMemory={() => setMemoryOpen(true)}
            onShowConsole={() => setConsoleOpen(true)}
            onShowBuilder={() => setBuilderOpen(true)}
            onShowVault={() => setVaultOpen(true)}
            onShowOperator={() => setOperatorOpen(true)}
          />
        </div>
      </div>

      {/* User chip (top-right) */}
      {user && (
        <div className="absolute top-3 right-4 z-40 flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-full border border-cyan-500/25 bg-black/40 backdrop-blur">
          {user.picture ? (
            <img src={user.picture} alt="" className="w-6 h-6 rounded-full border border-cyan-500/30" />
          ) : (
            <div className="w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-200 text-[10px]">
              {(user.name || "?").slice(0, 1).toUpperCase()}
            </div>
          )}
          <span className="text-[11px] text-cyan-200 tracking-wider max-w-[160px] truncate">{user.name || user.email}</span>
          <button onClick={logout} title="Sair" className="text-cyan-400/70 hover:text-red-300 ml-1">
            <LogOut size={13} />
          </button>
        </div>
      )}

      <CredentialVault open={vaultOpen} onOpenChange={setVaultOpen} />
      <OperatorPanel open={operatorOpen} onOpenChange={setOperatorOpen} />
    </div>
  );
}
