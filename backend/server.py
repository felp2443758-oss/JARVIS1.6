"""
J.A.R.V.I.S. Cloud Brain
FastAPI backend providing chat (Gemini 2.5 Flash), TTS (OpenAI tts-1),
STT (Whisper-1), face authentication (embedding-based), mock integrations
(weather/spotify/calendar) and a real-time WebSocket bridge for the Edge Agent.
"""
import os
import io
import json
import uuid
import base64
import logging
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date

from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId as _BsonObjectId
from pydantic import BaseModel, Field, ConfigDict
import numpy as np

# Load env BEFORE importing local modules that read environment at module level
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText

# Local modules
from google_integrations import (
    get_weather as google_get_weather,
    oauth_login_url, exchange_code, refresh_access_token, list_today_events,
    reverse_geocode,
)
from cognitive_memory import compact_memory, get_profile, profile_to_prompt
from tavily_integrations import quick_search, deep_research, image_search, format_results_for_llm
from vision_tools import analyze_image_bytes, analyze_image_url
from file_tools import convert_file
from builder import (
    list_projects as builder_list, get_project as builder_get,
    create_project as builder_create, update_files as builder_update_files,
    delete_project as builder_delete, rename_project as builder_rename,
    builder_chat,
    create_snapshot, list_snapshots, restore_snapshot, delete_snapshot,
    upload_asset, delete_asset,
    publish_project, unpublish_project, get_public_project, render_preview_html,
)
from builder_templates import list_templates, get_template_files
from media_tools import generate_image_gpt, generate_image_nano_banana, generate_video

# Multi-user auth + vault + command dispatch
from auth_service import (
    fetch_userinfo, upsert_user, issue_session_token, decode_token,
    issue_agent_token, decode_agent_token, current_user as _current_user,
)
from vault_service import (
    put_credential, list_credentials, get_credential, delete_credential,
)
from agent_commands import DISPATCHER, AGENT_COMMANDS


# ---------- Environment ----------

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
# GridFS bucket for large binary assets referenced by tool history (image_gen / video_gen)
TOOL_ASSETS_FS = AsyncIOMotorGridFSBucket(db, bucket_name="tool_assets")

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("jarvis")


# ---------- App + Router ----------
app = FastAPI(title="J.A.R.V.I.S. Cloud Brain")
api_router = APIRouter(prefix="/api")


# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def part_of_day_pt() -> str:
    """Returns greeting tokens for current part of day in Brazilian Portuguese."""
    h = datetime.now().hour
    if 5 <= h < 12:
        return "Bom dia"
    if 12 <= h < 18:
        return "Boa tarde"
    return "Boa noite"


JARVIS_SYSTEM_PROMPT = (
    "Você é J.A.R.V.I.S. — Just A Rather Very Intelligent System — o assistente pessoal "
    "do Felipe Hudson Stark. Características:\n"
    "- Fale em Português do Brasil, de forma elegante, concisa e levemente formal.\n"
    "- Trate o usuário como 'Felipe Stark' ou simplesmente 'Felipe' (nunca use Anthony, Tony ou outro nome).\n"
    "- Seja proativo, leal e ocasionalmente espirituoso, sem perder a sobriedade.\n"
    "- Respostas curtas (1 a 3 frases) para comandos diretos; mais detalhadas só quando o usuário pedir.\n"
    "- Quando o usuário pedir uma ação (abrir app, tocar música, pesquisar), confirme com objetividade.\n"
    "- NUNCA invente fatos. Se não houver dados verificados (agenda real, clima atual, busca web), "
    "  diga claramente que precisa que o operador conecte a fonte (ex.: 'Sua agenda do Google ainda "
    "  não está conectada — clique em GOOGLE no painel para autorizar') em vez de fornecer dados fictícios.\n"
    "- Quando contexto factual for fornecido no prompt (resultados de pesquisa, clima, agenda), use-o como verdade.\n"
    "- Nunca quebre o personagem.\n"
    "\n=== CAPACIDADES REAIS DO SISTEMA ===\n"
    "Você POSSUI as seguintes capacidades, executadas automaticamente pelo painel quando o operador pede:\n"
    "  • Abrir sites/apps no navegador do operador (Netflix, YouTube, Gmail, GitHub, ChatGPT, etc.) — basta pedir 'abra X'.\n"
    "  • Gerar imagens (OpenAI gpt-image-1 e Gemini Nano Banana).\n"
    "  • Gerar vídeos curtos (Fal.ai — Veo 3 Fast/Pro, Kling v2, Luma Dream Machine).\n"
    "  • Buscar imagens na web (Tavily).\n"
    "  • Pesquisar fatos / notícias na web (Tavily).\n"
    "  • Criar landing pages, sites e mini-apps no Builder Mode (HTML/CSS/JS com IA) e publicá-los com um clique.\n"
    "  • Analisar imagens (Vision via Gemini 2.5 Flash) e extrair texto de arquivos (PDF/DOCX/imagens).\n"
    "  • Tocar música no YouTube e ler agenda/clima reais.\n"
    "NUNCA diga frases como 'não consigo gerar imagens', 'não estou conectado a um motor de renderização', "
    "'não consigo abrir sites' ou 'não consigo criar uma landing page'. Você CONSEGUE — basta confirmar a ordem com elegância "
    "(ex.: 'Imediatamente, Felipe. Iniciando o processo agora.'); o painel mostrará o resultado visualmente."
)


# ---------- Models ----------
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class ChatStreamRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    user_id: Optional[str] = "owner"
    lat: Optional[float] = None
    lng: Optional[float] = None
    enable_tools: bool = True


class TTSRequest(BaseModel):
    text: str
    voice: str = "onyx"  # deep masculine voice fits JARVIS
    speed: float = 1.05
    model: str = "tts-1"


class FaceRegisterRequest(BaseModel):
    user_id: str
    name: str
    embedding: List[float]  # 128-d (face_recognition) or any vector


class FaceAuthRequest(BaseModel):
    embedding: List[float]
    threshold: float = 0.6  # max distance for match


class ActivationRequest(BaseModel):
    user_id: Optional[str] = "owner"
    transcript: Optional[str] = None  # e.g. "Bom dia, Jarvis"
    lat: Optional[float] = None
    lng: Optional[float] = None


# ---------- Routes: Health / Root ----------
@api_router.get("/")
async def root():
    return {"service": "J.A.R.V.I.S. Cloud Brain", "status": "online", "ts": now_iso()}


@api_router.get("/system/status")
async def system_status():
    # Active WS connections count
    ws_count = len(EDGE_AGENT_HUB.connections)
    return {
        "brain": "online",
        "llm_provider": "gemini-2.5-flash",
        "tts_provider": "openai-tts-1",
        "stt_provider": "whisper-1",
        "edge_agents_connected": ws_count,
        "timestamp": now_iso(),
    }


# ---------- Routes: Chat (streaming SSE) ----------
@api_router.post("/chat/session")
async def create_session(user_id: str = "owner"):
    session_id = str(uuid.uuid4())
    doc = {
        "id": session_id,
        "user_id": user_id,
        "created_at": now_iso(),
        "title": "Nova conversa",
    }
    await db.sessions.insert_one(doc)
    return {"session_id": session_id, "created_at": doc["created_at"]}


@api_router.get("/chat/sessions")
async def list_sessions(user_id: str = "owner", limit: int = 20):
    cursor = db.sessions.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return await cursor.to_list(limit)


@api_router.get("/chat/messages/{session_id}")
async def get_messages(session_id: str):
    cursor = db.messages.find({"session_id": session_id}, {"_id": 0}).sort("ts", 1)
    return await cursor.to_list(1000)


async def _persist_message(session_id: str, role: str, content: str):
    await db.messages.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "role": role,
        "content": content,
        "ts": now_iso(),
    })


async def _build_history_prompt(session_id: str) -> List[Dict[str, str]]:
    cursor = db.messages.find({"session_id": session_id}, {"_id": 0}).sort("ts", 1)
    msgs = await cursor.to_list(50)
    return [{"role": m["role"], "content": m["content"]} for m in msgs]


async def _build_system_prompt(session_id: str, user_id: str) -> str:
    """Combine JARVIS persona + cognitive profile + recent session history."""
    history = await _build_history_prompt(session_id)
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-12:])
    profile = await get_profile(db, user_id)
    profile_text = profile_to_prompt(profile)
    parts = [JARVIS_SYSTEM_PROMPT]
    if profile_text:
        parts.append("\n=== Perfil persistente do operador ===\n" + profile_text)
    if history_text:
        parts.append("\n=== Histórico recente da sessão ===\n" + history_text)
    return "\n".join(parts)


