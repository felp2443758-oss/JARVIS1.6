import React, { useEffect, useRef, useState } from "react";
import { X, Search, Image as ImageIcon, FileText, ExternalLink, Upload, Loader2, Sparkles, Globe, Download, Film, History, Trash2, ChevronRight } from "lucide-react";
import { webSearch, analyzeImageUpload, analyzeImageUrl, convertFileUpload, imageSearchWeb, generateImage, generateVideo, getToolHistory, clearToolHistory, deleteToolHistoryItem, toolAssetUrl, API } from "@/lib/api";

/**
 * Edge Console — tooling modal: search, vision, files, image search, image gen, video gen.
 * Each tab has its own history fetched from /api/agent/history?type=<tab>.
 *
 * Props:
 *  - initial: optional { tab, prompt|query, provider|model, autoRun } to open at a specific
 *    tab and (optionally) auto-run a generation/search.
 */
export default function EdgeConsole({ onClose, onSendToChat, initial }) {
  const [tab, setTab] = useState(initial?.tab || "search");

  // When `initial` changes, switch tab (used when JARVIS triggers from chat)
  useEffect(() => {
    if (initial?.tab) setTab(initial.tab);
  }, [initial]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur p-4" data-testid="edge-console-modal">
      <div className="hud-panel w-[900px] max-w-[95vw] h-[88vh] max-h-[88vh] relative">
        <button className="absolute top-3 right-3 text-cyan-300 hover:text-white z-10" onClick={onClose} data-testid="edge-close">
          <X size={18} />
        </button>
        <div className="px-5 pt-4 pb-2 flex items-center gap-2 shrink-0">
          <Sparkles className="text-cyan-300" size={20} />
          <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-sm">Edge Agent — Console</h3>
        </div>

        <div className="px-5 flex gap-2 mb-3 border-b border-cyan-500/15 pb-2 shrink-0 flex-wrap">
          <TabBtn id="search" active={tab} onClick={setTab} icon={Search} label="Pesquisa" />
          <TabBtn id="vision" active={tab} onClick={setTab} icon={ImageIcon} label="Visão" />
          <TabBtn id="files" active={tab} onClick={setTab} icon={FileText} label="Arquivos" />
          <TabBtn id="images" active={tab} onClick={setTab} icon={Globe} label="Imagens Web" />
          <TabBtn id="genimg" active={tab} onClick={setTab} icon={Sparkles} label="Gerar Imagem" />
          <TabBtn id="genvid" active={tab} onClick={setTab} icon={Sparkles} label="Gerar Vídeo" />
        </div>

        <div className="hud-body px-5 pb-5">
          {tab === "search" && <SearchTab onSendToChat={onSendToChat} initial={initial?.tab === "search" ? initial : null} />}
          {tab === "vision" && <VisionTab onSendToChat={onSendToChat} />}
          {tab === "files" && <FilesTab onSendToChat={onSendToChat} />}
          {tab === "images" && <ImagesTab initial={initial?.tab === "images" ? initial : null} />}
          {tab === "genimg" && <GenerateImageTab onSendToChat={onSendToChat} initial={initial?.tab === "genimg" ? initial : null} />}
          {tab === "genvid" && <GenerateVideoTab onSendToChat={onSendToChat} initial={initial?.tab === "genvid" ? initial : null} />}
        </div>
      </div>
    </div>
  );
}

