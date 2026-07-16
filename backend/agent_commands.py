"""Command dispatch: brain -> edge agent, with request/response correlation.

Used by chat/LLM tool calls and by the frontend action buttons to instruct the
user's Edge Agent to perform local actions (open app, open URL, browser login,
type text, screenshot, edit document, etc.).
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Any, Dict, Optional, List


class CommandDispatcher:
    """Correlates command requests sent to edge agents with their async results."""

    def __init__(self):
        self._pending: Dict[str, asyncio.Future] = {}

    def new_request(self) -> str:
        return uuid.uuid4().hex[:12]

    def register(self, request_id: str) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._pending[request_id] = fut
        return fut

    def resolve(self, request_id: str, payload: Dict[str, Any]) -> bool:
        fut = self._pending.pop(request_id, None)
        if fut and not fut.done():
            fut.set_result(payload)
            return True
        return False

    def cancel(self, request_id: str, reason: str = "cancelled"):
        fut = self._pending.pop(request_id, None)
        if fut and not fut.done():
            fut.set_exception(TimeoutError(reason))


DISPATCHER = CommandDispatcher()


# List of commands the Edge Agent MUST support. Keep in sync with edge_agent/actions_v2.py
AGENT_COMMANDS: List[str] = [
    "open_app",             # {name}
    "open_url",             # {url, new_window}
    "close_app",            # {name}
    "list_apps",            # -> list of running apps
    "type_text",            # {text, interval}
    "press_keys",           # {keys: ["ctrl","s"]}
    "hotkey",                # {sequence: "ctrl+shift+esc"}
    "screenshot",           # -> {b64, mime}
    "mouse_click",          # {x, y, button}
    "mouse_move",           # {x, y}
    "volume",                # {action: up|down|mute, steps}
    "browser_open",         # {url}
    "browser_login",        # {site, url?, username_selector?, password_selector?, submit_selector?}
    "browser_navigate",     # {url}
    "browser_evaluate",     # {script}
    "browser_screenshot",   # -> {b64, mime}
    "browser_search",       # {engine, query}
    "spotify_play",         # {query} -> uses browser autologin + search
    "file_read",             # {path}
    "file_write",            # {path, content}
    "doc_edit",              # {path, instructions}  (docx/txt)
    "shell_exec",            # {command}  (opt-in in agent config)
    "system_info",           # -> {os, ram, cpu, battery}
]