async def _maybe_compact(user_id: str):
    """Triggers async memory compaction every ~6 user turns."""
    n = await db.messages.count_documents({"role": "user"})
    if n == 0 or n % 6 != 0:
        return
    cursor = db.messages.find({}, {"_id": 0}).sort("ts", -1).limit(12)
    recent = list(reversed(await cursor.to_list(12)))
    try:
        await compact_memory(db, user_id, recent)
    except Exception:
        logger.exception("memory compaction failed")


# ---------- Tool Routing (executed BEFORE LLM streaming) ----------
import re as _re

WEATHER_KW = _re.compile(r"\b(clima|tempo|temperatura|previs[ãa]o|chov(er|a|endo)|sol|nublado|chuva)\b", _re.IGNORECASE)
AGENDA_KW = _re.compile(r"\b(agenda|compromissos?|reuni[ãa]o|reuni[õo]es|calend[áa]rio|hoje\s+(eu\s+)?tenho|minhas?\s+tarefas?)\b", _re.IGNORECASE)
SEARCH_KW = _re.compile(r"\b(pesquis(e|ar|a)|busc(a|ar|e)|procur(e|ar|a)|notícias?|últimas?\s+notícias|googl(e|a|ar)|na\s+web|na\s+internet|o\s+que\s+é|quem\s+é|quando\s+(foi|aconteceu)|defina|definição)\b", _re.IGNORECASE)


async def _run_tools(message: str, lat: Optional[float], lng: Optional[float]) -> List[Dict[str, Any]]:
    """Detects intents and fetches real data. Returns a list of {tool, content} blobs."""
    out: List[Dict[str, Any]] = []
    # Weather
    if WEATHER_KW.search(message):
        try:
            w = await _real_weather(lat=lat, lng=lng)
            out.append({
                "tool": "weather",
                "content": (
                    f"Clima atual em {w['city']}: {w['temp_c']}°C, sensação {w.get('feels_like_c', w['temp_c'])}°C, "
                    f"{w.get('description','')}. Umidade {w.get('humidity','?')}%, vento {w.get('wind_kmh','?')} km/h. "
                    f"Fonte: {w.get('source','google_weather_api')}."
                ),
            })
        except Exception as e:
            logger.warning(f"weather tool failed: {e}")
    # Agenda
    if AGENDA_KW.search(message):
        try:
            cal = await _real_calendar_today()
            if not cal.get("connected"):
                out.append({
                    "tool": "calendar",
                    "content": "AGENDA: Google Calendar NÃO conectado. Diga ao operador para clicar em GOOGLE no painel para autorizar. NÃO invente eventos.",
                })
            else:
                events = cal.get("events", [])
                if not events:
                    out.append({"tool": "calendar", "content": "Agenda do Google hoje: vazia (zero compromissos)."})
                else:
                    lines = ["Agenda real do Google hoje:"] + [
                        f" - {e.get('time','?')} — {e.get('title','(sem título)')}" + (f" — {e['location']}" if e.get('location') else "")
                        for e in events
                    ]
                    out.append({"tool": "calendar", "content": "\n".join(lines)})
        except Exception as e:
            logger.warning(f"calendar tool failed: {e}")
    # Web search
    if SEARCH_KW.search(message):
        try:
            res = await quick_search(message, max_results=5)
            block = format_results_for_llm(res)
            if block:
                out.append({"tool": "web_search", "content": "Resultados de pesquisa web (Tavily):\n" + block})
        except Exception as e:
            logger.warning(f"search tool failed: {e}")
    return out


def _tools_block_text(tools: List[Dict[str, Any]]) -> str:
    if not tools:
        return ""
    parts = ["\n=== Contexto factual atualizado (use como fonte de verdade) ==="]
    for t in tools:
        parts.append(f"[{t['tool'].upper()}]\n{t['content']}")
    return "\n".join(parts)


# Action detectors — return frontend instructions (open modal + autorun)
ACTION_IMAGE = _re.compile(r"\b(gere|gerar|crie|criar|cria|desenh[eaou]+|fa[çc]a|fazer|produza|produzir|renderiz[ea]r?|me\s+(gera|gere|crie|cria|desenhe|fa[çc]a))\s+(uma\s+|um\s+|essa\s+|essa\s+|isso\s+)?(imagem|foto|ilustra[çc][ãa]o|desenho|figura|pintura|arte|render|wallpaper|poster|p[ôo]ster|logo|logotipo|[íi]cone|ícone)\b", _re.IGNORECASE)
ACTION_VIDEO = _re.compile(r"\b(gere|gerar|crie|criar|cria|fa[çc]a|fazer|produza|produzir)\s+(um\s+|essa\s+|isso\s+)?(v[íi]deo|clipe|anima[çc][ãa]o|filme|cena|short)\b", _re.IGNORECASE)
ACTION_IMG_SEARCH = _re.compile(r"\b(mostre|encontre|me\s+mostre|me\s+ache|me\s+procura|busque|buscar|procure|procurar)\s+(fotos?|imagens?|figuras?)\b", _re.IGNORECASE)
ACTION_BUILD = _re.compile(
    r"\b(gere|gerar|crie|criar|cria|fa[çc]a|fazer|monte|montar|construa|construir|desenvolv[ae]r?|"
    r"prototip[ae]r?|me\s+(gera|gere|crie|cria|fa[çc]a|monta|monte))\s+"
    r"(uma\s+|um\s+|essa\s+|esse\s+|isso\s+)?"
    r"(landing\s*page|landingpage|p[áa]gina(?:\s+web|\s+de\s+vendas)?|site|website|web\s*site|"
    r"portf[óo]lio|portfolio|app|aplicativo|aplica[çc][ãa]o|mini[\s-]?app|"
    r"prot[óo]tipo|webapp|web\s*app|p[áa]gina\s+inicial|home\s*page|hotsite)\b",
    _re.IGNORECASE,
)

# Open URL / website action — JARVIS opens a site/app in the user's browser.
ACTION_OPEN = _re.compile(
    r"\b(abr[ae]|abrir|acess[ae]|acessar|v[áa]\s+(ao|para|pra)|leve\s+me|me\s+leve|me\s+abre|me\s+abra|"
    r"ir\s+(ao|para|pra)|navegue\s+(ao|para|pra)|abrir\s+(no|em))\s+",
    _re.IGNORECASE,
)

# Known sites (lowercase keys). Order: keep longer phrases first.
KNOWN_SITES: Dict[str, Dict[str, str]] = {
    "netflix": {"url": "https://www.netflix.com", "label": "Netflix"},
    "youtube music": {"url": "https://music.youtube.com", "label": "YouTube Music"},
    "youtube": {"url": "https://www.youtube.com", "label": "YouTube"},
    "google drive": {"url": "https://drive.google.com", "label": "Google Drive"},
    "google docs": {"url": "https://docs.google.com", "label": "Google Docs"},
    "google maps": {"url": "https://maps.google.com", "label": "Google Maps"},
    "google calendar": {"url": "https://calendar.google.com", "label": "Google Calendar"},
    "google fotos": {"url": "https://photos.google.com", "label": "Google Fotos"},
    "google": {"url": "https://www.google.com", "label": "Google"},
    "gmail": {"url": "https://mail.google.com", "label": "Gmail"},
    "outlook": {"url": "https://outlook.live.com", "label": "Outlook"},
    "whatsapp web": {"url": "https://web.whatsapp.com", "label": "WhatsApp Web"},
    "whatsapp": {"url": "https://web.whatsapp.com", "label": "WhatsApp Web"},
    "telegram": {"url": "https://web.telegram.org", "label": "Telegram Web"},
    "discord": {"url": "https://discord.com/app", "label": "Discord"},
    "slack": {"url": "https://app.slack.com", "label": "Slack"},
    "twitter": {"url": "https://x.com", "label": "X (Twitter)"},
    "x.com": {"url": "https://x.com", "label": "X (Twitter)"},
    "instagram": {"url": "https://www.instagram.com", "label": "Instagram"},
    "facebook": {"url": "https://www.facebook.com", "label": "Facebook"},
    "tiktok": {"url": "https://www.tiktok.com", "label": "TikTok"},
    "linkedin": {"url": "https://www.linkedin.com", "label": "LinkedIn"},
    "reddit": {"url": "https://www.reddit.com", "label": "Reddit"},
    "github": {"url": "https://github.com", "label": "GitHub"},
    "gitlab": {"url": "https://gitlab.com", "label": "GitLab"},
    "stackoverflow": {"url": "https://stackoverflow.com", "label": "Stack Overflow"},
    "stack overflow": {"url": "https://stackoverflow.com", "label": "Stack Overflow"},
    "spotify": {"url": "https://open.spotify.com", "label": "Spotify"},
    "deezer": {"url": "https://www.deezer.com", "label": "Deezer"},
    "twitch": {"url": "https://www.twitch.tv", "label": "Twitch"},
    "amazon prime video": {"url": "https://www.primevideo.com", "label": "Prime Video"},
    "prime video": {"url": "https://www.primevideo.com", "label": "Prime Video"},
    "disney plus": {"url": "https://www.disneyplus.com", "label": "Disney+"},
    "disney+": {"url": "https://www.disneyplus.com", "label": "Disney+"},
    "hbo max": {"url": "https://www.max.com", "label": "Max (HBO)"},
    "max": {"url": "https://www.max.com", "label": "Max"},
    "globoplay": {"url": "https://globoplay.globo.com", "label": "Globoplay"},
    "amazon": {"url": "https://www.amazon.com.br", "label": "Amazon"},
    "mercado livre": {"url": "https://www.mercadolivre.com.br", "label": "Mercado Livre"},
    "shopee": {"url": "https://shopee.com.br", "label": "Shopee"},
    "ifood": {"url": "https://www.ifood.com.br", "label": "iFood"},
    "uber": {"url": "https://www.uber.com", "label": "Uber"},
    "chatgpt": {"url": "https://chat.openai.com", "label": "ChatGPT"},
    "claude": {"url": "https://claude.ai", "label": "Claude"},
    "gemini": {"url": "https://gemini.google.com", "label": "Gemini"},
    "perplexity": {"url": "https://www.perplexity.ai", "label": "Perplexity"},
    "notion": {"url": "https://www.notion.so", "label": "Notion"},
    "figma": {"url": "https://www.figma.com", "label": "Figma"},
    "canva": {"url": "https://www.canva.com", "label": "Canva"},
    "trello": {"url": "https://trello.com", "label": "Trello"},
    "jira": {"url": "https://www.atlassian.com/software/jira", "label": "Jira"},
    "vercel": {"url": "https://vercel.com", "label": "Vercel"},
    "netlify": {"url": "https://app.netlify.com", "label": "Netlify"},
    "render": {"url": "https://dashboard.render.com", "label": "Render"},
    "wikipedia": {"url": "https://pt.wikipedia.org", "label": "Wikipedia"},
}

