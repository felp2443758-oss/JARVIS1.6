"""J.A.R.V.I.S. Desktop — entry point EXE.

Modes dispatched by argv (avoids the PyInstaller fork bomb — sys.executable IS
the frozen JARVIS.exe, so subprocess.Popen(sys.executable) re-runs the whole
app; without argv dispatch every spawn recurses forever):

  JARVIS.exe                 -> full desktop app (login + embedded dashboard) + tray
  JARVIS.exe --agent         -> runs edge_agent/agent_v2.py in this process
  JARVIS.exe --tray-only     -> tray icon only (used internally)
  JARVIS.exe --dashboard     -> reopens the embedded dashboard window
"""
from __future__ import annotations
import os
import sys
import json
import time
import runpy
import subprocess
import threading
import webbrowser
from pathlib import Path

# --- PyInstaller belt & suspenders: force-include GUI/net deps -----------
try:
    import tkinter  # noqa: F401
    import tkinter.ttk  # noqa: F401
    import tkinter.messagebox  # noqa: F401
    import tkinter.filedialog  # noqa: F401
    import tkinter.simpledialog  # noqa: F401
    import tkinter.font  # noqa: F401
except Exception:
    pass
try:
    import requests  # noqa: F401
    import websockets  # noqa: F401
    import httpx  # noqa: F401
except Exception:
    pass
try:
    import webview  # noqa: F401  # pywebview
except Exception:
    pass


