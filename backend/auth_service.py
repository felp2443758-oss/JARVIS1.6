"""J.A.R.V.I.S. Multi-User Auth Service.

Handles Google OAuth per-user, JARVIS session JWTs, and Edge Agent pairing tokens.

Flow:
  1) User hits GET /api/auth/google/login -> returns Google OAuth URL with a fresh `state`.
  2) Google redirects to /api/auth/google/callback?code&state -> we exchange code for tokens,
     fetch userinfo (sub, email, name, picture) and upsert a `users` doc keyed by google `sub`.
  3) We issue a JARVIS JWT (`jarvis_token`) valid for 30 days and redirect back to '/'
     with `?token=...` so the SPA can store it.
  4) The SPA sends the JWT as `Authorization: Bearer <token>` on every request.
  5) Edge Agent pairing: authenticated user opens /api/auth/agent/pair -> receives a
     long-lived (365d) `agent_token` for `agent_name`. Agent uses it to open WS and
     hit /api/vault/get with `X-Agent-Token`.
"""
from __future__ import annotations
import os
import uuid
import hmac
import hashlib
import secrets
import base64
import json
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

import httpx
import jwt as pyjwt

USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
JWT_ALGO = "HS256"


def _server_secret() -> str:
    """Derive a stable server secret from env. Fallback to CLIENT_SECRET + REDIRECT_URI hash.
    NEVER expose this. Used for signing JWTs and deriving vault keys.
    """
    seed = (
        os.environ.get("JARVIS_SERVER_SECRET")
        or (os.environ.get("GOOGLE_CLIENT_SECRET", "") + "::" + os.environ.get("GOOGLE_REDIRECT_URI", ""))
        or "jarvis-dev-only-do-not-use-in-prod"
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


# -------------------- User model helpers --------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def fetch_userinfo(access_token: str) -> Optional[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10) as cx:
        r = await cx.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
        if r.status_code != 200:
            return None
        return r.json()


async def upsert_user(db, userinfo: Dict[str, Any], tokens: Dict[str, Any]) -> Dict[str, Any]:
    """Create/update user by Google `sub`. Returns user doc."""
    sub = userinfo.get("sub")
    if not sub:
        raise ValueError("userinfo missing sub")
    user_id = f"g:{sub}"  # namespaced user id
    doc = {
        "user_id": user_id,
        "google_sub": sub,
        "email": userinfo.get("email"),
        "name": userinfo.get("name") or userinfo.get("email") or "Usuário",
        "picture": userinfo.get("picture"),
        "locale": userinfo.get("locale"),
        "last_login": _now_iso(),
    }
    existing = await db.users.find_one({"user_id": user_id})
    if not existing:
        doc["created_at"] = _now_iso()
    await db.users.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)

    # Store Google tokens separately (they include refresh_token which we need to keep)
    token_doc = {
        "user_id": user_id,
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
        "scope": tokens.get("scope"),
        "ts": _now_iso(),
    }
    # Preserve existing refresh_token if new response omits it (Google returns it only on first consent)
    prev = await db.google_tokens.find_one({"user_id": user_id})
    if prev and not token_doc.get("refresh_token") and prev.get("refresh_token"):
        token_doc["refresh_token"] = prev["refresh_token"]
    await db.google_tokens.replace_one({"user_id": user_id}, token_doc, upsert=True)

    return {**doc, "created_at": (existing or {}).get("created_at") or doc.get("created_at")}


# -------------------- JWT session tokens --------------------
def issue_session_token(user: Dict[str, Any], ttl_days: int = 30) -> str:
    payload = {
        "sub": user["user_id"],
        "email": user.get("email"),
        "name": user.get("name"),
        "pic": user.get("picture"),
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_days * 86400,
        "typ": "session",
    }
    return pyjwt.encode(payload, _server_secret(), algorithm=JWT_ALGO)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        return pyjwt.decode(token, _server_secret(), algorithms=[JWT_ALGO])
    except Exception:
        return None


# -------------------- Edge Agent pairing tokens --------------------
def issue_agent_token(user_id: str, agent_name: str, ttl_days: int = 365) -> str:
    payload = {
        "sub": user_id,
        "agent": agent_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_days * 86400,
        "typ": "agent",
    }
    return pyjwt.encode(payload, _server_secret(), algorithm=JWT_ALGO)


def decode_agent_token(token: str) -> Optional[Dict[str, Any]]:
    data = decode_token(token)
    if not data or data.get("typ") != "agent":
        return None
    return data


# -------------------- Vault key derivation (per-user) --------------------
def derive_vault_key(user_id: str) -> bytes:
    """HKDF-like derivation of a 32-byte AES key from server_secret + user_id.
    Deterministic so the user does NOT need to provide a passphrase.
    Note: server compromise = vault compromise. This is acceptable for the MVP;
    a future upgrade can add user-provided passphrases.
    """
    seed = _server_secret().encode("utf-8") + b":vault:" + user_id.encode("utf-8")
    return hashlib.sha256(seed).digest()  # 32 bytes


# -------------------- FastAPI dependency helpers --------------------
def extract_bearer(request) -> Optional[str]:
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(None, 1)[1].strip()
    # Also allow ?token= for redirect flows
    return request.query_params.get("token")


async def current_user(request, db) -> Optional[Dict[str, Any]]:
    tok = extract_bearer(request)
    payload = decode_token(tok) if tok else None
    if not payload or payload.get("typ") != "session":
        return None
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
    return user