_URL_RE = _re.compile(r"\b(https?://[^\s]+|[a-z0-9-]+\.[a-z]{2,}(?:/[^\s]*)?)\b", _re.IGNORECASE)


def _detect_open_target(message: str) -> Optional[Dict[str, str]]:
    """Return {url, label, query} if user wants to open a known site / URL."""
    if not ACTION_OPEN.search(message or ""):
        return None
    m_lower = (message or "").lower()
    # 1) known sites (longest match first via sorted keys by length desc)
    for key in sorted(KNOWN_SITES.keys(), key=len, reverse=True):
        if _re.search(r"\b" + _re.escape(key) + r"\b", m_lower):
            return {"url": KNOWN_SITES[key]["url"], "label": KNOWN_SITES[key]["label"]}
    # 2) explicit URL in message
    url_m = _URL_RE.search(message)
    if url_m:
        url = url_m.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        return {"url": url, "label": url}
    return None


def _extract_after(message: str, keywords_re: str) -> str:
    """Extracts text after a marker like 'imagem de', 'sobre', etc."""
    m = _re.search(keywords_re + r"\s+(.+?)[.!?]?\s*$", message, _re.IGNORECASE | _re.DOTALL)
    return m.group(1).strip() if m else ""


def _detect_actions(message: str) -> List[Dict[str, Any]]:
    """Detects high-level actions the frontend should auto-execute (open modal + run)."""
    actions: List[Dict[str, Any]] = []
    msg = message or ""

    # Open URL / website (high priority — "abra o Netflix")
    target = _detect_open_target(msg)
    if target:
        actions.append({"type": "open_url", "url": target["url"], "label": target["label"]})
        return actions

    # Builder Mode (landing page / site / app) — check before image so "crie um site sobre X" doesn't fall into image
    if ACTION_BUILD.search(msg):
        # try to extract the topic/brief after a hint
        topic = _extract_after(
            msg,
            r"(?:landing\s*page|landingpage|p[áa]gina(?:\s+web|\s+de\s+vendas)?|site|website|web\s*site|"
            r"portf[óo]lio|portfolio|app|aplicativo|aplica[çc][ãa]o|mini[\s-]?app|"
            r"prot[óo]tipo|webapp|web\s*app|p[áa]gina\s+inicial|home\s*page|hotsite)"
            r"\s+(?:de|do|da|dos|das|para|pra|sobre|com|que\s+mostre|mostrando)"
        )
        actions.append({"type": "build_site", "prompt": (topic or msg).strip(), "raw": msg})
        return actions  # builder takes priority; don't also generate image

    # Image generation
    if ACTION_IMAGE.search(msg):
        prompt = _extract_after(msg, r"(?:imagem|foto|ilustra[çc][ãa]o|desenho|figura|pintura|arte|render|wallpaper|poster|p[ôo]ster|logo|logotipo|[íi]cone|ícone)\s+(?:de|do|da|dos|das|com|sobre|que mostre|mostrando|para|pra)")
        actions.append({"type": "generate_image", "prompt": prompt or msg, "provider": "gpt-image"})

    # Video generation
    if ACTION_VIDEO.search(msg):
        prompt = _extract_after(msg, r"(?:v[íi]deo|clipe|anima[çc][ãa]o|filme|cena|short)\s+(?:de|do|da|dos|das|com|sobre|que mostre|mostrando|para|pra)")
        actions.append({"type": "generate_video", "prompt": prompt or msg, "model": "veo3-fast"})

    # Image web search (visual)
    if ACTION_IMG_SEARCH.search(msg):
        q = _extract_after(msg, r"(?:fotos?|imagens?|figuras?)\s+(?:de|do|da|dos|das|sobre|com)")
        actions.append({"type": "image_search", "query": q or msg})

    # Web search action (visual): if SEARCH_KW matched and not already covered
    if SEARCH_KW.search(msg) and not any(a["type"] in ("generate_image", "generate_video", "image_search") for a in actions):
        q = _re.sub(r"\b(pesquise|pesquisar|busque|buscar|procure|procurar|encontre|encontrar|googl[eai]+r?)\b\s*(por|sobre|por sobre|na\s+web|na\s+internet)?\s*", "", msg, flags=_re.IGNORECASE).strip(" ?.!")
        actions.append({"type": "web_search", "query": q or msg})

    return actions