function TabBtn({ id, active, onClick, icon: Icon, label }) {
  const a = active === id;
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex items-center gap-2 px-3 py-1.5 rounded text-[11px] font-data uppercase tracking-widest border transition-all ${
        a ? "border-cyan-400 text-cyan-200 bg-cyan-500/10 shadow-[0_0_12px_rgba(0,229,255,0.25)]"
          : "border-cyan-500/20 text-cyan-500 hover:text-cyan-300 hover:border-cyan-500/40"
      }`}
      data-testid={`edge-tab-${id}`}
    >
      <Icon size={12} /> {label}
    </button>
  );
}

// ============ History Hook & Panel (shared) ============
function useToolHistory(type) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const refresh = React.useCallback(async () => {
    try { setItems(await getToolHistory(type, 50)); } catch (_) { /* ignore */ }
  }, [type]);
  useEffect(() => { refresh(); }, [refresh]);

  // SSE: refresh automatically when the backend broadcasts a history.updated event
  // matching this tab's type. Keeps multiple open tabs (and tabs in other windows) in sync.
  useEffect(() => {
    let es;
    try {
      es = new EventSource(`${API}/agent/history/events`);
      es.addEventListener("history.updated", (e) => {
        try {
          const data = JSON.parse(e.data || "{}");
          if (data.type === type) refresh();
        } catch (_) { /* ignore bad frames */ }
      });
    } catch (_) { /* SSE optional */ }
    return () => { try { es && es.close(); } catch (_) { /* noop */ } };
  }, [type, refresh]);

  async function clearAll() {
    if (!window.confirm("Limpar todo o histórico desta aba?")) return;
    try { await clearToolHistory(type); setItems([]); } catch (_) { /* ignore */ }
  }
  async function removeItem(id) {
    try { await deleteToolHistoryItem(id); setItems((p) => p.filter((x) => x.id !== id)); } catch (_) { /* ignore */ }
  }
  return { items, refresh, open, setOpen, clearAll, removeItem };
}

function HistoryPanel({ hook, renderItem }) {
  const { items, open, setOpen, clearAll, removeItem } = hook;
  const [filter, setFilter] = useState("");

  // Lightweight, type-agnostic filter: stringify payload + match (case-insensitive)
  const filtered = React.useMemo(() => {
    if (!filter.trim()) return items;
    const q = filter.toLowerCase();
    return items.filter((it) => {
      try {
        const blob = JSON.stringify(it.payload || {}).toLowerCase();
        return blob.includes(q);
      } catch (_) { return false; }
    });
  }, [items, filter]);

  return (
    <div className={`border border-cyan-500/15 rounded ${open ? "" : ""}`}>
      <button
        className="w-full flex items-center justify-between px-3 py-2 text-[10px] font-data uppercase tracking-widest text-cyan-400 hover:text-cyan-200"
        onClick={() => setOpen((o) => !o)}
        data-testid="history-toggle"
      >
        <span className="flex items-center gap-2"><History size={11} /> Histórico ({items.length}{filter ? ` · ${filtered.length} filtrados` : ""})</span>
        <ChevronRight size={11} className={`transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="border-t border-cyan-500/10">
          {items.length > 5 && (
            <div className="px-3 py-2 border-b border-cyan-500/5">
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filtrar histórico…"
                className="w-full bg-black/50 border border-cyan-500/20 rounded px-2 py-1 text-[11px] text-cyan-100 font-data outline-none focus:border-cyan-400/60"
                data-testid="history-filter"
              />
            </div>
          )}
          <div className="max-h-72 overflow-y-auto scroll-tech">
            {filtered.length === 0 && (
              <div className="text-cyan-700 text-[11px] font-data px-3 py-3 text-center">
                {items.length === 0 ? "Vazio" : "Nada encontrado"}
              </div>
            )}
            {filtered.map((it) => (
              <div key={it.id} className="group flex items-center justify-between gap-2 px-3 py-2 border-b border-cyan-500/5 hover:bg-cyan-500/5">
                <div className="flex-1 min-w-0 cursor-pointer" onClick={() => renderItem.onClick && renderItem.onClick(it)}>
                  {renderItem.preview(it)}
                  <div className="text-[9px] font-data text-cyan-700">{new Date(it.ts).toLocaleString("pt-BR")}</div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); removeItem(it.id); }} className="opacity-0 group-hover:opacity-100 text-red-400/70 hover:text-red-400 shrink-0" title="Remover">
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
          {items.length > 0 && (
            <button className="w-full text-[10px] font-data uppercase tracking-widest text-red-400/80 hover:text-red-300 py-2 border-t border-cyan-500/10" onClick={clearAll}>
              Limpar tudo
            </button>
          )}
        </div>
      )}
    </div>
  );
}



