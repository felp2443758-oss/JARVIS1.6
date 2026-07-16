"""Client for the cloud vault. Uses the agent's own agent_token as auth."""
from __future__ import annotations
import os
from typing import Optional, Dict, Any

import httpx


def _brain_url() -> str:
    return os.environ.get("BRAIN_URL", "").rstrip("/")


def _agent_token() -> str:
    return os.environ.get("AGENT_TOKEN", "")


async def get_credential(site: str) -> Optional[Dict[str, Any]]:
    base = _brain_url()
    tok = _agent_token()
    if not base or not tok:
        return None
    async with httpx.AsyncClient(timeout=15) as cx:
        r = await cx.get(f"{base}/api/vault/get/{site}", headers={"X-Agent-Token": tok})
        if r.status_code != 200:
            return None
        return r.json()