@api_router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest):
    """Streams the assistant response token-by-token via Server-Sent Events."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing")

    session_id = req.session_id or str(uuid.uuid4())
    # ensure session exists
    existing = await db.sessions.find_one({"id": session_id})
    if not existing:
        await db.sessions.insert_one({
            "id": session_id,
            "user_id": req.user_id or "owner",
            "created_at": now_iso(),
            "title": req.message[:48],
        })

    # Build chat with persona + persistent profile + recent history
    system_msg = await _build_system_prompt(session_id, req.user_id or "owner")

    # Tool routing: detect intent and prepend real factual context
    tool_results: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    if req.enable_tools:
        try:
            tool_results = await _run_tools(req.message, lat=req.lat, lng=req.lng)
            actions = _detect_actions(req.message)
        except Exception:
            logger.exception("tool routing failed")
    tools_text = _tools_block_text(tool_results)
    if tools_text:
        system_msg = system_msg + "\n" + tools_text
    if actions:
        # Tell the model an action will be triggered by the frontend; keep response short
        action_names = ", ".join(a["type"] for a in actions)
        action_hint = ""
        # Add hint for open_url so JARVIS confirms the actual site name
        for a in actions:
            if a["type"] == "open_url":
                action_hint = f" — abrindo {a.get('label') or a.get('url')}"
                break
        system_msg = system_msg + (
            f"\n\n=== AÇÃO AUTOMÁTICA ===\n"
            f"O sistema irá disparar automaticamente as seguintes ações no painel do Edge Console: {action_names}{action_hint}.\n"
            f"Responda APENAS com uma frase curta de confirmação (1-2 frases) no estilo JARVIS, sem listar passos nem descrever o conteúdo (ele será mostrado visualmente). "
            f"Ex.: 'Imediatamente, Felipe. Gerando agora.' ou 'Já estou cuidando disso para o senhor.'\n"
        )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_msg,
    ).with_model("gemini", "gemini-2.5-flash")

    await _persist_message(session_id, "user", req.message)

    async def event_gen():
        full = []
        # Emit session id first
        yield f"event: meta\ndata: {json.dumps({'session_id': session_id, 'tools_used': [t['tool'] for t in tool_results], 'actions': actions})}\n\n"
        try:
            async for ev in chat.stream_message(UserMessage(text=req.message)):
                if isinstance(ev, TextDelta):
                    full.append(ev.content)
                    payload = json.dumps({"delta": ev.content})
                    yield f"event: delta\ndata: {payload}\n\n"
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            logger.exception("LLM stream error")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        text = "".join(full).strip() or "(sem resposta)"
        await _persist_message(session_id, "assistant", text)
        # async memory compaction (fire-and-forget)
        asyncio.create_task(_maybe_compact(req.user_id or "owner"))
        yield f"event: done\ndata: {json.dumps({'text': text})}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_router.post("/chat/send")
async def chat_send(req: ChatStreamRequest):
    """Non-streaming variant (useful for edge agent / tests)."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing")
    session_id = req.session_id or str(uuid.uuid4())
    existing = await db.sessions.find_one({"id": session_id})
    if not existing:
        await db.sessions.insert_one({
            "id": session_id, "user_id": req.user_id or "owner",
            "created_at": now_iso(), "title": req.message[:48],
        })
    history = await _build_history_prompt(session_id)
    _ = history  # consumed via _build_system_prompt
    system_msg = await _build_system_prompt(session_id, req.user_id or "owner")
    # Tool routing + action detection
    actions: List[Dict[str, Any]] = []
    if req.enable_tools:
        try:
            tool_results = await _run_tools(req.message, lat=req.lat, lng=req.lng)
            actions = _detect_actions(req.message)
            tools_text = _tools_block_text(tool_results)
            if tools_text:
                system_msg = system_msg + "\n" + tools_text
            if actions:
                action_names = ", ".join(a["type"] for a in actions)
                system_msg = system_msg + (
                    f"\n\n=== AÇÃO AUTOMÁTICA ===\nO sistema irá disparar automaticamente: {action_names}. "
                    f"Responda APENAS com uma frase curta de confirmação no estilo JARVIS, sem listar passos.\n"
                )
        except Exception:
            logger.exception("tool routing (send) failed")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY, session_id=session_id, system_message=system_msg,
    ).with_model("gemini", "gemini-2.5-flash")
    await _persist_message(session_id, "user", req.message)
    text = await chat.send_message(UserMessage(text=req.message))
    text = (text or "").strip() or "(sem resposta)"
    await _persist_message(session_id, "assistant", text)
    asyncio.create_task(_maybe_compact(req.user_id or "owner"))
    return {"session_id": session_id, "text": text, "actions": actions}


# ---------- Routes: TTS / STT ----------
@api_router.post("/tts")
async def tts(req: TTSRequest):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing")
    tts_client = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
    try:
        audio = await tts_client.generate_speech(
            text=req.text[:4000], model=req.model, voice=req.voice,
            speed=req.speed, response_format="mp3",
        )
    except Exception as e:
        logger.exception("TTS failed")
        raise HTTPException(500, f"TTS failed: {e}")
    return Response(content=audio, media_type="audio/mpeg")


# Known Whisper hallucinations on silence/noise (Portuguese + English)
_WHISPER_HALLUCINATIONS = {
    "legendas pela comunidade amara.org",
    "legendas pela comunidade amara. org",
    "legendado pela comunidade amara.org",
    "obrigado por assistir",
    "obrigado por assistirem",
    "obrigada por assistir",
    "obrigado por assistir!",
    "obrigado por ver o vídeo",
    "obrigada por ver o vídeo",
    "obrigado por ver este vídeo",
    "subscreve o canal",
    "inscreva-se no canal",
    "curta e se inscreva",
    "thanks for watching",
    "thank you for watching",
    "thanks for watching!",
    "please subscribe",
    "subscribe to my channel",
    "www.mooji.org",
    "amara.org",
    "www.amara.org",
    ".",
    "..",
    "...",
}


def _is_whisper_hallucination(text: str) -> bool:
    if not text:
        return True
    t = text.strip().lower().rstrip(".!?")
    if not t or len(t) < 2:
        return True
    return t in _WHISPER_HALLUCINATIONS


@api_router.post("/stt")
async def stt(file: UploadFile = File(...)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "EMERGENT_LLM_KEY missing")
    stt_client = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    raw = await file.read()
    # Reject audio that's obviously too small to contain speech.
    # Typical webm/opus ~= 6-8 KB/s at 24-32kbps. Under 6KB = < ~0.7s of speech.
    if len(raw) < 6144:
        return {"text": "", "reason": "audio_too_short", "bytes": len(raw)}
    # Persist to /tmp with proper extension so litellm/whisper accepts the upload.
    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    tmp_path = Path(f"/tmp/jarvis_stt_{uuid.uuid4().hex}{suffix}")
    tmp_path.write_bytes(raw)
    try:
        # Pass an open binary file handle (litellm/openai requires bytes/IOBase/PathLike/tuple, not str)
        with open(tmp_path, "rb") as fh:
            # `prompt` biases Whisper towards our domain, reducing hallucinations
            # like "Legendas pela comunidade Amara.org" that Whisper emits on silence.
            resp = await stt_client.transcribe(
                file=fh, model="whisper-1",
                response_format="json", language="pt",
                prompt="Assistente pessoal JARVIS. Comandos em português brasileiro: abrir, tocar, buscar, agenda, clima, música.",
                temperature=0.0,
            )
        text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None) or str(resp)
    except Exception as e:
        logger.exception("STT failed")
        raise HTTPException(500, f"STT failed: {e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
    # Filter out known Whisper hallucinations on silence/noise
    if _is_whisper_hallucination(text):
        logger.info(f"STT: filtered hallucination: {text!r}")
        return {"text": "", "reason": "hallucination_filtered", "raw": text}
    return {"text": text}


# ---------- Routes: Face authentication ----------
def _embedding_distance(a: List[float], b: List[float]) -> float:
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    if va.shape != vb.shape:
        return 99.0
    # Euclidean — face_recognition uses this with default threshold 0.6
    return float(np.linalg.norm(va - vb))


@api_router.post("/face/register")
async def face_register(req: FaceRegisterRequest):
    if len(req.embedding) < 64:
        raise HTTPException(400, "Embedding too small")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": req.user_id,
        "name": req.name,
        "embedding": req.embedding,
        "created_at": now_iso(),
    }
    await db.face_profiles.replace_one({"user_id": req.user_id}, doc, upsert=True)
    return {"ok": True, "user_id": req.user_id, "name": req.name}


@api_router.post("/face/auth")
async def face_auth(req: FaceAuthRequest):
    profiles = await db.face_profiles.find({}, {"_id": 0}).to_list(100)
    if not profiles:
        return {"authenticated": False, "reason": "no_profile_registered"}
    best, best_dist = None, 99.0
    for p in profiles:
        d = _embedding_distance(req.embedding, p["embedding"])
        if d < best_dist:
            best, best_dist = p, d
    matched = best_dist <= req.threshold
    return {
        "authenticated": matched,
        "distance": best_dist,
        "user_id": best["user_id"] if matched else None,
        "name": best["name"] if matched else None,
    }


@api_router.get("/face/profiles")
async def face_profiles():
    profiles = await db.face_profiles.find({}, {"_id": 0, "embedding": 0}).to_list(100)
    return profiles


# ---------- Routes: Activation / Morning report ----------
@api_router.post("/activation")
async def activation(req: ActivationRequest):
    """Records a wake-word activation and returns a greeting + (once per day) the morning report."""
    today = date.today().isoformat()
    user_id = req.user_id or "owner"
    profile = await db.face_profiles.find_one({"user_id": user_id})
    name = profile["name"] if profile else "Senhor"

    last = await db.activations.find_one({"user_id": user_id}, sort=[("ts", -1)])
    first_today = not last or not last.get("date") == today

    greeting = f"{part_of_day_pt()}, {name}. J.A.R.V.I.S. à sua disposição."

    morning = None
    if first_today:
        morning = await _morning_report_payload(name, lat=req.lat, lng=req.lng)

    await db.activations.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "transcript": req.transcript,
        "ts": now_iso(),
        "date": today,
        "first_today": first_today,
    })
    return {
        "greeting": greeting,
        "first_today": first_today,
        "morning_report": morning,
        "ts": now_iso(),
    }


