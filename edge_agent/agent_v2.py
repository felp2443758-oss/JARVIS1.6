"""J.A.R.V.I.S. Edge Agent v2 — command-driven, multi-user.

Reads config from ~/.jarvis/agent.json (created by pair.py) and connects to the
brain via authenticated WebSocket. Handles inbound commands (open_app, browser
control, etc.) and forwards results back.

Still supports the legacy wake-word / conversation loop if wake_word deps are
installed. Otherwise runs headless as a pure command executor.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import websockets

JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
CFG_PATH = JARVIS_HOME / "agent.json"

# Load config (either from ~/.jarvis/agent.json or from env)
cfg = {}
if CFG_PATH.exists():
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
for k in ("BRAIN_URL", "AGENT_TOKEN", "AGENT_ID"):
    if k not in cfg and os.getenv(k):
        cfg[k] = os.getenv(k)

BRAIN_URL = (cfg.get("BRAIN_URL") or "").rstrip("/")
AGENT_TOKEN = cfg.get("AGENT_TOKEN") or ""
AGENT_ID = cfg.get("AGENT_ID") or os.getenv("AGENT_ID", "edge-agent")

# Export for vault_client
os.environ["BRAIN_URL"] = BRAIN_URL
os.environ["AGENT_TOKEN"] = AGENT_TOKEN

from command_handler import handle_command  # noqa: E402


async def ws_loop():
    if not BRAIN_URL or not AGENT_TOKEN:
        print("[agent] ERRO: faca login no JARVIS Desktop primeiro (falta BRAIN_URL/AGENT_TOKEN em ~/.jarvis/agent.json).", file=sys.stderr)
        sys.exit(2)

    ws_url = BRAIN_URL.replace("http", "ws") + f"/api/ws/agent/{AGENT_ID}?token={AGENT_TOKEN}"
    backoff = 2
    while True:
        try:
            print(f"[agent] connecting: {ws_url}")
            async with websockets.connect(ws_url, ping_interval=20, max_size=8 * 1024 * 1024) as ws:
                print("[agent] connected")
                await ws.send(json.dumps({"type": "status", "data": {"online": True, "agent_id": AGENT_ID}}))
                backoff = 2
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("type") == "command":
                        request_id = msg.get("request_id")
                        cmd = msg.get("command", "")
                        args = msg.get("args", {}) or {}
                        print(f"[agent] <- {cmd}({list(args.keys())}) rid={request_id}")
                        result = await handle_command(cmd, args)
                        await ws.send(json.dumps({
                            "type": "command_result",
                            "request_id": request_id,
                            "ok": bool(result.get("ok")),
                            "output": result.get("output"),
                            "error": result.get("error"),
                        }))
                        print(f"[agent] -> ok={result.get('ok')}")
                    elif msg.get("type") == "welcome":
                        print(f"[agent] hello from brain: agent_id={msg.get('agent_id')}")
        except Exception as e:
            print(f"[agent] disconnected ({e}); retry in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2)


def main():
    try:
        asyncio.run(ws_loop())
    except KeyboardInterrupt:
        print("\n[agent] bye")


if __name__ == "__main__":
    main()
