"""Media generation tools — Images (OpenAI gpt-image-1 via Emergent) + Video (Fal.ai)."""
from __future__ import annotations
import os
import base64
import logging
import asyncio
from typing import Optional, Dict, Any, List

import fal_client

logger = logging.getLogger("jarvis.media")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
FAL_KEY = os.environ.get("FAL_KEY", "")
if FAL_KEY:
    os.environ["FAL_KEY"] = FAL_KEY


async def generate_image_gpt(prompt: str, n: int = 1, size: str = "1024x1024") -> Dict[str, Any]:
    """OpenAI gpt-image-1 via Emergent integrations. Returns base64 PNGs."""
    if not EMERGENT_LLM_KEY:
        return {"error": "missing_emergent_key"}
    try:
        from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
        gen = OpenAIImageGeneration(api_key=EMERGENT_LLM_KEY)
        images = await gen.generate_images(prompt=prompt, model="gpt-image-1", number_of_images=max(1, min(n, 4)))
        # images is list of bytes
        out = []
        for raw in images or []:
            if isinstance(raw, (bytes, bytearray)):
                out.append({"b64": base64.b64encode(bytes(raw)).decode("ascii"), "mime": "image/png"})
            elif isinstance(raw, str):
                # already base64 or URL
                if raw.startswith("http"):
                    out.append({"url": raw})
                else:
                    out.append({"b64": raw, "mime": "image/png"})
        return {"provider": "openai/gpt-image-1", "prompt": prompt, "images": out}
    except Exception as e:
        logger.exception("gpt-image-1 failed")
        return {"error": str(e), "provider": "openai/gpt-image-1"}


async def generate_image_nano_banana(prompt: str) -> Dict[str, Any]:
    """Fallback: Gemini Nano Banana via Emergent integrations.

    Note: the installed emergentintegrations lib uses google.genai directly,
    so it requires a real Google API key (GOOGLE_API_KEY) rather than
    EMERGENT_LLM_KEY for this code path.
    """
    api_key = GOOGLE_API_KEY or EMERGENT_LLM_KEY
    if not api_key:
        return {"error": "missing_google_api_key", "provider": "gemini/nano-banana"}
    try:
        # Note: emergentintegrations package uses 'gemeni' (sic) as the subpackage name.
        try:
            from emergentintegrations.llm.gemeni.image_generation import GeminiImageGeneration  # type: ignore
        except ImportError:
            from emergentintegrations.llm.gemini.image_generation import GeminiImageGeneration  # fallback if typo gets fixed upstream
        gen = GeminiImageGeneration(api_key=api_key)
        images = await gen.generate_images(prompt=prompt, model="gemini-2.5-flash-image-preview", number_of_images=1)
        out = []
        for raw in images or []:
            if isinstance(raw, (bytes, bytearray)):
                out.append({"b64": base64.b64encode(bytes(raw)).decode("ascii"), "mime": "image/png"})
        return {"provider": "gemini/nano-banana", "prompt": prompt, "images": out}
    except Exception as e:
        logger.exception("nano-banana failed")
        return {"error": str(e), "provider": "gemini/nano-banana"}


# ---------- Video (Fal.ai) ----------
FAL_VIDEO_MODELS = {
    "veo3-fast": "fal-ai/veo3/fast",
    "veo3": "fal-ai/veo3",
    "kling-v2": "fal-ai/kling-video/v2/master/text-to-video",
    "luma": "fal-ai/luma-dream-machine",
}


def _normalize_video_result(model_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Try to extract video URL from various Fal.ai response shapes."""
    url = None
    if isinstance(data, dict):
        # common shape: {"video": {"url": ...}} or {"video_url": ...}
        v = data.get("video")
        if isinstance(v, dict):
            url = v.get("url")
        elif isinstance(v, str):
            url = v
        url = url or data.get("video_url") or data.get("url")
        if not url and isinstance(data.get("videos"), list) and data["videos"]:
            first = data["videos"][0]
            url = first.get("url") if isinstance(first, dict) else first
    return {"provider": model_id, "video_url": url, "raw": data}


async def generate_video(prompt: str, model: str = "veo3-fast", duration_seconds: int = 8, aspect_ratio: str = "16:9") -> Dict[str, Any]:
    """Generate a short text-to-video via Fal.ai. Returns {video_url}."""
    if not FAL_KEY:
        return {"error": "missing_fal_key"}
    model_id = FAL_VIDEO_MODELS.get(model, FAL_VIDEO_MODELS["veo3-fast"])
    args = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "duration": f"{duration_seconds}s",
    }
    try:
        handler = await fal_client.submit_async(model_id, arguments=args)
        result = await handler.get()
        return _normalize_video_result(model_id, result or {})
    except Exception as e:
        logger.exception("fal video failed")
        return {"error": str(e), "provider": model_id}