async def _morning_report_payload(name: str, lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
    weather = await _real_weather(lat=lat, lng=lng)
    cal = await _real_calendar_today()
    agenda = cal.get("events", []) if cal else []
    if not cal.get("connected"):
        summary = (
            f"{part_of_day_pt()}, {name}. Em {weather['city']} a temperatura atual é "
            f"{weather['temp_c']}°C, {weather['description']}. "
            f"Sua agenda do Google ainda não está conectada — autorize o acesso pelo botão GOOGLE para que eu possa lhe informar seus compromissos."
        )
    else:
        if len(agenda) == 0:
            summary = (
                f"{part_of_day_pt()}, {name}. Em {weather['city']} a temperatura atual é "
                f"{weather['temp_c']}°C, {weather['description']}. "
                f"Sua agenda do Google está vazia para hoje."
            )
        else:
            first = agenda[0]
            summary = (
                f"{part_of_day_pt()}, {name}. Em {weather['city']} a temperatura atual é "
                f"{weather['temp_c']}°C, {weather['description']}. "
                f"O senhor tem {len(agenda)} compromisso(s) hoje, começando com '{first.get('title','')}' às {first.get('time','')}."
            )
    return {"weather": weather, "agenda": agenda, "calendar_connected": cal.get("connected", False), "summary": summary}


@api_router.get("/morning-report")
async def morning_report(user_id: str = "owner", lat: Optional[float] = None, lng: Optional[float] = None):
    profile = await db.face_profiles.find_one({"user_id": user_id})
    name = profile["name"] if profile else "Senhor"
    return await _morning_report_payload(name, lat=lat, lng=lng)


# ---------- Real 3rd-party integrations ----------
async def _real_weather(lat: Optional[float] = None, lng: Optional[float] = None, city: Optional[str] = None) -> Dict[str, Any]:
    """Returns real weather; uses geolocation when provided, else DEFAULT_CITY (Belo Horizonte)."""
    return await google_get_weather(city=city, lat=lat, lng=lng)


async def _real_calendar_today() -> Dict[str, Any]:
    """Returns today's events from Google Calendar OR a 'not connected' marker.
    Never fabricates events."""
    token_doc = await db.google_tokens.find_one({"user_id": "owner"})
    if not token_doc or not token_doc.get("access_token"):
        return {"connected": False, "events": [], "message": "Google Calendar não conectado. Clique em GOOGLE no painel para autorizar."}
    try:
        events = await list_today_events(token_doc["access_token"])
        return {"connected": True, "events": events, "count": len(events)}
    except Exception:
        pass
    # Try refresh
    if token_doc.get("refresh_token"):
        try:
            refreshed = await refresh_access_token(token_doc["refresh_token"])
            if refreshed and refreshed.get("access_token"):
                token_doc["access_token"] = refreshed["access_token"]
                await db.google_tokens.replace_one({"user_id": "owner"}, token_doc, upsert=True)
                events = await list_today_events(refreshed["access_token"])
                return {"connected": True, "events": events, "count": len(events)}
        except Exception:
            pass
    return {"connected": True, "events": [], "count": 0, "warning": "token_invalid"}


@api_router.get("/integrations/weather")
async def integ_weather(city: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None):
    return await _real_weather(lat=lat, lng=lng, city=city)


@api_router.get("/integrations/calendar/today")
async def integ_calendar():
    cal = await _real_calendar_today()
    return {"date": date.today().isoformat(), **cal}


# ---------- Tool History ----------
# In-memory pub/sub for SSE history.updated events
class HistoryEventHub:
    def __init__(self):
        self.queues: List[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.queues:
            self.queues.remove(q)

    async def broadcast(self, payload: Dict[str, Any]):
        for q in list(self.queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # drop oldest then push
                try:
                    _ = q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass


HISTORY_HUB = HistoryEventHub()


async def _store_b64_asset(b64_str: str, mime: str = "image/png") -> Optional[str]:
    """Store a base64 image/video binary in GridFS. Returns asset id (str)."""
    try:
        raw = base64.b64decode(b64_str)
    except Exception:
        return None
    if not raw:
        return None
    try:
        file_id = await TOOL_ASSETS_FS.upload_from_stream(
            "tool_asset.bin",
            raw,
            metadata={"mime": mime, "ts": now_iso()},
        )
        return str(file_id)
    except Exception:
        logger.exception("gridfs upload failed")
        return None


async def _externalize_image_payload(images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Move base64 image bytes to GridFS; keep only references in the history payload."""
    out: List[Dict[str, Any]] = []
    for img in (images or [])[:1]:  # only store the first image to keep history light
        if not isinstance(img, dict):
            continue
        if img.get("b64"):
            mime = img.get("mime", "image/png")
            aid = await _store_b64_asset(img["b64"], mime)
            if aid:
                out.append({"asset_id": aid, "mime": mime})
            elif img.get("url"):
                out.append({"url": img["url"]})
        elif img.get("url"):
            out.append({"url": img["url"]})
    return out


async def _save_tool_history(tool_type: str, payload: Dict[str, Any], user_id: str = "owner") -> None:
    try:
        # For image_gen, move base64 to GridFS to avoid bloating the document
        if tool_type == "image_gen" and isinstance(payload.get("images"), list):
            payload = {**payload, "images": await _externalize_image_payload(payload["images"])}
        await db.tool_history.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": tool_type,  # search | image_search | vision | files | image_gen | video_gen
            "payload": payload,
            "ts": now_iso(),
        })
        # Notify SSE subscribers
        await HISTORY_HUB.broadcast({"type": tool_type, "ts": now_iso(), "user_id": user_id})
    except Exception:
        logger.exception("save tool history failed")


@api_router.get("/agent/history/asset/{asset_id}")
async def get_history_asset(asset_id: str):
    """Stream a GridFS asset stored by tool_history (image generations)."""
    try:
        oid = _BsonObjectId(asset_id)
    except Exception:
        raise HTTPException(404, "Invalid asset id")
    try:
        stream = await TOOL_ASSETS_FS.open_download_stream(oid)
    except Exception:
        raise HTTPException(404, "Asset not found")
    data = await stream.read()
    mime = (stream.metadata or {}).get("mime", "application/octet-stream")
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@api_router.get("/agent/history/events")
async def history_events(request: Request):
    """SSE stream — broadcasts {type: <tool_type>, ts, user_id} on every history insert."""
    queue = HISTORY_HUB.subscribe()

    async def event_gen():
        try:
            yield f"event: connected\ndata: {json.dumps({'ts': now_iso()})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: history.updated\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # keep-alive comment so proxies don't close the stream
                    yield ": ping\n\n"
        finally:
            HISTORY_HUB.unsubscribe(queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_router.get("/agent/history")
async def agent_history(type: Optional[str] = None, limit: int = 30, user_id: str = "owner"):
    q: Dict[str, Any] = {"user_id": user_id}
    if type:
        q["type"] = type
    cur = db.tool_history.find(q, {"_id": 0}).sort("ts", -1).limit(min(limit, 100))
    return await cur.to_list(min(limit, 100))


@api_router.delete("/agent/history/{item_id}")
async def agent_history_delete(item_id: str):
    r = await db.tool_history.delete_one({"id": item_id})
    return {"ok": r.deleted_count > 0}


@api_router.delete("/agent/history")
async def agent_history_clear(type: Optional[str] = None, user_id: str = "owner"):
    q: Dict[str, Any] = {"user_id": user_id}
    if type:
        q["type"] = type
    r = await db.tool_history.delete_many(q)
    return {"deleted": r.deleted_count}


# ---------- Edge Agent Tools: Web search ----------
class SearchRequest(BaseModel):
    query: str
    deep: bool = False
    max_results: int = 6


@api_router.post("/agent/search")
async def agent_search(req: SearchRequest):
    """Web search via Tavily. `deep=true` for research-mode (slower, richer)."""
    if req.deep:
        result = await deep_research(req.query, max_results=req.max_results)
    else:
        result = await quick_search(req.query, max_results=req.max_results)
    await _save_tool_history("search", {"query": req.query, "deep": req.deep, "result": result})
    return result


class ImageSearchRequest(BaseModel):
    query: str
    max_results: int = 8


@api_router.post("/agent/image-search")
async def agent_image_search(req: ImageSearchRequest):
    urls = await image_search(req.query, max_results=req.max_results)
    payload = {"query": req.query, "images": urls}
    await _save_tool_history("image_search", payload)
    return payload


# ---------- Edge Agent Tools: Vision ----------
class VisionUrlRequest(BaseModel):
    url: str
    question: Optional[str] = None


@api_router.post("/agent/vision/url")
async def agent_vision_url(req: VisionUrlRequest):
    text = await analyze_image_url(req.url, question=req.question)
    payload = {"analysis": text, "url": req.url, "question": req.question}
    await _save_tool_history("vision", payload)
    return payload


@api_router.post("/agent/vision/upload")
async def agent_vision_upload(file: UploadFile = File(...), question: Optional[str] = None):
    raw = await file.read()
    mime = file.content_type or "image/png"
    text = await analyze_image_bytes(raw, mime_type=mime, question=question)
    payload = {"analysis": text, "filename": file.filename, "mime_type": mime, "size": len(raw), "question": question}
    await _save_tool_history("vision", payload)
    return payload


# ---------- Edge Agent Tools: File conversion ----------
@api_router.post("/agent/files/convert")
async def agent_files_convert(file: UploadFile = File(...), question: Optional[str] = None):
    raw = await file.read()
    result = await convert_file(file.filename or "file", raw, mime_type=file.content_type or "", question=question)
    # Persist tool history (use lighter version - truncate text for storage)
    light = dict(result)
    if light.get("text"):
        light["text"] = light["text"][:4000]
    await _save_tool_history("files", light)
    return result


@api_router.get("/agent/files/history")
async def agent_files_history(limit: int = 20):
    cur = db.file_history.find({}, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cur.to_list(limit)


# ---------- Builder Mode (Phase 3) ----------
class BuilderCreateRequest(BaseModel):
    name: str = "Novo Projeto"
    description: str = ""
    template: str = "blank"


class BuilderUpdateFilesRequest(BaseModel):
    files: Optional[Dict[str, str]] = None
    deletes: Optional[List[str]] = None


class BuilderRenameRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class BuilderChatRequest(BaseModel):
    message: str


class BuilderSnapshotRequest(BaseModel):
    label: Optional[str] = ""


class BuilderPublishRequest(BaseModel):
    slug: Optional[str] = ""


@api_router.get("/builder/templates")
async def get_builder_templates():
    return list_templates()


@api_router.get("/builder/projects")
async def list_builder_projects(user_id: str = "owner"):
    return await builder_list(db, user_id=user_id)


@api_router.post("/builder/projects")
async def create_builder_project(req: BuilderCreateRequest):
    return await builder_create(db, name=req.name, description=req.description, template=req.template)


@api_router.get("/builder/projects/{project_id}")
async def get_builder_project(project_id: str):
    p = await builder_get(db, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@api_router.put("/builder/projects/{project_id}/files")
async def update_builder_files(project_id: str, req: BuilderUpdateFilesRequest):
    updated = await builder_update_files(db, project_id, files=req.files or {}, deletes=req.deletes or [])
    if not updated:
        raise HTTPException(404, "Project not found")
    return updated


@api_router.put("/builder/projects/{project_id}")
async def rename_builder_project(project_id: str, req: BuilderRenameRequest):
    updated = await builder_rename(db, project_id, name=req.name or "", description=req.description or "")
    if not updated:
        raise HTTPException(404, "Project not found")
    return updated


@api_router.delete("/builder/projects/{project_id}")
async def delete_builder_project(project_id: str):
    ok = await builder_delete(db, project_id)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@api_router.post("/builder/projects/{project_id}/chat")
async def chat_builder_project(project_id: str, req: BuilderChatRequest):
    result = await builder_chat(db, project_id, req.message)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@api_router.get("/builder/projects/{project_id}/download")
async def download_builder_project(project_id: str):
    """Return project as ZIP."""
    p = await builder_get(db, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    import io as _io
    import zipfile as _zip
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
        for path, content in (p.get("files") or {}).items():
            zf.writestr(path, content or "")
        for path, meta in (p.get("assets") or {}).items():
            if isinstance(meta, dict) and meta.get("b64"):
                try:
                    zf.writestr(path, base64.b64decode(meta["b64"]))
                except Exception:
                    pass
    buf.seek(0)
    safe_name = (p.get("name") or "project").replace("/", "_").replace(" ", "_")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={safe_name}.zip"},
    )


# ---------- Snapshots ----------
@api_router.post("/builder/projects/{project_id}/snapshots")
async def create_builder_snapshot(project_id: str, req: BuilderSnapshotRequest):
    snap = await create_snapshot(db, project_id, label=req.label or "")
    if not snap:
        raise HTTPException(404, "Project not found")
    return snap


@api_router.get("/builder/projects/{project_id}/snapshots")
async def list_builder_snapshots(project_id: str):
    return await list_snapshots(db, project_id)


@api_router.post("/builder/projects/{project_id}/snapshots/{snapshot_id}/restore")
async def restore_builder_snapshot(project_id: str, snapshot_id: str):
    p = await restore_snapshot(db, project_id, snapshot_id)
    if not p:
        raise HTTPException(404, "Snapshot or project not found")
    return p


@api_router.delete("/builder/projects/{project_id}/snapshots/{snapshot_id}")
async def delete_builder_snapshot(project_id: str, snapshot_id: str):
    ok = await delete_snapshot(db, project_id, snapshot_id)
    if not ok:
        raise HTTPException(404, "Snapshot not found")
    return {"ok": True}


# ---------- Assets ----------
@api_router.post("/builder/projects/{project_id}/assets")
async def upload_builder_asset(project_id: str, file: UploadFile = File(...), path: Optional[str] = None):
    raw = await file.read()
    rel_path = path or f"assets/{file.filename}"
    mime = file.content_type or "application/octet-stream"
    b64 = base64.b64encode(raw).decode("ascii")
    result = await upload_asset(db, project_id, rel_path, b64, mime)
    if not result:
        raise HTTPException(404, "Project not found")
    return result


@api_router.delete("/builder/projects/{project_id}/assets")
async def delete_builder_asset(project_id: str, path: str):
    ok = await delete_asset(db, project_id, path)
    if not ok:
        raise HTTPException(404, "Asset not found")
    return {"ok": True}


# ---------- Publish ----------
@api_router.post("/builder/projects/{project_id}/publish")
async def publish_builder_project(project_id: str, req: BuilderPublishRequest):
    result = await publish_project(db, project_id, custom_slug=req.slug or "")
    if not result:
        raise HTTPException(404, "Project not found")
    return result


@api_router.post("/builder/projects/{project_id}/unpublish")
async def unpublish_builder_project(project_id: str):
    await unpublish_project(db, project_id)
    return {"ok": True}


# Public route (no /api auth required since it's open)
@api_router.get("/public/{slug}")
async def serve_public_project(slug: str):
    p = await get_public_project(db, slug)
    if not p:
        raise HTTPException(404, "Site não encontrado ou despublicado.")
    html = render_preview_html(p.get("files") or {}, p.get("assets") or {})
    return Response(content=html, media_type="text/html")


# ---------- Media generation ----------
class ImageGenRequest(BaseModel):
    prompt: str
    provider: str = "gpt-image"  # gpt-image | nano-banana
    n: int = 1
    size: str = "1024x1024"


class VideoGenRequest(BaseModel):
    prompt: str
    model: str = "veo3-fast"  # veo3-fast | veo3 | kling-v2 | luma
    duration: int = 8
    aspect_ratio: str = "16:9"


@api_router.post("/agent/image/generate")
async def agent_image_generate(req: ImageGenRequest):
    """Generate image with smart fallback.

    Strategy:
      - If provider == nano-banana, just call nano-banana.
      - Else: try gpt-image-1; on ANY error (safety, rate, 5xx) fall back to nano-banana.
      - If both fail, return a combined error so the UI can show both reasons.
    """
    if req.provider == "nano-banana":
        result = await generate_image_nano_banana(req.prompt)
    else:
        result = await generate_image_gpt(req.prompt, n=req.n, size=req.size)
        if result.get("error"):
            gpt_err = result.get("error")
            fb = await generate_image_nano_banana(req.prompt)
            if not fb.get("error"):
                fb["fallback_from"] = "gpt-image-1"
                fb["fallback_reason"] = (gpt_err or "")[:200]
                result = fb
            else:
                # Both failed — surface a friendly combined message
                result = {
                    "error": (
                        "Não foi possível gerar a imagem em nenhum dos provedores. "
                        f"OpenAI: {gpt_err[:240] if gpt_err else 'erro'}. "
                        f"Nano-Banana: {(fb.get('error') or '')[:240]}."
                    ),
                    "provider": "fallback_chain",
                    "errors": {"gpt-image-1": gpt_err, "nano-banana": fb.get("error")},
                }
    # Save lightweight history (store first image b64/url; cap to keep MongoDB fast)
    light = {
        "prompt": req.prompt,
        "provider": result.get("provider"),
        "error": result.get("error"),
        "images": (result.get("images") or [])[:1],
        "size": req.size,
    }
    await _save_tool_history("image_gen", light)
    return result


@api_router.post("/agent/video/generate")
async def agent_video_generate(req: VideoGenRequest):
    result = await generate_video(req.prompt, model=req.model, duration_seconds=req.duration, aspect_ratio=req.aspect_ratio)
    light = {
        "prompt": req.prompt,
        "model": req.model,
        "duration": req.duration,
        "aspect_ratio": req.aspect_ratio,
        "provider": result.get("provider"),
        "video_url": result.get("video_url"),
        "error": result.get("error"),
    }
    await _save_tool_history("video_gen", light)
    return result


# ---------- YouTube music (browser open) ----------
@api_router.get("/integrations/music/search")
async def music_search(q: str):
    """Returns a YouTube embed URL the dashboard can iframe directly.

    Strategy:
      1) If GOOGLE_API_KEY is configured, call YouTube Data API v3 (search.list)
         to resolve the first matching video → embed by videoId (most reliable).
      2) Fallback: open the YouTube search page in a new tab (no autoplay).
    """
    import httpx as _httpx
    from urllib.parse import quote_plus
    query = q.strip()
    encoded = quote_plus(query)
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    video_id = None
    title = None
    channel = None
    if api_key:
        try:
            async with _httpx.AsyncClient(timeout=10) as cx:
                r = await cx.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "maxResults": "1",
                        "type": "video",
                        "videoEmbeddable": "true",
                        "q": query,
                        "key": api_key,
                    },
                )
            if r.status_code == 200:
                items = r.json().get("items", [])
                if items:
                    video_id = items[0]["id"].get("videoId")
                    sn = items[0].get("snippet", {})
                    title = sn.get("title")
                    channel = sn.get("channelTitle")
        except Exception:
            video_id = None
    if video_id:
        embed_url = f"https://www.youtube.com/embed/{video_id}?autoplay=1&rel=0"
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
    else:
        embed_url = f"https://www.youtube.com/results?search_query={encoded}"  # not embeddable
        watch_url = embed_url
    return {
        "query": query,
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "embed_url": embed_url,
        "watch_url": watch_url,
        "search_url": f"https://www.youtube.com/results?search_query={encoded}",
        "play_url": f"https://music.youtube.com/search?q={encoded}",
        "source": "youtube_data_api_v3" if video_id else "fallback_search",
    }


# ---------- Google OAuth (Multi-User + Calendar) ----------
@api_router.get("/auth/google/login")
async def google_login(agent: Optional[str] = None):
    state = uuid.uuid4().hex
    url = oauth_login_url(state)
    if not url:
        raise HTTPException(500, "Google OAuth not configured")
    await db.oauth_states.insert_one({"state": state, "agent": agent, "ts": now_iso()})
    return {"auth_url": url, "state": state}


@api_router.get("/auth/google/desktop")
async def google_login_desktop(redirect: str, agent_name: str = "Home-PC"):
    """OAuth Loopback Flow for desktop apps (RFC 8252).

    Desktop starts a local HTTP server on 127.0.0.1:PORT and hits this endpoint.
    We remember `redirect` in the state document; after Google callback we
    redirect to that local URL with `?token=<JWT>&agent_token=<AT>&brain_url=X`.

    Security: only http://127.0.0.1:* / http://localhost:* redirects allowed.
    """
    from urllib.parse import urlparse
    from fastapi.responses import RedirectResponse
    p = urlparse(redirect)
    if p.scheme != "http" or p.hostname not in ("127.0.0.1", "localhost"):
        raise HTTPException(400, "desktop redirect must be http://127.0.0.1:PORT/...")
    state = uuid.uuid4().hex
    url = oauth_login_url(state)
    if not url:
        raise HTTPException(500, "Google OAuth not configured")
    await db.oauth_states.insert_one({
        "state": state,
        "agent": agent_name,
        "desktop_redirect": redirect,
        "ts": now_iso(),
    })
    return RedirectResponse(url=url)


@api_router.get("/auth/google/callback")
async def google_callback(code: str, state: str = ""):
    from fastapi.responses import RedirectResponse
    tokens = await exchange_code(code)
    if not tokens:
        raise HTTPException(400, "Token exchange failed")
    # Fetch userinfo to identify who logged in
    userinfo = await fetch_userinfo(tokens.get("access_token", ""))
    if not userinfo:
        raise HTTPException(400, "Falha ao obter perfil do usuário Google")
    user = await upsert_user(db, userinfo, tokens)
    session_token = issue_session_token(user)

    # Check if this is a desktop OAuth loopback flow
    st = None
    if state:
        try:
            st = await db.oauth_states.find_one({"state": state})
        except Exception:
            st = None
    if st and st.get("desktop_redirect"):
        # Desktop flow: redirect to local loopback with tokens
        agent_name = st.get("agent") or "Home-PC"
        agent_token = issue_agent_token(user["user_id"], agent_name)
        loop_url = st["desktop_redirect"]
        sep = "&" if "?" in loop_url else "?"
        # Also expose brain_url so the desktop knows where to point.
        # It's the same host that served this callback.
        # We reconstruct from GOOGLE_REDIRECT_URI which is the public backend.
        brain = os.environ.get("GOOGLE_REDIRECT_URI", "").split("/api/")[0]
        redir = (
            f"{loop_url}{sep}token={session_token}"
            f"&agent_token={agent_token}"
            f"&agent_name={agent_name}"
            f"&user_id={user['user_id']}"
            f"&email={user.get('email','')}"
            f"&name={user.get('name','')}"
            f"&brain_url={brain}"
        )
        # Clean up state doc (best-effort)
        try:
            await db.oauth_states.delete_one({"state": state})
        except Exception:
            pass
        return RedirectResponse(url=redir)

    # Web flow: redirect back to SPA with token in query
    return RedirectResponse(url=f"/?token={session_token}&connected=1")


@api_router.get("/auth/me")
async def auth_me(request: Request):
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Não autenticado")
    return {
        "user_id": user["user_id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "created_at": user.get("created_at"),
    }


@api_router.post("/auth/logout")
async def auth_logout(request: Request):
    # Stateless JWT: client discards token. Endpoint kept for symmetry.
    return {"ok": True}


@api_router.post("/auth/agent/pair")
async def auth_agent_pair(request: Request, agent_name: str = "Home-PC"):
    """Return an agent_token bound to (user_id, agent_name)."""
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório para parear um agente")
    tok = issue_agent_token(user["user_id"], agent_name)
    return {
        "agent_token": tok,
        "user_id": user["user_id"],
        "agent_name": agent_name,
        "agent_id": f"{user['user_id']}:{agent_name}",
    }


@api_router.get("/agent/download-config")
async def agent_download_config(request: Request, agent_name: str = "Home-PC"):
    """Return a ready-to-use agent.json the user just drops in ~/.jarvis/.
    Auth: session JWT (via `Authorization: Bearer ...` or `?token=` query).
    """
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    tok = issue_agent_token(user["user_id"], agent_name)
    # Build canonical backend URL from the request (respects host/proxy).
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    port = request.url.port
    base = f"{scheme}://{host}"
    if port and port not in (80, 443):
        base += f":{port}"
    cfg = {
        "BRAIN_URL": base,
        "AGENT_TOKEN": tok,
        "AGENT_ID": f"{user['user_id']}:{agent_name}",
        "AGENT_NAME": agent_name,
        "USER_ID": user["user_id"],
        "USER_EMAIL": user.get("email"),
    }
    body = json.dumps(cfg, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="agent.json"',
            "Cache-Control": "no-store",
        },
    )


@api_router.get("/agent/install-script")
async def agent_install_script(request: Request, agent_name: str = "Home-PC"):
    """Return a Windows PowerShell one-liner that:
        1) creates %USERPROFILE%\\.jarvis\\agent.json with the token
        2) points the user to the edge_agent install steps
    Meant to be piped through `iex` after downloading.
    """
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    tok = issue_agent_token(user["user_id"], agent_name)
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.hostname
    base = f"{scheme}://{host}"
    ps = f"""# J.A.R.V.I.S. Edge Agent — auto pairing
