"""Credential Vault (AES-GCM, per-user key).

Stores site logins (username/password/notes/cookies) encrypted at rest.
Only the JARVIS server can decrypt (key = HKDF(server_secret, user_id)).
The Edge Agent fetches decrypted credentials over HTTPS using its agent token.
"""
from __future__ import annotations
import os
import json
import base64
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from auth_service import derive_vault_key


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encrypt(user_id: str, plaintext: str) -> Dict[str, str]:
    key = derive_vault_key(user_id)
    aes = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return {
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ct": base64.b64encode(ct).decode("ascii"),
        "v": "aesgcm-1",
    }


def _decrypt(user_id: str, blob: Dict[str, str]) -> str:
    key = derive_vault_key(user_id)
    aes = AESGCM(key)
    nonce = base64.b64decode(blob["nonce"])
    ct = base64.b64decode(blob["ct"])
    pt = aes.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


async def put_credential(db, user_id: str, site: str, username: str, password: str,
                          url: Optional[str] = None, notes: Optional[str] = None,
                          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = json.dumps({
        "username": username,
        "password": password,
        "notes": notes or "",
        "extra": extra or {},
    })
    enc = _encrypt(user_id, payload)
    site_key = site.strip().lower()
    doc = {
        "user_id": user_id,
        "site": site_key,
        "site_display": site,
        "url": url,
        "blob": enc,
        "updated_at": _now(),
    }
    prev = await db.vault.find_one({"user_id": user_id, "site": site_key})
    if not prev:
        doc["created_at"] = _now()
    await db.vault.update_one(
        {"user_id": user_id, "site": site_key},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True, "site": site_key}


async def list_credentials(db, user_id: str) -> List[Dict[str, Any]]:
    cursor = db.vault.find({"user_id": user_id}, {"_id": 0, "blob": 0}).sort("updated_at", -1)
    return await cursor.to_list(200)


async def get_credential(db, user_id: str, site: str) -> Optional[Dict[str, Any]]:
    site_key = site.strip().lower()
    doc = await db.vault.find_one({"user_id": user_id, "site": site_key})
    if not doc:
        return None
    try:
        payload = json.loads(_decrypt(user_id, doc["blob"]))
    except Exception as e:
        return {"error": f"decrypt_failed: {e}"}
    return {
        "site": doc["site"],
        "site_display": doc.get("site_display"),
        "url": doc.get("url"),
        "username": payload.get("username"),
        "password": payload.get("password"),
        "notes": payload.get("notes"),
        "extra": payload.get("extra") or {},
        "updated_at": doc.get("updated_at"),
    }


async def delete_credential(db, user_id: str, site: str) -> bool:
    site_key = site.strip().lower()
    r = await db.vault.delete_one({"user_id": user_id, "site": site_key})
    return r.deleted_count > 0