// ============ Search Tab ============
function SearchTab({ onSendToChat, initial }) {
  const [query, setQuery] = useState(initial?.query || "");
  const [deep, setDeep] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const history = useToolHistory("search");
  const didAutoRun = useRef(false);

  const run = React.useCallback(async (q) => {
    const queryStr = (q ?? query).trim();
    if (!queryStr) return;
    setLoading(true); setError(null); setData(null);
    try {
      const r = await webSearch(queryStr, { deep, maxResults: deep ? 10 : 6 });
      setData(r);
      history.refresh();
    } catch (e) { setError(e.message || String(e)); }
    setLoading(false);
  }, [query, deep, history]);

  useEffect(() => {
    if (initial?.autoRun && initial?.query && !didAutoRun.current) {
      didAutoRun.current = true;
      setQuery(initial.query);
      run(initial.query);
    }
  }, [initial, run]);

  return (
    <div className="space-y-3" data-testid="search-tab">
      <div className="flex gap-2">
        <input
          value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="Pesquisar na web…"
          className="flex-1 bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
          data-testid="search-input"
        />
        <label className="flex items-center gap-2 text-[11px] font-data text-cyan-400 px-2">
          <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} data-testid="search-deep" /> DEEP
        </label>
        <button className="glass-btn" onClick={() => run()} disabled={loading} data-testid="search-run">
          {loading ? <Loader2 className="animate-spin" size={14} /> : <Search size={14} />} Buscar
        </button>
      </div>
      {error && <div className="text-red-400 text-xs font-data">{error}</div>}
      {data && data.error && <div className="text-amber-400 text-xs font-data">Erro: {data.error}</div>}
      {data?.answer && (
        <div className="border border-cyan-500/30 rounded p-3 bg-cyan-500/5">
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-1">Resposta Direta</div>
          <div className="text-sm font-data text-slate-100 leading-relaxed">{data.answer}</div>
        </div>
      )}
      {data?.results?.length > 0 && (
        <div className="space-y-2" data-testid="search-results">
          {data.results.map((r, i) => (
            <div key={i} className="border border-cyan-500/15 rounded p-3 hover:border-cyan-400/40 transition-colors">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="font-data text-cyan-200 text-sm truncate">{r.title}</div>
                  <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-[10px] font-data text-cyan-500 hover:text-cyan-300 truncate inline-flex items-center gap-1">
                    <ExternalLink size={10} /> {r.url}
                  </a>
                </div>
                {typeof r.score === "number" && (
                  <div className="text-[10px] font-data text-cyan-400 shrink-0">{(r.score * 100).toFixed(0)}%</div>
                )}
              </div>
              <div className="text-xs font-data text-slate-300 mt-2 leading-relaxed line-clamp-4">{r.content}</div>
            </div>
          ))}
          {onSendToChat && data?.answer && (
            <button
              className="glass-btn w-full justify-center"
              onClick={() => onSendToChat(`Resuma para mim esta pesquisa sobre "${data.query}": ${data.answer}`)}
              data-testid="search-send-chat"
            >
              Enviar resumo para o JARVIS
            </button>
          )}
        </div>
      )}
      {!loading && !data && (
        <div className="text-center text-cyan-700 text-[11px] font-data uppercase tracking-widest py-8">
          Faça uma pesquisa para começar
        </div>
      )}
      <HistoryPanel
        hook={history}
        renderItem={{
          onClick: (it) => { setData(it.payload?.result || null); setQuery(it.payload?.query || ""); },
          preview: (it) => <div className="text-xs font-data text-cyan-200 truncate">{it.payload?.query || "(sem query)"}</div>,
        }}
      />
    </div>
  );
}

