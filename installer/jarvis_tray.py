"""J.A.R.V.I.S. — System tray icon (Windows).

Single-entry-point EXE with argv routing to avoid the PyInstaller fork-bomb
(sys.executable IS the frozen JARVIS.exe, so subprocess.Popen re-runs the whole
app; without argv dispatch every spawn recurses forever).

Modes:
  JARVIS.exe                 → tray icon (default)
  JARVIS.exe --wizard        → runs setup_wizard in-process
  JARVIS.exe --agent         → runs edge_agent/agent_v2.py in-process
"""
from __future__ import annotations
import os
import sys
import json
import time
import runpy
import subprocess
import webbrowser
from pathlib import Path


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
WIZARD_PY = RES / "setup_wizard.py"


# ---------------------------------------------------------------------------
# Modes dispatched by argv (avoid fork bomb when frozen)
# ---------------------------------------------------------------------------
def run_wizard_inproc():
    """Runs setup_wizard.py in the current process (blocks until closed)."""
    wiz = WIZARD_PY
    if not wiz.exists():
        # dev fallback
        wiz = Path(__file__).resolve().parent / "setup_wizard.py"
    sys.path.insert(0, str(wiz.parent))
    runpy.run_path(str(wiz), run_name="__main__")


def run_agent_inproc():
    """Runs edge_agent/agent_v2.py in the current process (blocking)."""
    agent = AGENT_PY
    if not agent.exists():
        agent = Path(__file__).resolve().parent.parent / "edge_agent" / "agent_v2.py"
    # Make sure edge_agent siblings (actions_v2, browser_manager, etc.) resolve
    sys.path.insert(0, str(agent.parent))
    runpy.run_path(str(agent), run_name="__main__")


# ---------------------------------------------------------------------------
# Tray mode
# ---------------------------------------------------------------------------
def _acquire_singleton() -> bool:
    """Prevents multiple tray instances from spawning (belt & suspenders)."""
    try:
        if LOCK_PATH.exists():
            try:
                pid = int(LOCK_PATH.read_text().strip() or "0")
            except Exception:
                pid = 0
            if pid > 0:
                # Best-effort check on Windows
                if sys.platform.startswith("win"):
                    try:
                        import ctypes
                        PROCESS_QUERY_LIMITED = 0x1000
                        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
                        if h:
                            ctypes.windll.kernel32.CloseHandle(h)
                            return False  # another tray is running
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
        # When frozen: relaunch self with --agent (single-file bundle).
        # In dev: python edge_agent/agent_v2.py
        if getattr(sys, "frozen", False):
            return [sys.executable, "--agent"]
        return [sys.executable, str(AGENT_PY)]

    def start(self):
        if self.is_running():
            return
        if not CFG_PATH.exists():
            self._run_wizard(); return
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logf = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        logf.write(f"\n===== agent start at {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        DETACHED = 0x00000008 if sys.platform.startswith("win") else 0
        try:
            self.proc = subprocess.Popen(
                self._agent_cmd(),
                stdout=logf, stderr=subprocess.STDOUT,
                creationflags=DETACHED, cwd=str(AGENT_PY.parent) if AGENT_PY.exists() else None,
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

    def _run_wizard(self):
        # Same trick: --wizard mode re-uses self exe in frozen builds.
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable, "--wizard"])
        else:
            subprocess.Popen([sys.executable, str(WIZARD_PY)])


def tray_main():
    if not _acquire_singleton():
        print("[tray] outra instância já está rodando. Saindo.")
        return

    try:
        import pystray
        from pystray import MenuItem as Item, Menu
        from PIL import Image, ImageDraw
    except Exception as e:
        print(f"[tray] pystray/pillow indisponível: {e}")
        # Fall through: at least launch wizard/agent so user isn't stranded.
        if not CFG_PATH.exists():
            run_wizard_inproc()
        else:
            run_agent_inproc()
        return

    def _make_icon(color=(34, 211, 238)) -> "Image.Image":
        # Prefer bundled ico/png if present, else draw on the fly.
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

    if not CFG_PATH.exists():
        # First run: open wizard (non-blocking so tray still shows up).
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable, "--wizard"])
            else:
                subprocess.Popen([sys.executable, str(WIZARD_PY)])
        except Exception as e:
            print(f"[tray] erro abrindo wizard: {e}")
    else:
        mgr.start()

    def open_dashboard(icon, item):
        brain = ""
        try:
            cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            brain = cfg.get("BRAIN_URL", "")
        except Exception:
            pass
        if brain:
            webbrowser.open(brain)

    def open_logs(icon, item):
        if LOG_PATH.exists():
            if sys.platform.startswith("win"):
                os.startfile(str(LOG_PATH))  # noqa
            else:
                subprocess.Popen(["xdg-open", str(LOG_PATH)])

    def run_wizard(icon, item):
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable, "--wizard"])
        else:
            subprocess.Popen([sys.executable, str(WIZARD_PY)])

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
        Item("Iniciar", lambda i, it: mgr.start()),
        Item("Parar", lambda i, it: mgr.stop()),
        Item("Reiniciar", lambda i, it: mgr.restart()),
        Menu.SEPARATOR,
        Item("Abrir dashboard", open_dashboard),
        Item("Abrir logs", open_logs),
        Item("Reconfigurar…", run_wizard),
        Menu.SEPARATOR,
        Item("Sair", lambda i, it: _quit(i)),
    )
    icon = pystray.Icon("jarvis", _make_icon(), "J.A.R.V.I.S.", menu)
    icon.run()


def main():
    # argv dispatch — critical: prevents PyInstaller fork bomb.
    args = sys.argv[1:]
    if args:
        mode = args[0].lstrip("-").lower()
        if mode in ("wizard", "setup"):
            run_wizard_inproc(); return
        if mode in ("agent", "edge"):
            run_agent_inproc(); return
        if mode in ("help", "h"):
            print("Uso: JARVIS.exe [--wizard | --agent]"); return
    tray_main()


if __name__ == "__main__":
    main()
