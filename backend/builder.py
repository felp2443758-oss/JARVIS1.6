"""JARVIS Builder Mode — project workspace with LLM-driven code generation.

Static web project sandbox: HTML/CSS/JS (Tailwind via CDN), built and edited by Gemini.
Projects are persisted in MongoDB as a map of {filepath: content}.
"""
from __future__ import annotations
import os
import json
import uuid
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("jarvis.builder")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


BUILDER_SYSTEM = (
    "Você é o JARVIS Builder — um agente de engenharia de software autônomo do J.A.R.V.I.S. "
    "Sua tarefa é construir/modificar projetos web ESTÁTICOS (HTML/CSS/JS) executáveis num iframe sandbox.\n\n"
    "REGRAS ESTRITAS:\n"
    "1. Responda SEMPRE em JSON válido seguindo o schema abaixo. Nenhum texto fora do JSON.\n"
    "2. Use Tailwind via CDN para estilo quando útil (<script src=\"https://cdn.tailwindcss.com\"></script>).\n"
    "3. Use somente bibliotecas via CDN (no npm). Sempre que possível, deixe o app funcional sem rede.\n"
    "4. Mantenha estrutura: index.html (entry), styles.css, app.js, e arquivos adicionais conforme necessário.\n"
    "5. Para imagens, use placeholders de https://picsum.photos/SEED ou https://images.unsplash.com/.\n"
    "6. NUNCA omita arquivos existentes que não foram alterados. Sempre devolva apenas os arquivos NOVOS ou MODIFICADOS.\n"
    "7. Para REMOVER um arquivo, inclua-o em \"deletes\".\n"
    "8. Faça UI moderna, responsiva e bonita (paleta escura cyber por padrão, salvo se o usuário pedir outra estética).\n"
    "9. Mantenha JavaScript puro/vanilla a menos que o usuário peça React/Vue (que então também via CDN ESM ou compiladores in-browser como Babel standalone).\n\n"
    "SCHEMA DA RESPOSTA (JSON):\n"
    "{\n"
    '  "explanation": "Resumo curto em PT-BR do que foi feito (1-3 frases)",\n'
    '  "files": {\n'
    '    "index.html": "<!doctype html>...",\n'
    '    "styles.css": "...",\n'
    '    "app.js": "..."\n'
    "  },\n"
    '  "deletes": []\n'
    "}\n"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- DB helpers ----------
async def list_projects(db, user_id: str = "owner", limit: int = 50) -> List[Dict[str, Any]]:
    cur = db.builder_projects.find({"user_id": user_id}, {"_id": 0, "files": 0, "messages": 0}).sort("updated_at", -1).limit(limit)
    return await cur.to_list(limit)


async def get_project(db, project_id: str) -> Optional[Dict[str, Any]]:
    return await db.builder_projects.find_one({"id": project_id}, {"_id": 0})


async def create_project(db, name: str, description: str = "", user_id: str = "owner", template: str = "blank") -> Dict[str, Any]:
    from builder_templates import get_template_files
    pid = str(uuid.uuid4())
    doc = {
        "id": pid,
        "user_id": user_id,
        "name": name or "Novo Projeto",
        "description": description or "",
        "files": get_template_files(template, name or "Projeto"),
        "messages": [],
        "snapshots": [],
        "assets": {},
        "public_slug": None,
        "template": template or "blank",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.builder_projects.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


async def update_files(db, project_id: str, files: Dict[str, str], deletes: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return None
    current = dict(proj.get("files") or {})
    if files:
        current.update(files)
    if deletes:
        for d in deletes:
            current.pop(d, None)
    await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {"files": current, "updated_at": now_iso()}},
    )
    proj["files"] = current
    proj["updated_at"] = now_iso()
    proj.pop("_id", None)
    return proj


# ---------- Snapshots ----------
async def create_snapshot(db, project_id: str, label: str = "") -> Optional[Dict[str, Any]]:
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return None
    snap = {
        "id": str(uuid.uuid4()),
        "label": label or f"Snapshot {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        "files": proj.get("files") or {},
        "assets": proj.get("assets") or {},
        "ts": now_iso(),
    }
    await db.builder_projects.update_one(
        {"id": project_id},
        {"$push": {"snapshots": snap}, "$set": {"updated_at": now_iso()}},
    )
    return snap


async def list_snapshots(db, project_id: str) -> List[Dict[str, Any]]:
    proj = await db.builder_projects.find_one({"id": project_id}, {"snapshots": 1})
    if not proj:
        return []
    snaps = proj.get("snapshots") or []
    # return without bulky files for listing
    return [{"id": s["id"], "label": s.get("label"), "ts": s.get("ts"), "file_count": len(s.get("files") or {})} for s in snaps]


async def restore_snapshot(db, project_id: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return None
    snaps = proj.get("snapshots") or []
    snap = next((s for s in snaps if s["id"] == snapshot_id), None)
    if not snap:
        return None
    await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {
            "files": snap.get("files") or {},
            "assets": snap.get("assets") or {},
            "updated_at": now_iso(),
        }},
    )
    return await get_project(db, project_id)