// ============ Vision Tab ============
function VisionTab({ onSendToChat }) {
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const history = useToolHistory("vision");
  const preview = file ? URL.createObjectURL(file) : null;

  async function runUpload() {
    if (!file) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await analyzeImageUpload(file, question || null);
      setResult(r);
      history.refresh();
    } catch (e) { setError(e.message); }
    setLoading(false);
  }
  async function runUrl() {
    if (!url.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await analyzeImageUrl(url.trim(), question || null);
      setResult(r);
      history.refresh();
    } catch (e) { setError(e.message); }
    setLoading(false);
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="vision-tab">
      <div className="space-y-3">
        <div className="border border-dashed border-cyan-500/30 rounded p-4 text-center">
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} className="hidden" id="vision-file" data-testid="vision-file" />
          <label htmlFor="vision-file" className="glass-btn justify-center cursor-pointer">
            <Upload size={14} /> Selecionar Imagem
          </label>
          <div className="text-[10px] font-data text-cyan-700 mt-2 uppercase tracking-widest">PNG, JPG, WebP</div>
          {preview && (
            <div className="mt-3"><img src={preview} alt="preview" className="max-h-48 mx-auto rounded border border-cyan-500/30" /></div>
          )}
        </div>
        <div className="text-center text-[10px] font-data text-cyan-700 uppercase tracking-widest">— ou —</div>
        <input
          value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="Cole a URL de uma imagem (https://…)"
          className="w-full bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
          data-testid="vision-url"
        />
        <input
          value={question} onChange={(e) => setQuestion(e.target.value)}
          placeholder="Pergunta opcional (ex.: 'Qual texto está visível?')"
          className="w-full bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
          data-testid="vision-question"
        />
        <div className="flex gap-2">
          <button className="glass-btn flex-1 justify-center" onClick={runUpload} disabled={!file || loading} data-testid="vision-analyze-upload">
            {loading ? <Loader2 className="animate-spin" size={14} /> : <ImageIcon size={14} />} Analisar Upload
          </button>
          <button className="glass-btn flex-1 justify-center" onClick={runUrl} disabled={!url.trim() || loading} data-testid="vision-analyze-url">
            {loading ? <Loader2 className="animate-spin" size={14} /> : <Globe size={14} />} Analisar URL
          </button>
        </div>
      </div>
      <div className="border border-cyan-500/20 rounded p-3 bg-black/30 min-h-[200px]" data-testid="vision-result">
        <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-2">Análise (Gemini 2.5 Flash)</div>
        {error && <div className="text-red-400 text-xs font-data">{error}</div>}
        {!result && !loading && !error && (
          <div className="text-cyan-700 text-[11px] font-data uppercase tracking-widest text-center py-12">Aguardando imagem</div>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-cyan-300 text-sm font-data"><Loader2 className="animate-spin" size={16} /> Analisando…</div>
        )}
        {result?.analysis && (
          <div className="text-sm font-data text-slate-100 leading-relaxed whitespace-pre-wrap">{result.analysis}</div>
        )}
        {result?.analysis && onSendToChat && (
          <button className="glass-btn mt-3 w-full justify-center" onClick={() => onSendToChat(`Analise esta imagem para mim. O sistema de visão disse: ${result.analysis}`)} data-testid="vision-send-chat">
            Enviar análise para o JARVIS
          </button>
        )}
      </div>
      <div className="md:col-span-2">
        <HistoryPanel
          hook={history}
          renderItem={{
            onClick: (it) => {
              setResult({ analysis: it.payload?.analysis });
              if (it.payload?.url) setUrl(it.payload.url);
              if (it.payload?.question) setQuestion(it.payload.question);
            },
            preview: (it) => (
              <div className="text-xs font-data text-cyan-200 truncate">
                {it.payload?.filename || it.payload?.url || "(análise)"}
                {it.payload?.question && <span className="text-cyan-600 ml-2">— {it.payload.question}</span>}
              </div>
            ),
          }}
        />
      </div>
    </div>
  );
}

