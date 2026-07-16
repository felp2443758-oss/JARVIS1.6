"""J.A.R.V.I.S. Desktop — modern login + embedded dashboard (no pairing needed).

Flow:
  1) User double-clicks JARVIS.exe (or tray "Login").
  2) A local HTTP server listens on 127.0.0.1:<random-free-port>/callback.
  3) System browser opens <BRAIN_URL>/api/auth/google/desktop?redirect=<local>.
  4) After Google login, backend redirects to the local URL with:
       ?token=<session_jwt>&agent_token=<agent_jwt>&brain_url=<...>&...
  5) We store ~/.jarvis/agent.json, close the login window and show the
     dashboard in an embedded webview (pywebview + Edge WebView2).
  6) Edge agent (agent_v2.py) is spawned in background using the AGENT_TOKEN.

No copy/paste. No pairing. No external browser tabs left open.
"""
from __future__ import annotations
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
JARVIS_HOME.mkdir(parents=True, exist_ok=True)
CFG_PATH = JARVIS_HOME / "agent.json"

DEFAULT_BRAIN = os.environ.get(
    "JARVIS_BRAIN_URL",
    "https://cloud-mind-2.preview.emergentagent.com",
).rstrip("/")


# --------------------------------------------------------------------------
# Loopback HTTP server that catches the OAuth redirect
# --------------------------------------------------------------------------
class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server_result: dict | None = None  # set on the server instance

    def log_message(self, format, *args):  # silence stdout
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/callback", "/"):
            self.send_response(404); self.end_headers(); return

        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        # Save result on the server object
        self.server.result = qs  # type: ignore[attr-defined]

        # Show a friendly success/error page
        ok = bool(qs.get("token"))
        html = _success_html() if ok else _error_html(qs)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


def _success_html() -> str:
    return """<!doctype html><html lang=pt-BR><head>
<meta charset=utf-8><title>J.A.R.V.I.S. — Login OK</title>
<style>
 body{margin:0;background:#02060d;color:#cffafe;font-family:'Segoe UI',system-ui;
      display:flex;align-items:center;justify-content:center;height:100vh}
 .box{text-align:center;max-width:420px}
 .ring{width:96px;height:96px;border:3px solid #22d3ee;border-top-color:transparent;
       border-radius:50%;margin:0 auto 20px;animation:s 1.2s linear infinite}
 h1{color:#a5f3fc;letter-spacing:.12em;font-size:20px;margin:8px 0}
 p{color:#7dd3fc;font-size:13px}
 @keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
<div class=box>
 <div class=ring></div>
 <h1>AUTENTICADO</h1>
 <p>Voce ja pode fechar esta aba. O J.A.R.V.I.S. Desktop assumiu o controle.</p>
</div>
<script>setTimeout(()=>window.close(),1400);</script>
</body></html>"""


