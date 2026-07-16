"""Image analysis via Gemini multimodal (Emergent integrations).

Accepts an image (bytes or URL) + question, returns a textual analysis.
Uses Gemini 2.5 Flash multimodal via emergentintegrations.LlmChat with image content.
"""
from __future__ import annotations
import os
import base64
import logging
import uuid
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, FileContentWithMimeType

logger = logging.getLogger("jarvis.vision")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

VISION_SYSTEM = (
    "Você é o módulo de visão computacional do J.A.R.V.I.S. — atua como o sentido visual "
    "do operador Felipe Stark. Descreva imagens de forma técnica, objetiva e em Português do Brasil. "
    "Identifique objetos, pessoas (sem identificar identidades específicas), texto visível (faça OCR), "
    "cores, atmosfera, riscos ou pontos relevantes. Seja conciso (3-6 frases) salvo se o operador pedir detalhes."
)


def _save_temp_image(raw: bytes, suffix: str = ".png") -> Path:
    p = Path(tempfile.gettempdir()) / f"jarvis_vision_{uuid.uuid4().hex}{suffix}"
    p.write_bytes(raw)
    return p


async def analyze_image_bytes(image_bytes: bytes, mime_type: str = "image/png", question: Optional[str] = None) -> str:
    if not EMERGENT_LLM_KEY:
        return "(módulo de visão indisponível: EMERGENT_LLM_KEY não configurada)"
    # base64 for ImageContent
    b64 = base64.b64encode(image_bytes).decode("ascii")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"vision-{uuid.uuid4().hex[:8]}",
        system_message=VISION_SYSTEM,
    ).with_model("gemini", "gemini-2.5-flash")
    q = question or "Descreva esta imagem em detalhes. Se houver texto, faça OCR completo."
    try:
        # Try ImageContent first (preferred API)
        msg = UserMessage(text=q, file_contents=[ImageContent(image_base64=b64)])
        resp = await chat.send_message(msg)
    except Exception as e1:
        logger.warning(f"ImageContent path failed: {e1}; falling back to file-on-disk")
        try:
            ext = ".png" if "png" in (mime_type or "") else (".jpg" if "jpeg" in (mime_type or "") else ".bin")
            p = _save_temp_image(image_bytes, ext)
            msg = UserMessage(text=q, file_contents=[FileContentWithMimeType(file_path=str(p), mime_type=mime_type or "image/png")])
            resp = await chat.send_message(msg)
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e2:
            logger.exception("vision analyze failed")
            return f"(falha ao analisar imagem: {e2})"
    return (resp or "").strip()


async def analyze_image_url(url: str, question: Optional[str] = None) -> str:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cx:
            r = await cx.get(url)
        if r.status_code != 200:
            return f"(não foi possível baixar a imagem: HTTP {r.status_code})"
        mime = r.headers.get("content-type", "image/png").split(";")[0]
        return await analyze_image_bytes(r.content, mime_type=mime, question=question)
    except Exception as e:
        logger.exception("analyze_image_url failed")
        return f"(falha ao baixar/analisar URL da imagem: {e})"