// ============ Files Tab ============
function FilesTab({ onSendToChat }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const history = useToolHistory("files");

  async function run() {
    if (!file) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await convertFileUpload(file);
      setResult(r);
      history.refresh();
    } catch (e) { setError(e.message); }
    setLoading(false);
  }

  return (
    <div className="space-y-3" data-testid="files-tab">
      <div className="border border-dashed border-cyan-500/30 rounded p-6 text-center">
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} className="hidden" id="files-file" data-testid="files-file" />
        <label htmlFor="files-file" className="glass-btn justify-center cursor-pointer">
          <Upload size={14} /> Selecionar Arquivo
        </label>
        <div className="text-[10px] font-data text-cyan-700 mt-2 uppercase tracking-widest">PDF, DOCX, TXT, MD, CSV, JSON, PNG, JPG (OCR)</div>
        {file && <div className="text-xs font-data text-cyan-200 mt-2">{file.name} <span className="text-cyan-700">({(file.size/1024).toFixed(1)} KB)</span></div>}
      </div>
      <button className="glass-btn w-full justify-center" onClick={run} disabled={!file || loading} data-testid="files-convert">
        {loading ? <Loader2 className="animate-spin" size={14} /> : <FileText size={14} />} Extrair Texto
      </button>
      {error && <div className="text-red-400 text-xs font-data">{error}</div>}
      {result && (
        <div className="border border-cyan-500/20 rounded p-3 bg-black/30" data-testid="files-result">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400">
              {result.type} — {result.chars} chars
            </div>
            <div className="text-[10px] font-data text-cyan-700 truncate ml-2">{result.filename}</div>
          </div>
          {result.error && <div className="text-amber-400 text-xs font-data mb-2">⚠ {result.error}</div>}
          <pre className="text-xs font-data text-slate-100 leading-relaxed whitespace-pre-wrap max-h-80 overflow-y-auto scroll-tech">{result.text}</pre>
          {result.text && onSendToChat && (
            <button
              className="glass-btn mt-3 w-full justify-center"
              onClick={() => onSendToChat(`Analise este conteúdo extraído de "${result.filename}":\n\n${result.text.slice(0, 4000)}`)}
              data-testid="files-send-chat"
            >
              Enviar para o JARVIS
            </button>
          )}
        </div>
      )}
      <HistoryPanel
        hook={history}
        renderItem={{
          onClick: (it) => setResult(it.payload || null),
          preview: (it) => (
            <div className="text-xs font-data text-cyan-200 truncate">
              {it.payload?.filename || "(arquivo)"}
              {it.payload?.type && <span className="text-cyan-600 ml-2">— {it.payload.type}</span>}
              {typeof it.payload?.chars === "number" && <span className="text-cyan-600 ml-2">— {it.payload.chars} chars</span>}
            </div>
          ),
        }}
      />
    </div>
  );
}