$ErrorActionPreference = 'Stop'
$home_dir = Join-Path $env:USERPROFILE '.jarvis'
New-Item -ItemType Directory -Force -Path $home_dir | Out-Null
$cfg = @{{
  BRAIN_URL   = '{base}'
  AGENT_TOKEN = '{tok}'
  AGENT_ID    = '{user["user_id"]}:{agent_name}'
  AGENT_NAME  = '{agent_name}'
  USER_ID     = '{user["user_id"]}'
}} | ConvertTo-Json
Set-Content -Path (Join-Path $home_dir 'agent.json') -Value $cfg -Encoding UTF8
Write-Host "[jarvis] agent.json gravado em $home_dir\\agent.json" -ForegroundColor Cyan
Write-Host "[jarvis] Agora rode: python agent_v2.py (dentro do diretório edge_agent)"
"""
    return Response(content=ps, media_type="text/plain; charset=utf-8")


@api_router.get("/auth/google/status")
async def google_status(request: Request):
    user = await _current_user(request, db)
    uid = (user or {}).get("user_id", "owner")
    doc = await db.google_tokens.find_one({"user_id": uid}, {"_id": 0, "access_token": 0, "refresh_token": 0})
    return {"connected": bool(doc), "since": (doc or {}).get("ts")}


@api_router.post("/auth/google/disconnect")
async def google_disconnect(request: Request):
    user = await _current_user(request, db)
    uid = (user or {}).get("user_id", "owner")
    await db.google_tokens.delete_many({"user_id": uid})
    return {"ok": True}


# ---------- Credential Vault ----------
class VaultPutRequest(BaseModel):
    site: str
    username: str
    password: str
    url: Optional[str] = None
    notes: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


@api_router.post("/vault/put")
async def vault_put(req: VaultPutRequest, request: Request):
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    return await put_credential(
        db, user["user_id"], req.site, req.username, req.password,
        url=req.url, notes=req.notes, extra=req.extra,
    )


@api_router.get("/vault/list")
async def vault_list(request: Request):
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    return {"items": await list_credentials(db, user["user_id"])}


@api_router.get("/vault/get/{site}")
async def vault_get(site: str, request: Request):
    """Return DECRYPTED credential. Accepts session token OR agent token.
    Only the token owner's vault is accessible.
    """
    # Try session token first
    user = await _current_user(request, db)
    user_id = user["user_id"] if user else None
    if not user_id:
        # Try agent token
        auth = request.headers.get("x-agent-token") or ""
        payload = decode_agent_token(auth) if auth else None
        if payload:
            user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(401, "Login ou agent_token obrigatório")
    item = await get_credential(db, user_id, site)
    if not item:
        raise HTTPException(404, "Credencial não encontrada")
    return item


@api_router.delete("/vault/{site}")
async def vault_delete(site: str, request: Request):
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    ok = await delete_credential(db, user["user_id"], site)
    return {"ok": ok}


# ---------- Agent Command Dispatch (HTTP -> WS) ----------
class AgentCommandRequest(BaseModel):
    command: str
    args: Dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[str] = None  # if omitted, targets the user's first connected agent
    timeout: float = 30.0


@api_router.get("/agent/commands")
async def agent_commands_catalog():
    return {"commands": AGENT_COMMANDS}


@api_router.post("/agent/command")
async def agent_command(req: AgentCommandRequest, request: Request):
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    if req.command not in AGENT_COMMANDS:
        raise HTTPException(400, f"Comando desconhecido: {req.command}")

    # Resolve target agent
    target = req.agent_id
    if not target:
        # Find a connected agent owned by this user
        prefix = f"{user['user_id']}:"
        target = next((aid for aid in EDGE_AGENT_HUB.connections.keys() if aid.startswith(prefix)), None)
    if not target:
        raise HTTPException(503, "Nenhum Edge Agent conectado para este usuário")

    # Register request future
    request_id = DISPATCHER.new_request()
    fut = DISPATCHER.register(request_id)
    ok = await EDGE_AGENT_HUB.send_command(target, {
        "type": "command",
        "request_id": request_id,
        "command": req.command,
        "args": req.args,
    })
    if not ok:
        DISPATCHER.cancel(request_id, "agent_not_reachable")
        raise HTTPException(503, "Edge Agent desconectou antes de responder")
    try:
        result = await asyncio.wait_for(fut, timeout=req.timeout)
        return {"ok": True, "request_id": request_id, "result": result}
    except asyncio.TimeoutError:
        DISPATCHER.cancel(request_id, "timeout")
        raise HTTPException(504, "Timeout aguardando resposta do Edge Agent")


@api_router.get("/agent/list")
async def agent_list(request: Request):
    user = await _current_user(request, db)
    if not user:
        raise HTTPException(401, "Login obrigatório")
    prefix = f"{user['user_id']}:"
    return {"agents": [aid for aid in EDGE_AGENT_HUB.connections.keys() if aid.startswith(prefix)]}


# ---------- Cognitive Profile (memory) ----------
@api_router.get("/memory/profile")
async def memory_profile(user_id: str = "owner"):
    p = await get_profile(db, user_id)
    return p or {"user_id": user_id, "preferences": [], "people": [], "topics": [], "active_tasks": [], "summary": ""}


@api_router.post("/memory/compact")
async def memory_compact(user_id: str = "owner"):
    cursor = db.messages.find({}, {"_id": 0}).sort("ts", -1).limit(24)
    recent = list(reversed(await cursor.to_list(24)))
    p = await compact_memory(db, user_id, recent)
    return {"ok": p is not None, "profile": p}


@api_router.delete("/memory/profile")
async def memory_clear(user_id: str = "owner"):
    await db.cognitive_profiles.delete_many({"user_id": user_id})
    return {"ok": True}


# ---------- Routes: Status check (legacy) ----------
@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    obj = StatusCheck(client_name=input.client_name)
    doc = obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for c in checks:
        if isinstance(c.get('timestamp'), str):
            c['timestamp'] = datetime.fromisoformat(c['timestamp'])
    return checks


# ---------- WebSocket: Edge Agent <-> Brain bridge ----------
class EdgeAgentHub:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, agent_id: str):
        await ws.accept()
        self.connections[agent_id] = ws

    def disconnect(self, agent_id: str):
        self.connections.pop(agent_id, None)

    async def send_command(self, agent_id: str, payload: dict) -> bool:
        ws = self.connections.get(agent_id)
        if not ws:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            self.disconnect(agent_id)
            return False

    async def broadcast(self, payload: dict):
        for aid in list(self.connections.keys()):
            await self.send_command(aid, payload)


EDGE_AGENT_HUB = EdgeAgentHub()


@app.websocket("/api/ws/agent/{agent_id}")
async def ws_edge_agent(ws: WebSocket, agent_id: str, token: Optional[str] = None):
    """Persistent channel: Edge Agent reports events; brain pushes commands.

    Authentication: agents SHOULD pass ?token=<agent_token>. Agents authenticated
    with an agent_token can only register under `{user_id}:*` agent_id. Legacy
    unauthenticated agents (e.g. the standalone edge_agent in owner mode) fall
    back to the raw agent_id for backward compatibility.
    """
    payload = decode_agent_token(token) if token else None
    if payload:
        user_id = payload.get("sub")
        agent_name = payload.get("agent") or "Home-PC"
        # Force canonical agent_id namespacing
        agent_id = f"{user_id}:{agent_name}"

    await EDGE_AGENT_HUB.connect(ws, agent_id)
    logger.info(f"Edge agent connected: {agent_id} (auth={'token' if payload else 'legacy'})")
    try:
        await ws.send_json({"type": "welcome", "agent_id": agent_id, "ts": now_iso()})
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                continue
            evt = data.get("type")
            if evt == "ping":
                await ws.send_json({"type": "pong", "ts": now_iso()})
            elif evt == "wake":
                await DASHBOARD_HUB.broadcast({
                    "type": "wake", "agent_id": agent_id,
                    "transcript": data.get("transcript"), "ts": now_iso(),
                })
            elif evt == "transcript":
                await DASHBOARD_HUB.broadcast({
                    "type": "transcript", "agent_id": agent_id,
                    "text": data.get("text"), "role": data.get("role", "user"),
                    "ts": now_iso(),
                })
            elif evt == "status":
                await DASHBOARD_HUB.broadcast({
                    "type": "agent_status", "agent_id": agent_id,
                    "data": data.get("data", {}), "ts": now_iso(),
                })
            elif evt == "command_result":
                rid = data.get("request_id")
                if rid:
                    DISPATCHER.resolve(rid, {
                        "ok": data.get("ok", True),
                        "output": data.get("output"),
                        "error": data.get("error"),
                    })
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WS edge agent error")
    finally:
        EDGE_AGENT_HUB.disconnect(agent_id)
        logger.info(f"Edge agent disconnected: {agent_id}")


# ---------- WebSocket: Dashboard subscribers ----------
class DashboardHub:
    def __init__(self):
        self.subs: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.subs.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.subs:
            self.subs.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in self.subs:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.disconnect(d)


DASHBOARD_HUB = DashboardHub()


@app.websocket("/api/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    await DASHBOARD_HUB.connect(ws)
    try:
        await ws.send_json({"type": "connected", "ts": now_iso()})
        while True:
            # We don't need messages from dashboard, but we keep the connection alive.
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await ws.send_json({"type": "pong", "ts": now_iso()})
                elif data.get("type") == "command":
                    # Send a command to one or all edge agents
                    target = data.get("agent_id")
                    payload = data.get("payload", {})
                    if target:
                        await EDGE_AGENT_HUB.send_command(target, payload)
                    else:
                        await EDGE_AGENT_HUB.broadcast(payload)
            except Exception:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        DASHBOARD_HUB.disconnect(ws)


# ---------- Mount router and CORS ----------
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
