"""J.A.R.V.I.S. Setup Wizard (Windows) — tkinter GUI.

Run this ONCE. It:
  1) Prompts for the BRAIN_URL (public URL of the JARVIS backend).
  2) Opens the JARVIS login page in the default browser.
  3) After the user logs in with Google, the SPA appends `?token=...` to the URL.
     The user pastes that URL (or just the token) here.
  4) The wizard calls /api/agent/download-config to fetch a ready-to-use
     agent.json and writes it to %USERPROFILE%\.jarvis\agent.json.
  5) Optionally launches the agent tray app.
"""
from __future__ import annotations
import json
import os
import re
import sys
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import tkinter as tk
from tkinter import ttk, messagebox

import requests

JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
JARVIS_HOME.mkdir(parents=True, exist_ok=True)
CFG_PATH = JARVIS_HOME / "agent.json"

DEFAULT_BRAIN = "https://cloud-mind-2.preview.emergentagent.com"


def extract_token(pasted: str) -> str:
    pasted = (pasted or "").strip()
    if not pasted:
        return ""
    # If they pasted a full URL, pull out ?token=
    if pasted.startswith("http"):
        try:
            q = parse_qs(urlparse(pasted).query)
            if q.get("token"):
                return q["token"][0]
        except Exception:
            pass
    # Match a JWT-like string
    m = re.search(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", pasted)
    return m.group(0) if m else pasted


class Wizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("J.A.R.V.I.S. — Configurar Edge Agent")
        self.geometry("640x460")
        self.configure(bg="#02060d")
        self.resizable(False, False)
        self._build()

    def _label(self, text, size=10, bold=False, color="#7dd3fc"):
        return tk.Label(self, text=text, bg="#02060d", fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def _build(self):
        self._label("J.A.R.V.I.S.", 24, True, "#a5f3fc").pack(pady=(24, 0))
        self._label("Configurar Edge Agent (Windows)", 10, False, "#67e8f9").pack()

        frame = tk.Frame(self, bg="#02060d")
        frame.pack(fill="both", expand=True, padx=32, pady=20)

        # 1. Brain URL
        self._label("1. URL do cérebro JARVIS", 10, True, "#cffafe").pack(anchor="w")
        self.brain_var = tk.StringVar(value=DEFAULT_BRAIN)
        ttk.Entry(self, textvariable=self.brain_var, width=70).pack(padx=32, pady=(2, 12), fill="x")

        # 2. Login button
        self._label("2. Faça login com Google", 10, True, "#cffafe").pack(anchor="w")
        row = tk.Frame(self, bg="#02060d")
        row.pack(fill="x", padx=32)
        ttk.Button(row, text="Abrir página de login", command=self.open_login).pack(side="left")
        self._label("→ depois copie a URL da barra do navegador (contém ?token=...)", 9, False, "#94a3b8").pack(side="left", padx=8)

        # 3. Paste token
        self._label("3. Cole a URL ou o token abaixo", 10, True, "#cffafe").pack(anchor="w", pady=(12, 0))
        self.token_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.token_var, width=70).pack(padx=32, pady=(2, 12), fill="x")

        # 4. Agent name
        self._label("4. Nome deste PC", 10, True, "#cffafe").pack(anchor="w")
        self.name_var = tk.StringVar(value=os.environ.get("COMPUTERNAME", "Home-PC"))
        ttk.Entry(self, textvariable=self.name_var, width=30).pack(padx=32, pady=(2, 12), anchor="w")

        # Actions
        actions = tk.Frame(self, bg="#02060d")
        actions.pack(fill="x", padx=32, pady=(8, 0))
        ttk.Button(actions, text="Salvar configuração", command=self.save).pack(side="left")
        ttk.Button(actions, text="Salvar e iniciar agente", command=self.save_and_run).pack(side="left", padx=8)
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="right")

        self.status = tk.Label(self, text="", bg="#02060d", fg="#f59e0b", font=("Segoe UI", 9))
        self.status.pack(pady=6)

    def open_login(self):
        brain = self.brain_var.get().strip().rstrip("/")
        if not brain:
            messagebox.showerror("J.A.R.V.I.S.", "Informe a URL do backend."); return
        webbrowser.open(brain + "/")

    def _fetch_config(self) -> dict | None:
        brain = self.brain_var.get().strip().rstrip("/")
        token = extract_token(self.token_var.get())
        agent = self.name_var.get().strip() or "Home-PC"
        if not (brain and token):
            messagebox.showerror("J.A.R.V.I.S.", "Preencha URL do backend e o token."); return None
        try:
            r = requests.get(
                f"{brain}/api/agent/download-config",
                params={"agent_name": agent, "token": token},
                timeout=15,
            )
            if r.status_code != 200:
                messagebox.showerror("J.A.R.V.I.S.", f"Erro HTTP {r.status_code}: {r.text[:200]}")
                return None
            return r.json()
        except Exception as e:
            messagebox.showerror("J.A.R.V.I.S.", f"Falha de rede: {e}")
            return None

    def save(self):
        cfg = self._fetch_config()
        if not cfg: return
        CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        self.status.configure(fg="#10b981", text=f"✔ gravado em {CFG_PATH}")

    def save_and_run(self):
        cfg = self._fetch_config()
        if not cfg: return
        CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        self.status.configure(fg="#10b981", text="iniciando agent_v2.py…")
        self.update_idletasks()
        agent_path = Path(__file__).resolve().parent.parent / "edge_agent" / "agent_v2.py"
        if not agent_path.exists():
            messagebox.showwarning("J.A.R.V.I.S.",
                f"agent_v2.py não encontrado em {agent_path}. Rode manualmente:\n  python agent_v2.py")
            return
        try:
            # Detached process, so wizard can close.
            DETACHED = 0x00000008 if sys.platform.startswith("win") else 0
            subprocess.Popen([sys.executable, str(agent_path)], creationflags=DETACHED)
            messagebox.showinfo("J.A.R.V.I.S.", "Agent iniciado em background.")
            self.destroy()
        except Exception as e:
            messagebox.showerror("J.A.R.V.I.S.", f"Falha ao iniciar agent: {e}")


def main():
    Wizard().mainloop()


if __name__ == "__main__":
    main()
