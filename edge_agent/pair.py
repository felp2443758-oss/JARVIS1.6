"""J.A.R.V.I.S. Edge Agent — pairing wizard.

Run ONCE on a new PC:
    python pair.py --brain https://your-jarvis.example.com --agent-name Home-PC

Opens the JARVIS login page, waits for the user to sign in with Google, then
fetches an `agent_token` and writes it to ~/.jarvis/agent.json.

Subsequent runs of `python agent_v2.py` will read that file and connect.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
JARVIS_HOME.mkdir(parents=True, exist_ok=True)
CFG_PATH = JARVIS_HOME / "agent.json"


def main():
    ap = argparse.ArgumentParser(description="Parear este PC com o cérebro J.A.R.V.I.S")
    ap.add_argument("--brain", required=True, help="URL do backend (ex.: https://jarvis-ai-1161.preview.emergentagent.com)")
    ap.add_argument("--agent-name", default="Home-PC", help="Nome amigável para este PC")
    args = ap.parse_args()
    brain = args.brain.rstrip("/")

    print(f"[pair] Abrindo login do JARVIS em {brain}/ ...")
    print("[pair] Após entrar com Google, copie o valor de 'token' da URL (aparece como '?token=...')")
    webbrowser.open(f"{brain}/?next=pair&agent={args.agent_name}")

    session_token = input("\n[pair] Cole aqui o session_token da URL: ").strip()
    if not session_token:
        print("[pair] cancelado", file=sys.stderr); sys.exit(2)

    r = requests.post(
        f"{brain}/api/auth/agent/pair",
        headers={"Authorization": f"Bearer {session_token}"},
        params={"agent_name": args.agent_name},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"[pair] erro HTTP {r.status_code}: {r.text}", file=sys.stderr); sys.exit(2)
    data = r.json()

    cfg = {
        "BRAIN_URL": brain,
        "AGENT_TOKEN": data["agent_token"],
        "AGENT_ID": data["agent_id"],
        "AGENT_NAME": data["agent_name"],
        "USER_ID": data["user_id"],
        "paired_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print(f"\n[pair] OK — token salvo em {CFG_PATH}")
    print(f"[pair] agent_id: {cfg['AGENT_ID']}")
    print("[pair] Rode agora: python agent_v2.py")


if __name__ == "__main__":
    main()
