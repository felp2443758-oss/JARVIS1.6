"""Dispatches command frames received over WebSocket to actions_v2 or browser_manager.

Expected inbound frame:
    { "type": "command", "request_id": "abc", "command": "open_app", "args": {...} }

Outbound response:
    { "type": "command_result", "request_id": "abc", "ok": true, "output": ... }
"""
from __future__ import annotations
import asyncio
import traceback
from typing import Any, Dict

from actions_v2 import (
    open_app, close_app, list_apps, open_url,
    type_text, press_keys, hotkey, screenshot,
    mouse_click, mouse_move, volume,
    file_read, file_write, doc_edit, shell_exec, system_info,
)
from browser_manager import BROWSER
from vault_client import get_credential


async def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


async def handle_command(command: str, args: Dict[str, Any]) -> Dict[str, Any]:
    args = args or {}
    try:
        # OS actions (sync -> run in thread to keep WS loop responsive)
        if command == "open_app":       return await _run_sync(open_app, args.get("name", ""))
        if command == "close_app":       return await _run_sync(close_app, args.get("name", ""))
        if command == "list_apps":       return await _run_sync(list_apps)
        if command == "open_url":        return await _run_sync(open_url, args.get("url", ""), bool(args.get("new_window", False)))
        if command == "type_text":       return await _run_sync(type_text, args.get("text", ""), float(args.get("interval", 0.02)))
        if command == "press_keys":      return await _run_sync(press_keys, list(args.get("keys", [])))
        if command == "hotkey":          return await _run_sync(hotkey, args.get("sequence", ""))
        if command == "screenshot":      return await _run_sync(screenshot)
        if command == "mouse_click":     return await _run_sync(mouse_click, int(args.get("x", 0)), int(args.get("y", 0)), args.get("button", "left"))
        if command == "mouse_move":      return await _run_sync(mouse_move, int(args.get("x", 0)), int(args.get("y", 0)), float(args.get("duration", 0.25)))
        if command == "volume":          return await _run_sync(volume, args.get("action", "up"), int(args.get("steps", 3)))
        if command == "file_read":       return await _run_sync(file_read, args.get("path", ""), int(args.get("max_bytes", 262144)))
        if command == "file_write":      return await _run_sync(file_write, args.get("path", ""), args.get("content", ""), args.get("mode", "overwrite"))
        if command == "doc_edit":        return await _run_sync(doc_edit, args.get("path", ""), args.get("instructions", ""))
        if command == "shell_exec":      return await _run_sync(shell_exec, args.get("command", ""), float(args.get("timeout", 30.0)))
        if command == "system_info":     return await _run_sync(system_info)

        # Browser (async native)
        if command == "browser_open":       return await BROWSER.open(args.get("url", "about:blank"))
        if command == "browser_navigate":   return await BROWSER.navigate(args.get("url", "about:blank"))
        if command == "browser_evaluate":   return await BROWSER.evaluate(args.get("script", "1+1"))
        if command == "browser_screenshot": return await BROWSER.screenshot()
        if command == "browser_search":     return await BROWSER.search(args.get("engine", "google"), args.get("query", ""))
        if command == "browser_login":
            site = args.get("site", "")
            url = args.get("url") or f"https://{site}"
            # Pull credentials from cloud vault if not provided inline
            username = args.get("username"); password = args.get("password")
            if not username or not password:
                cred = await get_credential(site)
                if not cred:
                    return {"ok": False, "error": f"Credenciais para '{site}' não encontradas no cofre"}
                username = cred.get("username"); password = cred.get("password")
                url = cred.get("url") or url
            return await BROWSER.login(site, url, username, password,
                                        username_selector=args.get("username_selector"),
                                        password_selector=args.get("password_selector"),
                                        submit_selector=args.get("submit_selector"))
        if command == "spotify_play":
            query = args.get("query", "")
            cred = await get_credential("spotify")
            u = (cred or {}).get("username"); p = (cred or {}).get("password")
            return await BROWSER.spotify_play(query, u, p)

        return {"ok": False, "error": f"Comando desconhecido: {command}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1000:]}
