"""Tavily web search & deep research integration.

Provides:
 - quick_search: fast factual web search with snippets + URLs
 - deep_research: deeper aggregation + answer summarization (advanced search depth)
 - image_search: search the web for image URLs
"""
from __future__ import annotations
import os
import logging
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger("jarvis.tavily")

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_BASE = "https://api.tavily.com"


async def quick_search(query: str, max_results: int = 6, include_answer: bool = True) -> Dict[str, Any]:
    """Basic Tavily search. Returns {answer, results: [{title, url, content, score}], images}."""
    if not TAVILY_API_KEY:
        return {"answer": None, "results": [], "images": [], "error": "no_api_key"}
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_answer": include_answer,
        "include_images": False,
        "max_results": max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as cx:
            r = await cx.post(f"{TAVILY_BASE}/search", json=payload)
        if r.status_code != 200:
            return {"answer": None, "results": [], "images": [], "error": f"http_{r.status_code}", "detail": r.text[:200]}
        data = r.json()
        return {
            "answer": data.get("answer"),
            "query": query,
            "results": [
                {
                    "title": it.get("title"),
                    "url": it.get("url"),
                    "content": (it.get("content") or "")[:600],
                    "score": it.get("score"),
                }
                for it in (data.get("results") or [])
            ],
            "images": data.get("images") or [],
        }
    except Exception as e:
        logger.exception("tavily quick_search failed")
        return {"answer": None, "results": [], "images": [], "error": str(e)}


async def deep_research(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Advanced search depth + raw content + larger max_results."""
    if not TAVILY_API_KEY:
        return {"answer": None, "results": [], "images": [], "error": "no_api_key"}
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": True,
        "include_images": True,
        "max_results": max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=45) as cx:
            r = await cx.post(f"{TAVILY_BASE}/search", json=payload)
        if r.status_code != 200:
            return {"answer": None, "results": [], "images": [], "error": f"http_{r.status_code}", "detail": r.text[:300]}
        data = r.json()
        return {
            "answer": data.get("answer"),
            "query": query,
            "results": [
                {
                    "title": it.get("title"),
                    "url": it.get("url"),
                    "content": (it.get("content") or "")[:1500],
                    "raw_content": (it.get("raw_content") or "")[:4000],
                    "score": it.get("score"),
                }
                for it in (data.get("results") or [])
            ],
            "images": data.get("images") or [],
        }
    except Exception as e:
        logger.exception("tavily deep_research failed")
        return {"answer": None, "results": [], "images": [], "error": str(e)}


async def image_search(query: str, max_results: int = 8) -> List[str]:
    """Returns a list of image URLs matching the query."""
    if not TAVILY_API_KEY:
        return []
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_images": True,
        "include_answer": False,
        "max_results": max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as cx:
            r = await cx.post(f"{TAVILY_BASE}/search", json=payload)
        if r.status_code != 200:
            return []
        data = r.json()
        imgs = data.get("images") or []
        # Normalise: API may return list of strings or list of dicts
        out: List[str] = []
        for i in imgs:
            if isinstance(i, str):
                out.append(i)
            elif isinstance(i, dict) and i.get("url"):
                out.append(i["url"])
        return out
    except Exception:
        logger.exception("tavily image_search failed")
        return []


def format_results_for_llm(payload: Dict[str, Any]) -> str:
    """Compress search results into a concise text block for LLM context."""
    if not payload:
        return ""
    lines = []
    if payload.get("answer"):
        lines.append(f"Resposta direta (Tavily): {payload['answer']}")
    results = payload.get("results") or []
    for i, r in enumerate(results[:6], 1):
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip()
        lines.append(f"[{i}] {title}\n    {url}\n    {content[:500]}")
    return "\n".join(lines)