def _error_html(qs: dict) -> str:
    err = qs.get("error", "desconhecido")
    return f"""<!doctype html><html><body style='background:#02060d;color:#f87171;
font-family:Segoe UI;padding:40px'>
<h2>Falha no login</h2><pre>{err}</pre></body></html>"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def do_login_flow(brain_url: str = DEFAULT_BRAIN, agent_name: str = "",
                  timeout_s: int = 300) -> dict | None:
    """Blocks until user completes Google login. Returns credential dict or None."""
    if not agent_name:
        agent_name = os.environ.get("COMPUTERNAME") or socket.gethostname() or "Home-PC"

    port = _free_port()
    server = socketserver.TCPServer(("127.0.0.1", port), _CallbackHandler)
    server.result = None  # type: ignore[attr-defined]
    server.timeout = 1.0

    from urllib.parse import quote
    login_url = (
        f"{brain_url.rstrip('/')}/api/auth/google/desktop"
        f"?redirect={quote(f'http://127.0.0.1:{port}/callback')}"
        f"&agent_name={quote(agent_name)}"
    )

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    deadline = time.time() + timeout_s
    result = None
    while time.time() < deadline:
        r = getattr(server, "result", None)
        if r:
            result = r
            break
        time.sleep(0.25)

    server.shutdown()
    try: server.server_close()
    except Exception: pass

    if not result or "token" not in result:
        return None

    cfg = {
        "BRAIN_URL": result.get("brain_url") or brain_url,
        "SESSION_TOKEN": result["token"],
        "AGENT_TOKEN": result.get("agent_token", ""),
        "AGENT_NAME": result.get("agent_name") or agent_name,
        "AGENT_ID": f"{result.get('user_id','')}:{result.get('agent_name') or agent_name}",
        "USER_ID": result.get("user_id", ""),
        "USER_EMAIL": result.get("email", ""),
        "USER_NAME": result.get("name", ""),
    }
    CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


# --------------------------------------------------------------------------
# Embedded dashboard window (pywebview with Edge WebView2, no external browser)
# --------------------------------------------------------------------------
def open_dashboard_window(cfg: dict, title: str = "J.A.R.V.I.S."):
    brain = cfg.get("BRAIN_URL", DEFAULT_BRAIN).rstrip("/")
    token = cfg.get("SESSION_TOKEN", "")
    url = f"{brain}/?token={token}" if token else brain
    try:
        import webview  # pywebview
        w = webview.create_window(
            title, url,
            width=1360, height=860, resizable=True,
            background_color="#02060d",
        )
        # Try Edge WebView2 first (Win10+), fallback to system default
        try:
            webview.start(gui="edgechromium")
        except Exception:
            webview.start()
        return True
    except Exception as e:
        # Graceful fallback: system browser
        print(f"[jarvis] pywebview indisponivel ({e}); abrindo browser padrao")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return False


# --------------------------------------------------------------------------
# Login screen (before webview) — tkinter mini window with a big login button
# --------------------------------------------------------------------------
def show_login_screen(on_login) -> None:
    """Minimal HUD-style tk window with a 'Sign in with Google' button.
    Calls on_login() when clicked. Closes when login succeeds or user quits.
    """
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("J.A.R.V.I.S. — Login")
    root.geometry("520x360")
    root.configure(bg="#02060d")
    root.resizable(False, False)

    tk.Label(root, text="J.A.R.V.I.S.", bg="#02060d", fg="#a5f3fc",
             font=("Segoe UI", 30, "bold")).pack(pady=(48, 6))
    tk.Label(root, text="Cloud Brain \u00b7 Edge Agent", bg="#02060d",
             fg="#67e8f9", font=("Segoe UI", 10)).pack()

    status = tk.Label(root, text="", bg="#02060d", fg="#7dd3fc",
                      font=("Segoe UI", 10))
    status.pack(pady=(28, 8))

    def click():
        btn.configure(state="disabled")
        status.configure(text="Abrindo navegador para autenticacao...")
        root.update_idletasks()

        def worker():
            cfg = do_login_flow()
            if cfg:
                status.configure(text="Autenticado. Iniciando dashboard...", fg="#34d399")
                root.after(600, root.destroy)
                # Store cfg in a mutable holder for the caller
                on_login(cfg)
            else:
                status.configure(text="Login cancelado ou expirou. Tente novamente.",
                                 fg="#f87171")
                btn.configure(state="normal")
        threading.Thread(target=worker, daemon=True).start()

    style = ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("Cyan.TButton", background="#22d3ee", foreground="#02060d",
                    font=("Segoe UI", 11, "bold"), padding=10)
    style.map("Cyan.TButton", background=[("active", "#67e8f9")])

    btn = ttk.Button(root, text="Entrar com Google", style="Cyan.TButton",
                     command=click)
    btn.pack(pady=8, ipadx=20)

    tk.Label(root,
             text=f"URL do cerebro: {DEFAULT_BRAIN}",
             bg="#02060d", fg="#475569", font=("Segoe UI", 8)).pack(side="bottom", pady=10)

    root.mainloop()


# --------------------------------------------------------------------------
# Full desktop app entry point (login + dashboard)
# --------------------------------------------------------------------------
def run():
    """Main entry: shows login if needed, then dashboard."""
    if CFG_PATH.exists():
        try:
            cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            if cfg.get("SESSION_TOKEN"):
                open_dashboard_window(cfg)
                return
        except Exception:
            pass

    cfg_holder: dict = {}
    def _on(cfg): cfg_holder.update(cfg)
    show_login_screen(_on)

    if cfg_holder:
        open_dashboard_window(cfg_holder)


if __name__ == "__main__":
    run()
