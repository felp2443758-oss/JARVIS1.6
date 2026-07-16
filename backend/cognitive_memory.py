"""Persistent Cognitive Profile (memory compaction).

After each conversation turn, asynchronously distill recent user/assistant exchanges
into a compact dossier of preferences, recurring people/topics, and active tasks.
This dossier is injected into the system prompt of future sessions so JARVIS
"remembers" the operator across sessions.
"""
from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("jarvis.memory")

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

COMPACT_SYSTEM = (
    "Você é um destilador de memória de longo prazo do J.A.R.V.I.S. "
    "Receba o perfil atual (JSON) e mensagens recentes. Retorne APENAS um JSON válido "
    "com as chaves:\n"
    "- preferences (lista curta de strings)\n"
    "- people (lista de objetos {name, relation, notes})\n"
    "- topics (lista de strings — tópicos recorrentes)\n"
    "- active_tasks (lista curta de strings — coisas pendentes mencionadas)\n"
    "- summary (string com ~2 frases descrevendo o usuário)\n"
    "Funda informações novas com o perfil existente, removendo redundâncias. "
    "Mantenha o JSON compacto (no máx ~120 palavras). NÃO inclua texto fora do JSON."
)


async def compact_memory(db, user_id: str, recent_msgs: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Update the cognitive profile for `user_id` using the last N messages."""
    if not EMERGENT_LLM_KEY or not recent_msgs:
        return None

    existing = await db.cognitive_profiles.find_one({"user_id": user_id}, {"_id": 0}) or {}
    existing_doc = {k: existing.get(k) for k in ("preferences", "people", "topics", "active_tasks", "summary")}

    convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent_msgs[-12:])
    prompt = (
        f"Perfil atual:\n{json.dumps(existing_doc, ensure_ascii=False)}\n\n"
        f"Mensagens recentes:\n{convo}\n\n"
        f"Retorne o JSON atualizado."
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"compact-{user_id}",
        system_message=COMPACT_SYSTEM,
    ).with_model("gemini", "gemini-2.5-flash")

    try:
        raw = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.warning(f"compact_memory llm error: {e}")
        return None

    if not raw:
        return None
    # Strip code fences if present
    t = raw.strip()
    if t.startswith("```"):
        t = t.strip("`")
        # remove leading 'json\n'
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    try:
        data = json.loads(t)
    except Exception as e:
        logger.warning(f"compact_memory parse failed: {e} :: {raw[:200]}")
        return None

    doc = {
        "user_id": user_id,
        "preferences": data.get("preferences") or [],
        "people": data.get("people") or [],
        "topics": data.get("topics") or [],
        "active_tasks": data.get("active_tasks") or [],
        "summary": data.get("summary") or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cognitive_profiles.replace_one({"user_id": user_id}, doc, upsert=True)
    return doc


async def get_profile(db, user_id: str) -> Optional[Dict[str, Any]]:
    return await db.cognitive_profiles.find_one({"user_id": user_id}, {"_id": 0})


def profile_to_prompt(profile: Optional[Dict[str, Any]]) -> str:
    if not profile:
        return ""
    parts = []
    if profile.get("summary"):
        parts.append(f"Sobre o usuário: {profile['summary']}")
    prefs = profile.get("preferences") or []
    if prefs:
        parts.append(f"Preferências conhecidas: {', '.join(prefs[:8])}.")
    people = profile.get("people") or []
    if people:
        ppl = "; ".join(f"{p.get('name','?')} ({p.get('relation','')})" for p in people[:6])
        parts.append(f"Pessoas próximas: {ppl}.")
    topics = profile.get("topics") or []
    if topics:
        parts.append(f"Tópicos recorrentes: {', '.join(topics[:8])}.")
    tasks = profile.get("active_tasks") or []
    if tasks:
        parts.append(f"Tarefas em aberto: {', '.join(tasks[:6])}.")
    return "\n".join(parts)
