"""J.A.R.V.I.S. — System tray icon (Windows).

Shows a tiny arc-reactor icon in the tray with a menu:
  * Status (online/offline)
  * Start / Stop / Restart agent
  * Open dashboard
  * Open logs folder
  * Re-run setup wizard
  * Quit

Auto-launches the setup wizard on first run if ~/.jarvis/agent.json is missing.
"""
from __future__ import annotations
import os
import sys
import json
import time
import threading
import subprocess
import webbrowser
from pathlib import Path

try:
    import pystray
    from pystray import MenuItem as Item, Menu
    from PIL import Image, ImageDraw
except Exception:
    print("[tray] pystray/pillow não instalados. Rode: pip install pystray pillow")
    raise

JARVIS_HOME = Path(os.getenv("JARVIS_HOME", str(Path.home() / ".jarvis")))
JARVIS_HOME.mkdir(parents=True, exist_ok=True)
CFG_PATH = JARVIS_HOME / "agent.json"
LOG_PATH = JARVIS_HOME / "agent.log"
STATE_PATH = JARVIS_HOME / "tray.state"

HERE = Path(__file__).resolve().parent
AGENT_PY = HERE.parent / "edge_agent" / "agent_v2.py"
WIZARD_PY = HERE / "setup_wizard.py"


class AgentManager:
    def __init__(self):
        self.proc: subprocess.Popen | None = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.is_running():
            return
        if not CFG_PATH.exists():
            self._run_wizard(); return
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logf = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        logf.write(f"\n===== agent start at {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        DETACHED = 0x00000008 if sys.platform.startswith("win") else 0
        self.proc = subprocess.Popen(
            [sys.executable, str(AGENT_PY)],
            stdout=logf, stderr=subprocess.STDOUT,
            creationflags=DETACHED, cwd=str(AGENT_PY.parent),
        )

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
        subprocess.Popen([sys.executable, str(WIZARD_PY)])


def _make_icon(color=(34, 211, 238)) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (2, 6, 13, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), outline=color, width=3)
    d.ellipse((18, 18, 46, 46), outline=color, width=2)
    d.ellipse((28, 28, 36, 36), fill=color)
    return img


def main():
    mgr = AgentManager()

    if not CFG_PATH.exists():
        # First run: open the wizard immediately.
        try:
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
        subprocess.Popen([sys.executable, str(WIZARD_PY)])

    def status_label(item=None):
        return f"Agent: {'online' if mgr.is_running() else 'offline'}"

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
        Item("Sair", lambda i, it: (mgr.stop(), icon.stop())),
    )
    icon = pystray.Icon("jarvis", _make_icon(), "J.A.R.V.I.S.", menu)
    icon.run()


if __name__ == "__main__":
    main()
