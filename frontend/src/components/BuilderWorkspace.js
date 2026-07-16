import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import Editor from "@monaco-editor/react";
import {
  X, Plus, Trash2, Download, Save, Loader2, Play, FileCode, Eye, Terminal,
  Send, Folder, FilePlus, RotateCcw, Sparkles, ChevronRight, Code2, ExternalLink,
  GitBranch, Globe, ImageIcon, Upload, Camera, Copy, Check,
} from "lucide-react";
import {
  listProjects, getProject, createProject, deleteProject, listTemplates,
  saveProjectFiles, builderChat, downloadProjectZipUrl, buildPreviewSrcDoc, fileLanguage,
  listSnapshots, createSnapshot, restoreSnapshot, deleteSnapshot,
  uploadAsset, deleteAsset, publishProject, unpublishProject, publicProjectUrl,
} from "@/lib/builder-api";

/**
 * BuilderWorkspace — JARVIS Builder Mode.
 * Fullscreen modal: project sidebar | chat | (preview | code | console)
 */
export default function BuilderWorkspace({ onClose, initial }) {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("preview"); // preview | code | console | assets
  const [previewKey, setPreviewKey] = useState(0);
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [dirtyFiles, setDirtyFiles] = useState({});
  const [activeFile, setActiveFile] = useState(null);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [showPublish, setShowPublish] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [publishCta, setPublishCta] = useState(null); // {projectId, published: false} after auto-create finishes
  const didAutoInit = useRef(false);

  // Load projects + templates on mount
  useEffect(() => {
    (async () => {
      try {
        const [list, tpls] = await Promise.all([listProjects(), listTemplates()]);
        setProjects(list);
        setTemplates(tpls);
        if (list.length > 0) await openProject(list[0].id);
      } catch (e) { console.error(e); }
    })();
    const onMsg = (ev) => {
      const d = ev.data;
      if (!d || !d.__jarvis_preview) return;
      setConsoleLogs((prev) => [...prev.slice(-200), { level: d.level, msg: d.msg, ts: d.ts }]);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refreshList() {
    try { setProjects(await listProjects()); } catch (_) { /* keep */ }
  }

  async function openProject(id) {
    setLoading(true);
    try {
      const p = await getProject(id);
      setProject(p);
      setDirtyFiles({});
      const firstFile = Object.keys(p.files || {})[0] || null;
      setActiveFile(firstFile);
      setConsoleLogs([]);
      setPreviewKey((k) => k + 1);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function handleCreate() {
    setShowNewModal(true);
  }

  async function createWithTemplate(name, templateId) {
    setShowNewModal(false);
    if (!name) return;
    setLoading(true);
    try {
      const p = await createProject(name, "", templateId);
      await refreshList();
      await openProject(p.id);
      return p;
    } catch (e) { console.error(e); }
    setLoading(false);
    return null;
  }

  // Auto-init from `initial` prop (chat-routed action: "crie um site de X")
  useEffect(() => {
    if (!initial?.autoCreate || didAutoInit.current) return;
    if (!templates || templates.length === 0) return; // wait for templates to load
    didAutoInit.current = true;
    (async () => {
      const brief = (initial.prompt || "").trim();
      const baseName = brief
        ? brief.slice(0, 40).replace(/\s+/g, " ").trim()
        : "Novo Projeto";
      const projectName = baseName.charAt(0).toUpperCase() + baseName.slice(1);
      setLoading(true);
      try {
        const created = await createProject(projectName, brief || "", "blank");
        await refreshList();
        await openProject(created.id);
        // Send the brief as a chat message so the AI starts scaffolding the site
        if (brief) {
          setChatInput("");
          setChatBusy(true);
          const optimistic = [
            { role: "user", content: brief, ts: new Date().toISOString() },
            { role: "assistant", content: "…", ts: new Date().toISOString(), pending: true },
          ];
          setProject((p) => ({ ...(p || created), messages: optimistic }));
          try {
            const r = await builderChat(created.id, brief);
            if (r.project) {
              setProject(r.project);
              setDirtyFiles({});
              if (r.changed_files && r.changed_files.length > 0) {
                setActiveFile(r.changed_files[0]);
              }
              setPreviewKey((k) => k + 1);
              // Offer to publish — JARVIS workflow: "voz → landing page no ar"
              const hasFiles = Object.keys(r.project.files || {}).length > 0;
              if (hasFiles && !r.project.public_slug) {
                setPublishCta({ projectId: r.project.id });
              }
            }
          } catch (e) {
            console.error(e);
            setProject((p) => ({ ...p, messages: [...(p?.messages || []).slice(0, -1), { role: "assistant", content: `Erro: ${e.message || e}`, ts: new Date().toISOString() }] }));
          }
          setChatBusy(false);
        }
      } catch (e) { console.error(e); }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial, templates]);

  async function handleDelete(id) {
    if (!window.confirm("Apagar este projeto?")) return;
    await deleteProject(id);
    if (project?.id === id) setProject(null);
    await refreshList();
  }

  // Files actually shown (drafts override saved)
  const mergedFiles = useMemo(() => {
    const f = { ...(project?.files || {}) };
    Object.entries(dirtyFiles).forEach(([k, v]) => { f[k] = v; });
    return f;
  }, [project, dirtyFiles]);

  const srcDoc = useMemo(() => buildPreviewSrcDoc(mergedFiles, project?.assets), [mergedFiles, project]);

  const isDirty = Object.keys(dirtyFiles).length > 0;

  async function handleSave() {
    if (!project || !isDirty) return;
    setLoading(true);
    try {
      const updated = await saveProjectFiles(project.id, dirtyFiles, []);
      setProject(updated);
      setDirtyFiles({});
      setPreviewKey((k) => k + 1);
    } catch (e) { console.error(e); }
    setLoading(false);
  }

  function handleEditorChange(value) {
    if (!activeFile) return;
    setDirtyFiles((prev) => ({ ...prev, [activeFile]: value ?? "" }));
  }

  function handleAddFile() {
    const name = prompt("Nome do novo arquivo (ex.: about.html, utils.js):");
    if (!name) return;
    if (!project) return;
    setDirtyFiles((prev) => ({ ...prev, [name]: "" }));
    setActiveFile(name);
    setTab("code");
  }

  async function handleSendChat() {
    if (!project || !chatInput.trim() || chatBusy) return;
    const msg = chatInput.trim();
    setChatInput("");
    setChatBusy(true);
    // optimistic UI
    const optimistic = [
      ...(project.messages || []),
      { role: "user", content: msg, ts: new Date().toISOString() },
      { role: "assistant", content: "…", ts: new Date().toISOString(), pending: true },
    ];
    setProject((p) => ({ ...p, messages: optimistic }));
    try {
      const r = await builderChat(project.id, msg);
      if (r.project) {
        setProject(r.project);
        setDirtyFiles({});
        if (r.changed_files && r.changed_files.length > 0) {
          setActiveFile(r.changed_files[0]);
        }
        setPreviewKey((k) => k + 1);
      }
    } catch (e) {
      console.error(e);
      setProject((p) => ({ ...p, messages: [...(p.messages || []).slice(0, -1), { role: "assistant", content: `Erro: ${e.message || e}`, ts: new Date().toISOString() }] }));
    }
    setChatBusy(false);
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 flex flex-col" data-testid="builder-workspace">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-cyan-500/20 px-4 py-2 bg-black/60 backdrop-blur shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Sparkles className="text-cyan-300" size={18} />
          <div className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">JARVIS Builder</div>
          {project && (
            <>
              <ChevronRight size={12} className="text-cyan-700" />
              <div className="font-data text-sm text-white truncate max-w-[300px]">{project.name}</div>
              {isDirty && <span className="text-amber-400 text-[10px] font-data uppercase">• modificado</span>}
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {project && (
            <>
              {project.public_slug && (
                <span className="text-emerald-300 text-[10px] font-data uppercase tracking-widest border border-emerald-500/30 rounded px-2 py-1">● publicado</span>
              )}
              <button className="glass-btn" onClick={() => setShowSnapshots(true)} data-testid="builder-snapshots">
                <GitBranch size={12} /> Snapshots
              </button>
              <button className="glass-btn" onClick={() => setShowPublish(true)} data-testid="builder-publish-btn" style={{ borderColor: "rgba(0,255,157,0.4)", color: "#86efac" }}>
                <Globe size={12} /> Publicar
              </button>
              <button className="glass-btn" onClick={handleSave} disabled={!isDirty || loading} data-testid="builder-save">
                {loading ? <Loader2 className="animate-spin" size={12} /> : <Save size={12} />} Salvar
              </button>
              <a className="glass-btn" href={downloadProjectZipUrl(project.id)} download data-testid="builder-download">
                <Download size={12} /> ZIP
              </a>
              <button className="glass-btn" onClick={() => setPreviewKey((k) => k + 1)} title="Recarregar preview" data-testid="builder-reload">
                <RotateCcw size={12} />
              </button>
            </>
          )}
          <button className="glass-btn danger" onClick={onClose} data-testid="builder-close">
            <X size={12} /> Fechar
          </button>
        </div>
      </div>

      {/* Sub-modals */}
      {showNewModal && (
        <NewProjectModal templates={templates} onClose={() => setShowNewModal(false)} onCreate={createWithTemplate} />
      )}
      {showSnapshots && project && (
        <SnapshotsModal
          projectId={project.id}
          onClose={() => setShowSnapshots(false)}
          onRestored={async () => { setShowSnapshots(false); await openProject(project.id); }}
        />
      )}
      {showPublish && project && (
        <PublishModal
          project={project}
          onClose={() => setShowPublish(false)}
          onChange={(updated) => setProject(updated)}
        />
      )}

      {/* Publish CTA — appears after JARVIS auto-generates a site via chat-routed action */}
      {publishCta && project && project.id === publishCta.projectId && !project.public_slug && (
        <div className="border-b border-emerald-500/30 bg-gradient-to-r from-emerald-950/60 via-emerald-900/30 to-transparent px-4 py-2.5 flex items-center gap-3" data-testid="publish-cta">
          <Globe size={14} className="text-emerald-300 shrink-0" />
          <div className="text-[12px] font-data text-emerald-100 flex-1">
            <span className="text-emerald-300 font-semibold">Sua landing page está pronta.</span>{" "}
            Devo publicá-la agora?
          </div>
          <button
            className="glass-btn"
            style={{ borderColor: "rgba(0,255,157,0.5)", color: "#86efac" }}
            onClick={() => { setShowPublish(true); setPublishCta(null); }}
            data-testid="publish-cta-yes"
          >
            <Globe size={12} /> Sim, publicar
          </button>
          <button
            className="text-emerald-400/70 hover:text-emerald-200 text-[11px] font-data uppercase tracking-widest px-2"
            onClick={() => setPublishCta(null)}
            data-testid="publish-cta-no"
          >
            Agora não
          </button>
        </div>
      )}

      {/* Body */}
      <div className="flex-1 grid grid-cols-[200px_minmax(320px,1fr)_minmax(420px,1.4fr)] min-h-0">
        {/* Project Sidebar */}
        <aside className="border-r border-cyan-500/15 bg-black/40 overflow-y-auto scroll-tech" data-testid="builder-sidebar">
          <div className="p-3 border-b border-cyan-500/10 flex items-center justify-between">
            <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400">Projetos</div>
            <button onClick={handleCreate} className="text-cyan-300 hover:text-white" title="Novo projeto" data-testid="builder-new-project">
              <Plus size={14} />
            </button>
          </div>
          {projects.length === 0 && <div className="text-cyan-700 text-[11px] font-data p-3">Nenhum projeto ainda. Clique em + para criar.</div>}
          {projects.map((p) => (
            <div key={p.id} className={`group flex items-center justify-between px-3 py-2 border-b border-cyan-500/5 cursor-pointer hover:bg-cyan-500/5 ${project?.id === p.id ? "bg-cyan-500/10 border-l-2 border-l-cyan-400" : ""}`} onClick={() => openProject(p.id)} data-testid={`project-item-${p.id}`}>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-data text-cyan-100 truncate">{p.name}</div>
                <div className="text-[9px] font-data text-cyan-700 truncate">{new Date(p.updated_at).toLocaleString("pt-BR")}</div>
              </div>
              <button onClick={(e) => { e.stopPropagation(); handleDelete(p.id); }} className="opacity-0 group-hover:opacity-100 text-red-400/70 hover:text-red-400">
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </aside>

        {/* Chat Pane */}
        <section className="border-r border-cyan-500/15 flex flex-col bg-black/30 min-w-0" data-testid="builder-chat-pane">
          <div className="px-3 py-2 border-b border-cyan-500/10 flex items-center gap-2 text-[10px] font-data uppercase tracking-widest text-cyan-400">
            <Code2 size={12} /> Conversa de Construção
          </div>
          <ChatHistory messages={project?.messages || []} />
          <div className="border-t border-cyan-500/15 p-2 bg-black/40">
            <div className="flex gap-2">
              <textarea
                rows={2}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSendChat(); } }}
                placeholder={project ? "Descreva o que construir ou modificar… (Enter para enviar, Shift+Enter para quebra de linha)" : "Crie ou abra um projeto na barra à esquerda."}
                className="flex-1 bg-black/60 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400 placeholder:text-cyan-800 resize-none"
                disabled={!project || chatBusy}
                data-testid="builder-chat-input"
              />
              <button className="glass-btn self-stretch" onClick={handleSendChat} disabled={!project || chatBusy || !chatInput.trim()} data-testid="builder-chat-send">
                {chatBusy ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />}
              </button>
            </div>
            <div className="text-[10px] font-data text-cyan-700 uppercase tracking-widest mt-1">
              {chatBusy ? "JARVIS Builder pensando…" : "Gemini 2.5 Flash · gera/edita arquivos do projeto"}
            </div>
          </div>
        </section>

        {/* Right Pane: Preview / Code / Console */}
        <section className="flex flex-col min-w-0 bg-black/20" data-testid="builder-right-pane">
          <div className="border-b border-cyan-500/15 flex items-center gap-1 px-2 py-1.5 bg-black/40">
            <TabBtn id="preview" active={tab} onClick={setTab} Icon={Eye} label="Preview" />
            <TabBtn id="code" active={tab} onClick={setTab} Icon={FileCode} label="Code" />
            <TabBtn id="assets" active={tab} onClick={setTab} Icon={ImageIcon} label={`Assets${project?.assets ? ` (${Object.keys(project.assets).length})` : ""}`} />
            <TabBtn id="console" active={tab} onClick={setTab} Icon={Terminal} label={`Console${consoleLogs.length ? ` (${consoleLogs.length})` : ""}`} />
            <div className="flex-1" />
            {tab === "preview" && project && (
              <button className="glass-btn" onClick={() => openInNewTab(srcDoc)} title="Abrir em nova janela" data-testid="builder-open-tab">
                <ExternalLink size={12} /> Nova Janela
              </button>
            )}
          </div>
          <div className="flex-1 min-h-0">
            {!project && (
              <div className="h-full flex flex-col items-center justify-center text-cyan-700 text-xs font-data uppercase tracking-widest gap-3">
                <Sparkles className="text-cyan-500" size={32} />
                <div>Selecione ou crie um projeto para começar</div>
                <button className="glass-btn" onClick={handleCreate}><Plus size={14} /> Criar Projeto</button>
              </div>
            )}
            {project && tab === "preview" && (
              <iframe
                key={previewKey}
                srcDoc={srcDoc}
                sandbox="allow-scripts allow-forms allow-modals allow-pointer-lock allow-popups allow-same-origin"
                title="preview"
                className="w-full h-full bg-white"
                data-testid="builder-preview-iframe"
              />
            )}
            {project && tab === "code" && (
              <CodeTab
                files={mergedFiles}
                activeFile={activeFile}
                onSelectFile={setActiveFile}
                onChange={handleEditorChange}
                onAddFile={handleAddFile}
                onDeleteFile={(name) => {
                  if (!window.confirm(`Remover ${name}?`)) return;
                  setDirtyFiles((prev) => { const c = { ...prev }; delete c[name]; return c; });
                  saveProjectFiles(project.id, {}, [name]).then(setProject);
                  setActiveFile(Object.keys(mergedFiles).find((k) => k !== name) || null);
                }}
                dirty={dirtyFiles}
              />
            )}
            {project && tab === "console" && (
              <ConsoleTab logs={consoleLogs} onClear={() => setConsoleLogs([])} />
            )}
            {project && tab === "assets" && (
              <AssetsTab
                project={project}
                onChanged={async () => { setProject(await getProject(project.id)); setPreviewKey((k) => k + 1); }}
              />
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function TabBtn({ id, active, onClick, Icon, label }) {
  const a = active === id;
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-[11px] font-data uppercase tracking-widest border transition-all ${
        a ? "border-cyan-400 text-cyan-100 bg-cyan-500/10 shadow-[0_0_10px_rgba(0,229,255,0.25)]"
          : "border-transparent text-cyan-600 hover:text-cyan-300"
      }`}
      data-testid={`builder-tab-${id}`}
    >
      <Icon size={12} /> {label}
    </button>
  );
}

function ChatHistory({ messages }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [messages]);
  return (
    <div ref={ref} className="flex-1 overflow-y-auto scroll-tech p-3 space-y-3" data-testid="builder-chat-history">
      {messages.length === 0 && (
        <div className="text-cyan-700 text-xs font-data leading-relaxed">
          <div className="mb-2 text-cyan-400 uppercase tracking-widest text-[10px]">// dica</div>
          Peça exemplos como:<br />
          {'• "Crie uma landing page de SaaS com hero e 3 features"'}<br />
          {'• "Adicione um formulário de contato com validação"'}<br />
          {'• "Mude as cores para roxo e preto"'}<br />
          {'• "Inclua um jogo de Snake em canvas"'}
        </div>
      )}
      {messages.map((m, i) => (
        <div key={i} className={`text-xs font-data leading-relaxed ${m.role === "user" ? "" : "border-l-2 border-cyan-500/40 pl-2"}`}>
          <div className={`text-[10px] uppercase tracking-widest mb-0.5 ${m.role === "user" ? "text-cyan-400" : "text-emerald-300"}`}>
            {m.role === "user" ? "VOCÊ" : "BUILDER"}
            {m.pending && <Loader2 className="inline ml-2 animate-spin" size={10} />}
          </div>
          <div className="text-slate-200 whitespace-pre-wrap">{m.content}</div>
          {m.changes && m.changes.length > 0 && (
            <div className="text-[10px] text-cyan-500 mt-1">arquivos: {m.changes.join(", ")}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function CodeTab({ files, activeFile, onSelectFile, onChange, onAddFile, onDeleteFile, dirty }) {
  const paths = Object.keys(files).sort();
  return (
    <div className="h-full grid grid-cols-[200px_minmax(0,1fr)]">
      <div className="border-r border-cyan-500/15 bg-black/30 overflow-y-auto scroll-tech">
        <div className="flex items-center justify-between px-2 py-1.5 border-b border-cyan-500/10">
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 flex items-center gap-1.5"><Folder size={10} /> Arquivos</div>
          <button onClick={onAddFile} className="text-cyan-300 hover:text-white" title="Adicionar arquivo">
            <FilePlus size={12} />
          </button>
        </div>
        {paths.map((p) => (
          <div
            key={p}
            onClick={() => onSelectFile(p)}
            className={`group flex items-center justify-between px-2 py-1.5 text-xs font-data cursor-pointer border-b border-cyan-500/5 ${activeFile === p ? "bg-cyan-500/10 text-cyan-100" : "text-cyan-400 hover:text-cyan-200 hover:bg-cyan-500/5"}`}
            data-testid={`builder-file-${p}`}
          >
            <span className="truncate flex items-center gap-1.5">
              {dirty[p] !== undefined && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
              {p}
            </span>
            <button onClick={(e) => { e.stopPropagation(); onDeleteFile(p); }} className="opacity-0 group-hover:opacity-100 text-red-400/70 hover:text-red-400" title="Remover">
              <Trash2 size={11} />
            </button>
          </div>
        ))}
      </div>
      <div className="min-h-0">
        {activeFile ? (
          <Editor
            height="100%"
            theme="vs-dark"
            language={fileLanguage(activeFile)}
            value={files[activeFile] ?? ""}
            onChange={onChange}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "JetBrains Mono, monospace",
              automaticLayout: true,
              wordWrap: "on",
              scrollBeyondLastLine: false,
            }}
          />
        ) : (
          <div className="h-full flex items-center justify-center text-cyan-700 text-xs font-data uppercase tracking-widest">
            Nenhum arquivo selecionado
          </div>
        )}
      </div>
    </div>
  );
}

function ConsoleTab({ logs, onClear }) {
  const ref = useRef(null);
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [logs]);
  return (
    <div className="h-full flex flex-col bg-black">
      <div className="px-3 py-1.5 border-b border-cyan-500/10 flex items-center justify-between">
        <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400">Console do Preview</div>
        <button className="glass-btn" onClick={onClear}><Trash2 size={10} /> Limpar</button>
      </div>
      <div ref={ref} className="flex-1 overflow-y-auto scroll-tech p-3 font-data text-xs space-y-1">
        {logs.length === 0 && <div className="text-cyan-700">// aguardando logs do preview…</div>}
        {logs.map((l, i) => (
          <div key={i} className={
            l.level === "error" ? "text-red-300" :
            l.level === "warn" ? "text-amber-300" :
            l.level === "info" ? "text-sky-300" : "text-slate-300"
          }>
            <span className="text-cyan-600 mr-2">[{new Date(l.ts).toLocaleTimeString("pt-BR")}]</span>
            <span className="uppercase mr-2 text-[10px]">{l.level}</span>
            {l.msg}
          </div>
        ))}
      </div>
    </div>
  );
}

function openInNewTab(html) {
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank", "noopener");
  if (w) setTimeout(() => URL.revokeObjectURL(url), 60_000);
}


// ============ New Project Modal ============
function NewProjectModal({ templates, onClose, onCreate }) {
  const [name, setName] = useState("");
  const [tplId, setTplId] = useState("blank");
  return (
    <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur flex items-center justify-center p-4" data-testid="new-project-modal">
      <div className="hud-panel w-[560px] max-w-full max-h-[85vh]">
        <div className="px-5 pt-4 pb-2 flex items-center justify-between shrink-0">
          <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs">Novo Projeto</h3>
          <button onClick={onClose} className="text-cyan-300 hover:text-white"><X size={16} /></button>
        </div>
        <div className="hud-body px-5 pb-5">
          <label className="block text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-1">Nome</label>
          <input
            value={name} onChange={(e) => setName(e.target.value)} autoFocus
            placeholder="Ex.: Meu site, Calculadora, Portfolio…"
            className="w-full bg-black/60 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400 mb-4"
            data-testid="new-project-name"
          />
          <div className="text-[10px] font-data uppercase tracking-widest text-cyan-400 mb-2">Template</div>
          <div className="grid grid-cols-1 gap-2">
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => setTplId(t.id)}
                className={`text-left border rounded p-3 transition-colors ${tplId === t.id ? "border-cyan-400 bg-cyan-500/10" : "border-cyan-500/20 hover:border-cyan-400/60"}`}
                data-testid={`template-${t.id}`}
              >
                <div className="text-sm font-data text-cyan-200 font-semibold flex items-center gap-2">
                  {tplId === t.id && <Check size={12} className="text-cyan-300" />} {t.name}
                </div>
                <div className="text-xs font-data text-slate-400 mt-0.5">{t.description}</div>
              </button>
            ))}
          </div>
          <div className="flex justify-end gap-2 mt-5">
            <button className="glass-btn" onClick={onClose}>Cancelar</button>
            <button className="glass-btn" onClick={() => onCreate(name.trim() || "Novo Projeto", tplId)} data-testid="new-project-create">
              <Plus size={14} /> Criar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Snapshots Modal ============
function SnapshotsModal({ projectId, onClose, onRestored }) {
  const [snaps, setSnaps] = useState([]);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try { setSnaps(await listSnapshots(projectId)); } catch (_) { /* keep */ }
  }
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [projectId]);

  async function create() {
    setBusy(true);
    try { await createSnapshot(projectId, label.trim()); setLabel(""); await refresh(); }
    catch (e) { console.error(e); }
    setBusy(false);
  }
  async function restore(id) {
    if (!window.confirm("Restaurar este snapshot? O estado atual será substituído.")) return;
    setBusy(true);
    try { await restoreSnapshot(projectId, id); onRestored && onRestored(); }
    catch (e) { console.error(e); }
    setBusy(false);
  }
  async function del(id) {
    if (!window.confirm("Apagar snapshot?")) return;
    setBusy(true);
    try { await deleteSnapshot(projectId, id); await refresh(); }
    catch (e) { console.error(e); }
    setBusy(false);
  }

  return (
    <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur flex items-center justify-center p-4" data-testid="snapshots-modal">
      <div className="hud-panel w-[640px] max-w-full max-h-[85vh]">
        <div className="px-5 pt-4 pb-2 flex items-center justify-between shrink-0">
          <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs flex items-center gap-2"><GitBranch size={14} /> Snapshots (versões)</h3>
          <button onClick={onClose} className="text-cyan-300 hover:text-white"><X size={16} /></button>
        </div>
        <div className="hud-body px-5 pb-5">
          <div className="flex gap-2 mb-4">
            <input
              value={label} onChange={(e) => setLabel(e.target.value)}
              placeholder="Rótulo opcional (ex.: 'antes de adicionar dark mode')"
              className="flex-1 bg-black/60 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
              data-testid="snapshot-label"
            />
            <button className="glass-btn" onClick={create} disabled={busy} data-testid="snapshot-create">
              {busy ? <Loader2 className="animate-spin" size={14} /> : <Plus size={14} />} Criar Snapshot
            </button>
          </div>
          {snaps.length === 0 && <div className="text-cyan-700 text-xs font-data text-center py-6">Nenhum snapshot ainda. Crie um para preservar o estado atual.</div>}
          <div className="space-y-2">
            {snaps.map((s) => (
              <div key={s.id} className="flex items-center justify-between border border-cyan-500/15 rounded p-3 hover:border-cyan-400/40">
                <div className="min-w-0">
                  <div className="text-sm font-data text-cyan-100 truncate">{s.label}</div>
                  <div className="text-[10px] font-data text-cyan-700">{new Date(s.ts).toLocaleString("pt-BR")} — {s.file_count} arquivos</div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button className="glass-btn" onClick={() => restore(s.id)} disabled={busy} data-testid={`snapshot-restore-${s.id}`}>
                    <RotateCcw size={12} /> Restaurar
                  </button>
                  <button className="glass-btn danger" onClick={() => del(s.id)} disabled={busy}>
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Publish Modal ============
function PublishModal({ project, onClose, onChange }) {
  const [slug, setSlug] = useState(project.public_slug || "");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const currentUrl = project.public_slug ? publicProjectUrl(project.public_slug) : null;

  async function doPublish() {
    setBusy(true);
    try {
      const r = await publishProject(project.id, slug.trim());
      onChange({ ...project, public_slug: r.slug });
    } catch (e) { console.error(e); }
    setBusy(false);
  }
  async function doUnpublish() {
    if (!window.confirm("Despublicar este site? O link público deixará de funcionar.")) return;
    setBusy(true);
    try { await unpublishProject(project.id); onChange({ ...project, public_slug: null }); }
    catch (e) { console.error(e); }
    setBusy(false);
  }
  async function copy() {
    if (!currentUrl) return;
    try { await navigator.clipboard.writeText(currentUrl); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch (_) { /* ignore */ }
  }

  return (
    <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur flex items-center justify-center p-4" data-testid="publish-modal">
      <div className="hud-panel w-[560px] max-w-full max-h-[85vh]">
        <div className="px-5 pt-4 pb-2 flex items-center justify-between shrink-0">
          <h3 className="font-heading uppercase tracking-[0.3em] text-cyan-300 text-xs flex items-center gap-2"><Globe size={14} /> Publicar Site</h3>
          <button onClick={onClose} className="text-cyan-300 hover:text-white"><X size={16} /></button>
        </div>
        <div className="hud-body px-5 pb-5 space-y-3">
          <div className="text-xs font-data text-slate-300 leading-relaxed">
            Gera uma URL pública (sem login) que qualquer pessoa pode acessar. O conteúdo refletirá o último estado salvo deste projeto.
          </div>
          <label className="block text-[10px] font-data uppercase tracking-widest text-cyan-400">Slug (opcional)</label>
          <input
            value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
            placeholder={(project.name || "site").toLowerCase().replace(/[^a-z0-9-]/g, "-")}
            className="w-full bg-black/60 border border-cyan-500/30 rounded px-3 py-2 text-sm text-cyan-100 font-data outline-none focus:border-cyan-400"
            data-testid="publish-slug"
          />
          {currentUrl && (
            <div className="border border-emerald-500/30 bg-emerald-500/5 rounded p-3" data-testid="publish-current-url">
              <div className="text-[10px] font-data uppercase tracking-widest text-emerald-300 mb-1">Site publicado em:</div>
              <div className="flex items-center gap-2">
                <a href={currentUrl} target="_blank" rel="noopener noreferrer" className="text-sm font-data text-emerald-200 hover:underline truncate flex-1">{currentUrl}</a>
                <button className="glass-btn" onClick={copy}>{copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Copiado" : "Copiar"}</button>
                <a className="glass-btn" href={currentUrl} target="_blank" rel="noopener noreferrer"><ExternalLink size={12} /></a>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            {currentUrl && (
              <button className="glass-btn danger" onClick={doUnpublish} disabled={busy} data-testid="publish-unpublish">
                {busy ? <Loader2 className="animate-spin" size={14} /> : <X size={14} />} Despublicar
              </button>
            )}
            <button className="glass-btn" onClick={doPublish} disabled={busy} data-testid="publish-confirm" style={{ borderColor: "rgba(0,255,157,0.5)", color: "#86efac" }}>
              {busy ? <Loader2 className="animate-spin" size={14} /> : <Globe size={14} />} {currentUrl ? "Atualizar publicação" : "Publicar agora"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ Assets Tab ============
function AssetsTab({ project, onChanged }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const assets = project.assets || {};
  const entries = Object.entries(assets);

  async function handleFiles(files) {
    if (!files || files.length === 0) return;
    setBusy(true);
    for (const f of files) {
      const path = `assets/${f.name}`;
      try { await uploadAsset(project.id, f, path); } catch (e) { console.error(e); }
    }
    setBusy(false);
    onChanged && onChanged();
  }
  async function del(path) {
    if (!window.confirm(`Remover asset "${path}"?`)) return;
    try { await deleteAsset(project.id, path); onChanged && onChanged(); } catch (e) { console.error(e); }
  }

  return (
    <div className="h-full flex flex-col" data-testid="builder-assets-tab">
      <div className="px-4 py-3 border-b border-cyan-500/10 flex items-center gap-2 shrink-0">
        <input ref={inputRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => handleFiles(Array.from(e.target.files || []))} data-testid="asset-file-input" />
        <button className="glass-btn" onClick={() => inputRef.current?.click()} disabled={busy} data-testid="asset-upload-btn">
          {busy ? <Loader2 className="animate-spin" size={14} /> : <Upload size={14} />} Enviar Imagens
        </button>
        <div className="text-[10px] font-data uppercase tracking-widest text-cyan-700">
          PNG, JPG, WebP, GIF — referencie no código como <span className="text-cyan-400">{`<img src="assets/nome.png">`}</span>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {entries.length === 0 ? (
          <div className="text-center text-cyan-700 text-xs font-data uppercase tracking-widest py-16">
            Nenhum asset. Envie imagens para usar no projeto.
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {entries.map(([path, meta]) => (
              <div key={path} className="border border-cyan-500/20 rounded overflow-hidden bg-black/30 group">
                <div className="aspect-square bg-black/50 flex items-center justify-center overflow-hidden">
                  {(meta.mime || "").startsWith("image/") ? (
                    <img src={`data:${meta.mime};base64,${meta.b64}`} alt={path} className="w-full h-full object-cover" />
                  ) : (
                    <div className="text-cyan-700 text-xs font-data">{meta.mime}</div>
                  )}
                </div>
                <div className="p-2">
                  <div className="text-[11px] font-data text-cyan-200 truncate" title={path}>{path}</div>
                  <div className="flex justify-between mt-1">
                    <div className="text-[10px] font-data text-cyan-700">{(meta.size / 1024).toFixed(1)} KB</div>
                    <button className="text-red-400/70 hover:text-red-400" onClick={() => del(path)} title="Remover" data-testid={`asset-del-${path}`}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