// ============ Images (web image search) Tab ============
function ImagesTab({ initial }) {
  const [query, setQuery] = useState(initial?.query || "");
  const [loading, setLoading] = useState(false);
  const [images, setImages] = useState([]);
  const history = useToolHistory("image_search");
  const didAutoRun = useRef(false);

  const run = React.useCallback(async (q) => {
    const queryStr = (q ?? query).trim();
    if (!queryStr) return;
    setLoading(true); setImages([]);
    try {
      const r = await imageSearchWeb(queryStr, 12);
      setImages(r.images || []);
      history.refresh();
    } catch (_) { /* keep silent */ }
    setLoading(false);
  }, [query, history]);

  useEffect(() => {
    if (initial?.autoRun && initial?.query && !didAutoRun.current) {
      didAutoRun.current = true;
      setQuery(initial.query);
      run(initial.query);
    }
  }, [initial, run]);

  return (
    <div className="space-y-3" data-testid="images-tab">
      <div className="flex gap-2">
        <input
          value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="Buscar imagens na web…"
          className="flex-1 bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
          data-testid="images-input"
        />
        <button className="glass-btn" onClick={() => run()} disabled={loading} data-testid="images-run">
          {loading ? <Loader2 className="animate-spin" size={14} /> : <Globe size={14} />} Buscar
        </button>
      </div>
      {images.length === 0 && !loading && (
        <div className="text-center text-cyan-700 text-[11px] font-data uppercase tracking-widest py-10">
          Digite uma busca para visualizar imagens
        </div>
      )}
      {loading && <div className="flex items-center gap-2 text-cyan-300 text-sm font-data"><Loader2 className="animate-spin" size={16} /> Buscando…</div>}
      {images.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2" data-testid="images-grid">
          {images.map((src, i) => (
            <a key={i} href={src} target="_blank" rel="noopener noreferrer" className="block border border-cyan-500/20 rounded overflow-hidden hover:border-cyan-400/60 transition-colors">
              <img src={src} alt={`result ${i}`} className="w-full h-32 object-cover" loading="lazy" onError={(e) => { e.currentTarget.style.opacity = 0.2; }} />
            </a>
          ))}
        </div>
      )}
      <HistoryPanel
        hook={history}
        renderItem={{
          onClick: (it) => {
            setQuery(it.payload?.query || "");
            setImages(it.payload?.images || []);
          },
          preview: (it) => (
            <div className="flex items-center gap-2">
              {it.payload?.images?.[0] && (
                <img src={it.payload.images[0]} alt="thumb" className="w-8 h-8 object-cover rounded border border-cyan-500/20" />
              )}
              <div className="text-xs font-data text-cyan-200 truncate flex-1">{it.payload?.query || "(busca)"}</div>
              <span className="text-[10px] font-data text-cyan-600">{(it.payload?.images || []).length}</span>
            </div>
          ),
        }}
      />
    </div>
  );
}