def _resource_root() -> Path:
    """Where bundled resources live (works dev + PyInstaller frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
JARVIS_HOME.mkdir(parents=True, exist_ok=True)
CFG_PATH = JARVIS_HOME / "agent.json"
LOG_PATH = JARVIS_HOME / "agent.log"
LOCK_PATH = JARVIS_HOME / "tray.lock"

RES = _resource_root()
AGENT_PY = RES / "edge_agent" / "agent_v2.py"
DESKTOP_APP_PY = RES / "desktop_app.py"


# ==========================================================================
# argv-dispatched modes (no subprocess -> no fork bomb)
# ==========================================================================
def run_agent_inproc():
    """Runs edge_agent/agent_v2.py in the current process (blocking)."""
    agent = AGENT_PY
    if not agent.exists():
        agent = Path(__file__).resolve().parent.parent / "edge_agent" / "agent_v2.py"
    sys.path.insert(0, str(agent.parent))
    runpy.run_path(str(agent), run_name="__main__")


def run_desktop_inproc():
    """Runs desktop_app.py in the current process (blocking)."""
    dp = DESKTOP_APP_PY
    if not dp.exists():
        dp = Path(__file__).resolve().parent / "desktop_app.py"
    sys.path.insert(0, str(dp.parent))
    runpy.run_path(str(dp), run_name="__main__")


# ==========================================================================
# Tray + agent lifecycle
# ==========================================================================
def _acquire_singleton() -> bool:
    """Prevents multiple tray instances from spawning."""
    try:
        if LOCK_PATH.exists():
            try:
                pid = int(LOCK_PATH.read_text().strip() or "0")
            except Exception:
                pid = 0
            if pid > 0 and sys.platform.startswith("win"):
                try:
                    import ctypes
                    PROCESS_QUERY_LIMITED = 0x1000
                    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
                    if h:
                        ctypes.windll.kernel32.CloseHandle(h)
                        return False
                except Exception:
                    pass
        LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return True


class AgentManager:
    """Spawns 'JARVIS.exe --agent' (or 'python agent_v2.py' in dev)."""
    def __init__(self):
        self.proc: "subprocess.Popen | None" = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _agent_cmd(self):
        if getattr(sys, "frozen", False):
            return [sys.executable, "--agent"]
        return [sys.executable, str(AGENT_PY)]

    def start(self):
        if self.is_running():
            return
        if not CFG_PATH.exists():
            return
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logf = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        logf.write(f"\n===== agent start at {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        DETACHED = 0x00000008 if sys.platform.startswith("win") else 0
        CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0
        try:
            self.proc = subprocess.Popen(
                self._agent_cmd(),
                stdout=logf, stderr=subprocess.STDOUT,
                creationflags=DETACHED | CREATE_NO_WINDOW,
            )
        except Exception as e:
            logf.write(f"[tray] falha ao spawnar agent: {e}\n")
            self.proc = None

    def stop(self):
        if self.is_running():
            try: self.proc.terminate()
            except Exception: pass
            try: self.proc.wait(timeout=5)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
        self.proc = None

    def restart(self):
        self.stop(); time.sleep(0.4); self.start()


def _spawn_dashboard():
    """Reopens the embedded dashboard window (via subprocess so tray keeps running)."""
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "--dashboard"])
    else:
        subprocess.Popen([sys.executable, str(DESKTOP_APP_PY)])


def tray_main():
    """Runs the system tray icon + agent lifecycle."""
    if not _acquire_singleton():
        print("[tray] outra instancia ja esta rodando. Saindo.")
        return

    try:
        import pystray
        from pystray import MenuItem as Item, Menu
        from PIL import Image, ImageDraw
    except Exception as e:
        print(f"[tray] pystray/pillow indisponivel: {e}")
        # Fallback: just run desktop app blocking
        run_desktop_inproc()
        return

    def _make_icon(color=(34, 211, 238)):
        for name in ("resources/jarvis.png", "jarvis.png"):
            p = RES / name
            if p.exists():
                try:
                    return Image.open(str(p)).convert("RGBA")
                except Exception:
                    pass
        img = Image.new("RGBA", (64, 64), (2, 6, 13, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, 58, 58), outline=color, width=3)
        d.ellipse((18, 18, 46, 46), outline=color, width=2)
        d.ellipse((28, 28, 36, 36), fill=color)
        return img

    mgr = AgentManager()
    if CFG_PATH.exists():
        mgr.start()

    def open_dashboard(icon, item):
        _spawn_dashboard()

    def open_logs(icon, item):
        if LOG_PATH.exists():
            if sys.platform.startswith("win"):
                os.startfile(str(LOG_PATH))  # noqa
            else:
                subprocess.Popen(["xdg-open", str(LOG_PATH)])

    def relogin(icon, item):
        # Force re-login by wiping config and reopening desktop app
        try: CFG_PATH.unlink(missing_ok=True)
        except Exception: pass
        mgr.stop()
        _spawn_dashboard()

    def status_label(item=None):
        return f"Agent: {'online' if mgr.is_running() else 'offline'}"

    def _quit(icon):
        try: mgr.stop()
        except Exception: pass
        try: LOCK_PATH.unlink(missing_ok=True)
        except Exception: pass
        icon.stop()

    menu = Menu(
        Item(status_label, None, enabled=False),
        Menu.SEPARATOR,
        Item("Abrir dashboard", open_dashboard, default=True),
        Menu.SEPARATOR,
        Item("Iniciar agente", lambda i, it: mgr.start()),
        Item("Parar agente", lambda i, it: mgr.stop()),
        Item("Reiniciar agente", lambda i, it: mgr.restart()),
        Menu.SEPARATOR,
        Item("Abrir logs", open_logs),
        Item("Trocar de conta / Reautenticar", relogin),
        Menu.SEPARATOR,
        Item("Sair", lambda i, it: _quit(i)),
    )
    icon = pystray.Icon("jarvis", _make_icon(), "J.A.R.V.I.S.", menu)
    icon.run()


def full_app():
    """Default entry: login+dashboard window AND tray icon (parallel).

    - If no config: shows the login screen; on success starts agent + tray.
    - If config exists: opens dashboard window AND starts tray + agent.
    """
    # 1) Start tray in a daemon thread so it can spawn subprocesses independently.
    t = threading.Thread(target=tray_main, daemon=True)
    t.start()

    # 2) Run the desktop_app (blocking): shows login if needed, then dashboard.
    #    When the user closes the window, the tray keeps running.
    try:
        run_desktop_inproc()
    except Exception as e:
        print(f"[jarvis] desktop_app crashed: {e}")

    # 3) When dashboard window closes, keep tray alive by joining thread.
    try:
        t.join()
    except KeyboardInterrupt:
        pass


def main():
    args = sys.argv[1:]
    if args:
        mode = args[0].lstrip("-").lower()
        if mode in ("agent", "edge"):
            run_agent_inproc(); return
        if mode in ("dashboard", "webview"):
            run_desktop_inproc(); return
        if mode in ("tray-only", "tray"):
            tray_main(); return
        if mode in ("help", "h"):
            print("Uso: JARVIS.exe [--agent | --dashboard | --tray-only]"); return
    full_app()


if __name__ == "__main__":
    main()
