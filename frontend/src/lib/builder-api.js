// Builder API helpers
import { api, API } from "@/lib/api";

export async function listProjects() {
  const r = await api.get("/builder/projects");
  return r.data;
}
export async function getProject(id) {
  const r = await api.get(`/builder/projects/${id}`);
  return r.data;
}
export async function listTemplates() {
  const r = await api.get("/builder/templates");
  return r.data;
}
export async function createProject(name = "Novo Projeto", description = "", template = "blank") {
  const r = await api.post("/builder/projects", { name, description, template });
  return r.data;
}
export async function deleteProject(id) {
  const r = await api.delete(`/builder/projects/${id}`);
  return r.data;
}
export async function renameProject(id, name, description) {
  const r = await api.put(`/builder/projects/${id}`, { name, description });
  return r.data;
}
export async function saveProjectFiles(id, files, deletes = []) {
  const r = await api.put(`/builder/projects/${id}/files`, { files, deletes });
  return r.data;
}
export async function builderChat(id, message) {
  const r = await api.post(`/builder/projects/${id}/chat`, { message }, { timeout: 120000 });
  return r.data;
}

// Snapshots
export async function listSnapshots(id) {
  const r = await api.get(`/builder/projects/${id}/snapshots`);
  return r.data;
}
export async function createSnapshot(id, label) {
  const r = await api.post(`/builder/projects/${id}/snapshots`, { label });
  return r.data;
}
export async function restoreSnapshot(id, snapshotId) {
  const r = await api.post(`/builder/projects/${id}/snapshots/${snapshotId}/restore`);
  return r.data;
}
export async function deleteSnapshot(id, snapshotId) {
  const r = await api.delete(`/builder/projects/${id}/snapshots/${snapshotId}`);
  return r.data;
}

// Assets
export async function uploadAsset(id, file, path) {
  const form = new FormData();
  form.append("file", file);
  const url = path ? `${API}/builder/projects/${id}/assets?path=${encodeURIComponent(path)}` : `${API}/builder/projects/${id}/assets`;
  const resp = await fetch(url, { method: "POST", body: form });
  if (!resp.ok) throw new Error(`Upload HTTP ${resp.status}`);
  return await resp.json();
}
export async function deleteAsset(id, path) {
  const r = await api.delete(`/builder/projects/${id}/assets`, { params: { path } });
  return r.data;
}

// Publish
export async function publishProject(id, slug = "") {
  const r = await api.post(`/builder/projects/${id}/publish`, { slug });
  return r.data;
}
export async function unpublishProject(id) {
  const r = await api.post(`/builder/projects/${id}/unpublish`);
  return r.data;
}
export function publicProjectUrl(slug) {
  return `${API}/public/${slug}`;
}

export function downloadProjectZipUrl(id) {
  return `${API}/builder/projects/${id}/download`;
}

/**
 * Build a single-document HTML string from a project files map suitable
 * for an <iframe srcdoc>. Inlines local .css and .js references found in
 * index.html via href="X.css" / src="Y.js". External URLs (http/https) stay.
 * Replaces asset paths (image/binary) with data: URLs.
 */
export function buildPreviewSrcDoc(files, assets) {
  if (!files || !files["index.html"]) {
    return "<!doctype html><meta charset='utf-8'><body style='background:#020617;color:#fff;font-family:monospace;padding:20px'>Sem index.html neste projeto.</body>";
  }
  let html = files["index.html"];

  // Inline <link rel="stylesheet" href="X.css">
  html = html.replace(/<link[^>]*href=["']([^"']+\.css)["'][^>]*>/gi, (match, href) => {
    if (/^https?:\/\//i.test(href)) return match;
    const content = files[href] || files[href.replace(/^\.\//, "")] || "";
    return content ? `<style data-from="${href}">\n${content}\n</style>` : match;
  });

  // Inline <script src="Y.js"></script>
  html = html.replace(/<script[^>]*src=["']([^"']+\.js)["'][^>]*><\/script>/gi, (match, src) => {
    if (/^https?:\/\//i.test(src)) return match;
    const content = files[src] || files[src.replace(/^\.\//, "")] || "";
    return content ? `<script data-from="${src}">\n${content}\n</script>` : match;
  });

  // Replace asset references (images, etc.) with data: URLs
  if (assets) {
    Object.entries(assets).forEach(([path, meta]) => {
      if (!meta || !meta.b64) return;
      const dataUrl = `data:${meta.mime || "application/octet-stream"};base64,${meta.b64}`;
      html = html.split(`"${path}"`).join(`"${dataUrl}"`).split(`'${path}'`).join(`'${dataUrl}'`);
    });
  }

  // Inject base console-bridge so the parent can capture preview logs/errors (optional, used by ConsolePane)
  const bridge = `<script>(function(){
    function send(level,args){try{parent.postMessage({__jarvis_preview:true,level,ts:Date.now(),msg:Array.from(args).map(a=>{try{return typeof a==='object'?JSON.stringify(a):String(a)}catch(_){return String(a)}}).join(' ')},'*')}catch(_){}}
    ['log','warn','error','info'].forEach(k=>{const o=console[k];console[k]=function(){send(k,arguments);return o.apply(console,arguments)}});
    window.addEventListener('error',e=>send('error',[e.message+' @'+(e.filename||'?')+':'+(e.lineno||'?')]));
    window.addEventListener('unhandledrejection',e=>send('error',['Unhandled: '+(e.reason&&e.reason.message||e.reason)]));
  })();</script>`;
  // Inject just before </head> if possible
  if (/<\/head>/i.test(html)) html = html.replace(/<\/head>/i, `${bridge}</head>`);
  else html = bridge + html;

  return html;
}

export function fileLanguage(path) {
  const p = (path || "").toLowerCase();
  if (p.endsWith(".html") || p.endsWith(".htm")) return "html";
  if (p.endsWith(".css")) return "css";
  if (p.endsWith(".js") || p.endsWith(".mjs") || p.endsWith(".jsx")) return "javascript";
  if (p.endsWith(".ts") || p.endsWith(".tsx")) return "typescript";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".md")) return "markdown";
  if (p.endsWith(".py")) return "python";
  if (p.endsWith(".svg") || p.endsWith(".xml")) return "xml";
  return "plaintext";
}