// ============ Generate Image Tab (gpt-image-1 / nano-banana) ============
function GenerateImageTab({ initial, onSendToChat }) {
  const [prompt, setPrompt] = useState(initial?.prompt || "");
  const [provider, setProvider] = useState(initial?.provider || "gpt-image");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const history = useToolHistory("image_gen");
  const didAutoRun = useRef(false);

  const run = React.useCallback(async (overrides) => {
    const p = (overrides?.prompt ?? prompt).trim();
    const prov = overrides?.provider ?? provider;
    if (!p || loading) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await generateImage(p, { provider: prov });
      if (r.error) setError(r.error);
      setResult(r);
      history.refresh();
    } catch (e) { setError(e.message || String(e)); }
    setLoading(false);
  }, [prompt, provider, loading, history]);

  useEffect(() => {
    if (initial?.autoRun && initial?.prompt && !didAutoRun.current) {
      didAutoRun.current = true;
      setPrompt(initial.prompt);
      if (initial.provider) setProvider(initial.provider);
      run({ prompt: initial.prompt, provider: initial.provider });
    }
  }, [initial, run]);

  const firstImg = result?.images?.[0];

  return (
    <div className="space-y-3" data-testid="genimg-tab">
      <div className="flex gap-2">
        <textarea
          rows={2}
          value={prompt} onChange={(e) => setPrompt(e.target.value)}
          placeholder="Descreva a imagem que deseja gerar… (ex.: 'um arc reactor cyberpunk em estilo blueprint')"
          className="flex-1 bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400 resize-none"
          data-testid="genimg-prompt"
        />
      </div>
      <div className="flex items-center gap-3">
        <label className="text-[10px] font-data uppercase tracking-widest text-cyan-400">Modelo:</label>
        <select value={provider} onChange={(e) => setProvider(e.target.value)} className="bg-black/60 border border-cyan-500/30 rounded px-2 py-1 text-xs text-cyan-100 font-data" data-testid="genimg-provider">
          <option value="gpt-image">OpenAI gpt-image-1</option>
          <option value="nano-banana">Gemini Nano Banana</option>
        </select>
        <button className="glass-btn ml-auto" onClick={() => run()} disabled={!prompt.trim() || loading} data-testid="genimg-run">
          {loading ? <Loader2 className="animate-spin" size={14} /> : <Sparkles size={14} />} Gerar
        </button>
      </div>
      {error && <div className="text-red-400 text-xs font-data">Erro: {error}</div>}
      {result?.fallback_from && <div className="text-amber-400 text-[10px] font-data">⚠ Fallback automático para {result.provider}</div>}
      {loading && (
        <div className="border border-cyan-500/20 rounded p-8 text-center text-cyan-300 text-sm font-data flex items-center justify-center gap-2">
          <Loader2 className="animate-spin" size={16} /> Gerando imagem… (pode levar até 60s)
        </div>
      )}
      {firstImg && (
        <div className="border border-cyan-500/30 rounded p-3 bg-black/30">
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-2">{result.provider}</div>
          <img
            src={firstImg.url || `data:${firstImg.mime || "image/png"};base64,${firstImg.b64}`}
            alt="generated"
            className="max-w-full max-h-[480px] mx-auto rounded border border-cyan-500/30"
            data-testid="genimg-result"
          />
          <a
            className="glass-btn w-full justify-center mt-3"
            download="jarvis-generated.png"
            href={firstImg.url || `data:${firstImg.mime || "image/png"};base64,${firstImg.b64}`}
            data-testid="genimg-download"
          >
            <Download size={14} /> Baixar PNG
          </a>
        </div>
      )}
      <HistoryPanel
        hook={history}
        renderItem={{
          onClick: (it) => {
            setPrompt(it.payload?.prompt || "");
            if (it.payload?.provider) setProvider(it.payload.provider);
            const imgs = (it.payload?.images || []).map((im) => {
              if (im.asset_id) return { url: toolAssetUrl(im.asset_id), mime: im.mime };
              return im;
            });
            if (imgs.length) {
              setResult({ provider: it.payload.provider, images: imgs });
            }
          },
          preview: (it) => {
            const im = (it.payload?.images || [])[0] || {};
            const src = im.asset_id ? toolAssetUrl(im.asset_id) : (im.url || (im.b64 ? `data:${im.mime || "image/png"};base64,${im.b64}` : null));
            return (
              <div className="flex items-center gap-2">
                {src && (
                  <img
                    src={src}
                    alt="thumb"
                    className="w-8 h-8 object-cover rounded border border-cyan-500/20"
                    loading="lazy"
                    onError={(e) => { e.currentTarget.style.opacity = 0.2; }}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-data text-cyan-200 truncate">{it.payload?.prompt || "(prompt)"}</div>
                  <div className="text-[9px] font-data text-cyan-600 truncate">{it.payload?.provider}{it.payload?.error ? " — erro" : ""}</div>
                </div>
              </div>
            );
          },
        }}
      />
      {onSendToChat && null /* keep API symmetry; chat handler exists via Dashboard */}
    </div>
  );
}

// ============ Generate Video Tab (Fal.ai) ============
function GenerateVideoTab({ initial, onSendToChat }) {
  const [prompt, setPrompt] = useState(initial?.prompt || "");
  const [model, setModel] = useState(initial?.model || "veo3-fast");
  const [duration, setDuration] = useState(8);
  const [aspect, setAspect] = useState("16:9");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const history = useToolHistory("video_gen");
  const didAutoRun = useRef(false);

  const run = React.useCallback(async (overrides) => {
    const p = (overrides?.prompt ?? prompt).trim();
    const m = overrides?.model ?? model;
    if (!p || loading) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await generateVideo(p, { model: m, duration, aspect_ratio: aspect });
      if (r.error) setError(r.error);
      setResult(r);
      history.refresh();
    } catch (e) { setError(e.message || String(e)); }
    setLoading(false);
  }, [prompt, model, duration, aspect, loading, history]);

  useEffect(() => {
    if (initial?.autoRun && initial?.prompt && !didAutoRun.current) {
      didAutoRun.current = true;
      setPrompt(initial.prompt);
      if (initial.model) setModel(initial.model);
      run({ prompt: initial.prompt, model: initial.model });
    }
  }, [initial, run]);

  return (
    <div className="space-y-3" data-testid="genvid-tab">
      <textarea
        rows={3}
        value={prompt} onChange={(e) => setPrompt(e.target.value)}
        placeholder="Descreva o vídeo… (ex.: 'drone voando sobre uma cidade cyberpunk à noite, neon, chuva')"
        className="w-full bg-black/50 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400 resize-none"
        data-testid="genvid-prompt"
      />
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-1">Modelo</div>
          <select value={model} onChange={(e) => setModel(e.target.value)} className="w-full bg-black/60 border border-cyan-500/30 rounded px-2 py-1 text-cyan-100 font-data" data-testid="genvid-model">
            <option value="veo3-fast">Veo 3 Fast (rápido)</option>
            <option value="veo3">Veo 3 (qualidade)</option>
            <option value="kling-v2">Kling v2 Master</option>
            <option value="luma">Luma Dream Machine</option>
          </select>
        </div>
        <div>
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-1">Duração (s)</div>
          <input type="number" min={4} max={10} value={duration} onChange={(e) => setDuration(parseInt(e.target.value || "8"))} className="w-full bg-black/60 border border-cyan-500/30 rounded px-2 py-1 text-cyan-100 font-data" />
        </div>
        <div>
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-1">Proporção</div>
          <select value={aspect} onChange={(e) => setAspect(e.target.value)} className="w-full bg-black/60 border border-cyan-500/30 rounded px-2 py-1 text-cyan-100 font-data">
            <option value="16:9">16:9</option>
            <option value="9:16">9:16</option>
            <option value="1:1">1:1</option>
          </select>
        </div>
      </div>
      <button className="glass-btn w-full justify-center" onClick={() => run()} disabled={!prompt.trim() || loading} data-testid="genvid-run">
        {loading ? <Loader2 className="animate-spin" size={14} /> : <Film size={14} />} {loading ? "Gerando vídeo… (1-3 min)" : "Gerar Vídeo"}
      </button>
      {error && <div className="text-red-400 text-xs font-data">Erro: {error}</div>}
      {result?.video_url && (
        <div className="border border-cyan-500/30 rounded p-3 bg-black/30">
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-2">{result.provider}</div>
          <video src={result.video_url} controls className="w-full rounded border border-cyan-500/30" data-testid="genvid-result" />
          <a className="glass-btn w-full justify-center mt-3" href={result.video_url} download target="_blank" rel="noopener noreferrer">
            <Download size={14} /> Baixar vídeo
          </a>
        </div>
      )}
      <HistoryPanel
        hook={history}
        renderItem={{
          onClick: (it) => {
            setPrompt(it.payload?.prompt || "");
            if (it.payload?.model) setModel(it.payload.model);
            if (it.payload?.video_url) setResult({ provider: it.payload.provider, video_url: it.payload.video_url });
          },
          preview: (it) => (
            <div className="flex-1 min-w-0">
              <div className="text-xs font-data text-cyan-200 truncate">{it.payload?.prompt || "(prompt)"}</div>
              <div className="text-[9px] font-data text-cyan-600 truncate">
                {it.payload?.model} · {it.payload?.aspect_ratio} · {it.payload?.duration}s{it.payload?.error ? " — erro" : ""}
              </div>
            </div>
          ),
        }}
      />
      {onSendToChat && null}
    </div>
  );
}