async def delete_snapshot(db, project_id: str, snapshot_id: str) -> bool:
    r = await db.builder_projects.update_one(
        {"id": project_id},
        {"$pull": {"snapshots": {"id": snapshot_id}}, "$set": {"updated_at": now_iso()}},
    )
    return r.modified_count > 0


# ---------- Assets (images/binaries) ----------
async def upload_asset(db, project_id: str, path: str, content_b64: str, mime: str) -> Optional[Dict[str, Any]]:
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return None
    assets = dict(proj.get("assets") or {})
    assets[path] = {"b64": content_b64, "mime": mime, "size": len(content_b64) * 3 // 4}
    await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {"assets": assets, "updated_at": now_iso()}},
    )
    return {"path": path, "mime": mime, "size": assets[path]["size"]}


async def delete_asset(db, project_id: str, path: str) -> bool:
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return False
    assets = dict(proj.get("assets") or {})
    if path not in assets:
        return False
    del assets[path]
    await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {"assets": assets, "updated_at": now_iso()}},
    )
    return True


# ---------- Public publish ----------
def _slugify(text: str) -> str:
    import re as _re
    s = (text or "").lower().strip()
    s = _re.sub(r"[^a-z0-9\-]+", "-", s)
    s = _re.sub(r"-+", "-", s).strip("-")
    return s or "site"


async def publish_project(db, project_id: str, custom_slug: str = "") -> Optional[Dict[str, Any]]:
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return None
    base = _slugify(custom_slug or proj.get("name") or "site")
    slug = base
    # Ensure uniqueness
    suffix = 1
    while True:
        existing = await db.builder_projects.find_one({"public_slug": slug, "id": {"$ne": project_id}})
        if not existing:
            break
        suffix += 1
        slug = f"{base}-{suffix}"
    await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {"public_slug": slug, "published_at": now_iso(), "updated_at": now_iso()}},
    )
    return {"slug": slug, "project_id": project_id}


async def unpublish_project(db, project_id: str) -> bool:
    r = await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {"public_slug": None, "updated_at": now_iso()}},
    )
    return r.modified_count > 0


async def get_public_project(db, slug: str) -> Optional[Dict[str, Any]]:
    return await db.builder_projects.find_one({"public_slug": slug}, {"_id": 0})


def render_preview_html(files: Dict[str, str], assets: Optional[Dict[str, Any]] = None) -> str:
    """Server-side render of preview HTML for the /public route.
    Inlines local CSS/JS references; replaces asset paths with data: URLs.
    """
    if not files or "index.html" not in files:
        return "<!doctype html><meta charset='utf-8'><body>Sem index.html.</body>"
    html = files["index.html"]
    import re as _re
    # Inline CSS
    def _css(m):
        href = m.group(1)
        if _re.match(r"^https?://", href):
            return m.group(0)
        content = files.get(href) or files.get(href.lstrip("./")) or ""
        return f'<style data-from="{href}">\n{content}\n</style>' if content else m.group(0)
    html = _re.sub(r"<link[^>]*href=[\"']([^\"']+\.css)[\"'][^>]*>", _css, html, flags=_re.IGNORECASE)
    # Inline JS
    def _js(m):
        src = m.group(1)
        if _re.match(r"^https?://", src):
            return m.group(0)
        content = files.get(src) or files.get(src.lstrip("./")) or ""
        return f'<script data-from="{src}">\n{content}\n</script>' if content else m.group(0)
    html = _re.sub(r"<script[^>]*src=[\"']([^\"']+\.js)[\"'][^>]*></script>", _js, html, flags=_re.IGNORECASE)
    # Replace asset references with data URLs
    if assets:
        for path, meta in assets.items():
            if not isinstance(meta, dict):
                continue
            data_url = f"data:{meta.get('mime','application/octet-stream')};base64,{meta.get('b64','')}"
            # Replace both bare path and relative
            html = html.replace(f'"{path}"', f'"{data_url}"').replace(f"'{path}'", f"'{data_url}'")
    return html


async def delete_project(db, project_id: str) -> bool:
    r = await db.builder_projects.delete_one({"id": project_id})
    return r.deleted_count > 0


async def rename_project(db, project_id: str, name: str, description: str = "") -> Optional[Dict[str, Any]]:
    update = {"updated_at": now_iso()}
    if name:
        update["name"] = name
    if description is not None:
        update["description"] = description
    await db.builder_projects.update_one({"id": project_id}, {"$set": update})
    return await get_project(db, project_id)


# ---------- LLM build ----------
def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Robust JSON extraction tolerating ```json fences and pre/post chatter."""
    if not text:
        return None
    t = text.strip()
    # strip code fences
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
        # remove trailing fence if any
        if t.endswith("```"):
            t = t[:-3].rstrip()
    # find first { ... last }
    first = t.find("{")
    last = t.rfind("}")
    if first == -1 or last == -1 or last <= first:
        return None
    candidate = t[first : last + 1]
    try:
        return json.loads(candidate)
    except Exception:
        # Try fixing common issues
        candidate2 = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            return json.loads(candidate2)
        except Exception:
            return None


def _files_summary(files: Dict[str, str], max_chars_per_file: int = 1200) -> str:
    parts = []
    for path, content in (files or {}).items():
        truncated = (content or "")[:max_chars_per_file]
        parts.append(f"### {path}\n```\n{truncated}\n```")
        if len(content or "") > max_chars_per_file:
            parts.append(f"(arquivo truncado em {max_chars_per_file} chars / total {len(content)})")
    return "\n\n".join(parts) if parts else "(projeto ainda vazio)"


async def builder_chat(db, project_id: str, user_message: str) -> Dict[str, Any]:
    """Sends user message + current project state to Gemini, parses JSON, updates files."""
    if not EMERGENT_LLM_KEY:
        return {"error": "EMERGENT_LLM_KEY missing"}
    proj = await db.builder_projects.find_one({"id": project_id})
    if not proj:
        return {"error": "project_not_found"}
    files = proj.get("files") or {}
    history = proj.get("messages") or []

    history_text = "\n".join(f"{m['role'].upper()}: {m['content'][:400]}" for m in history[-6:])

    prompt = (
        f"## Pedido do operador\n{user_message}\n\n"
        f"## Estado atual do projeto '{proj.get('name','')}'\n"
        f"{_files_summary(files)}\n\n"
        f"## Histórico recente\n{history_text or '(novo projeto)'}\n\n"
        "Responda APENAS com o JSON conforme o schema."
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"builder-{project_id}",
        system_message=BUILDER_SYSTEM,
    ).with_model("gemini", "gemini-2.5-flash")

    try:
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.exception("builder chat llm failed")
        return {"error": f"llm_failed: {e}"}

    data = _extract_json(raw or "")
    if not data:
        return {"error": "json_parse_failed", "raw": (raw or "")[:1200]}

    new_files = data.get("files") or {}
    deletes = data.get("deletes") or []
    explanation = (data.get("explanation") or "").strip()

    if not new_files and not deletes:
        # No file change; just record assistant message
        await db.builder_projects.update_one(
            {"id": project_id},
            {"$push": {"messages": {"$each": [
                {"role": "user", "content": user_message, "ts": now_iso()},
                {"role": "assistant", "content": explanation or "(sem alterações)", "ts": now_iso()},
            ]}}, "$set": {"updated_at": now_iso()}},
        )
        updated = await db.builder_projects.find_one({"id": project_id}, {"_id": 0})
        return {
            "project": updated,
            "explanation": explanation or "(sem alterações)",
            "changed_files": [],
            "deleted_files": [],
        }

    # Apply changes
    current = dict(files)
    if new_files:
        current.update(new_files)
    for d in deletes:
        current.pop(d, None)

    await db.builder_projects.update_one(
        {"id": project_id},
        {"$set": {"files": current, "updated_at": now_iso()},
         "$push": {"messages": {"$each": [
            {"role": "user", "content": user_message, "ts": now_iso()},
            {"role": "assistant", "content": explanation or "(arquivos atualizados)", "ts": now_iso(), "changes": list(new_files.keys()), "deletes": deletes},
         ]}}},
    )
    updated = await db.builder_projects.find_one({"id": project_id}, {"_id": 0})
    return {
        "project": updated,
        "explanation": explanation or "(arquivos atualizados)",
        "changed_files": list(new_files.keys()),
        "deleted_files": deletes,
    }


# ---------- Default scaffold ----------
def _default_files(name: str) -> Dict[str, str]:
    title = name.strip() or "JARVIS Build"
    safe_title = title.replace("\"", "'")
    return {
        "index.html": (
            "<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n"
            "  <meta charset=\"utf-8\" />\n"
            "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
            f"  <title>{safe_title}</title>\n"
            "  <script src=\"https://cdn.tailwindcss.com\"></script>\n"
            "  <link rel=\"stylesheet\" href=\"styles.css\" />\n"
            "</head>\n<body class=\"bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center p-6\">\n"
            "  <div class=\"text-center max-w-xl\">\n"
            f"    <h1 class=\"text-4xl font-bold text-cyan-300 mb-3\">{safe_title}</h1>\n"
            "    <p class=\"text-slate-300 mb-6\">Projeto inicial gerado pelo J.A.R.V.I.S. Builder. Use o chat à esquerda para descrever o que deseja construir.</p>\n"
            "    <button id=\"hello\" class=\"px-5 py-2 rounded bg-cyan-500/20 border border-cyan-400/60 text-cyan-200 hover:bg-cyan-500/30 transition\">Clique aqui</button>\n"
            "    <div id=\"out\" class=\"mt-4 text-cyan-400 font-mono text-sm\"></div>\n"
            "  </div>\n"
            "  <script src=\"app.js\"></script>\n"
            "</body>\n</html>\n"
        ),
        "styles.css": (
            "/* Estilos personalizados */\n"
            "body { font-family: 'Inter', system-ui, sans-serif; }\n"
        ),
        "app.js": (
            "document.getElementById('hello').addEventListener('click', () => {\n"
            "  document.getElementById('out').textContent = 'Pronto. Próximo passo: peça ao JARVIS Builder para evoluir este projeto.';\n"
            "});\n"
        ),
    }
