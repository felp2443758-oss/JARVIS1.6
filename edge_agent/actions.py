"""Local OS-level actions: open app, volume control, typing, web search."""
from __future__ import annotations
import os
import subprocess
import sys
import webbrowser
from typing import Dict, Callable

try:
    import pyautogui  # type: ignore
    PYAUTOGUI = True
except Exception:
    PYAUTOGUI = False

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def open_app(name: str) -> str:
    """Best-effort cross-platform app launcher."""
    name = name.lower().strip()
    aliases = {
        "spotify": {"win": "spotify", "mac": "Spotify", "linux": "spotify"},
        "chrome": {"win": "chrome", "mac": "Google Chrome", "linux": "google-chrome"},
        "firefox": {"win": "firefox", "mac": "Firefox", "linux": "firefox"},
        "code": {"win": "code", "mac": "Visual Studio Code", "linux": "code"},
        "vscode": {"win": "code", "mac": "Visual Studio Code", "linux": "code"},
        "calculator": {"win": "calc", "mac": "Calculator", "linux": "gnome-calculator"},
        "notepad": {"win": "notepad", "mac": "TextEdit", "linux": "gedit"},
    }
    target = aliases.get(name, {"win": name, "mac": name, "linux": name})
    try:
        if IS_WIN:
            subprocess.Popen(["cmd", "/c", "start", "", target["win"]], shell=False)
        elif IS_MAC:
            subprocess.Popen(["open", "-a", target["mac"]])
        else:
            subprocess.Popen([target["linux"]])
        return f"Abrindo {name}"
    except Exception as e:
        return f"Falha ao abrir {name}: {e}"


def web_search(query: str) -> str:
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    return f"Pesquisando '{query}'"


def volume_up():
    if not PYAUTOGUI:
        return "PyAutoGUI indisponível"
    pyautogui.press("volumeup")
    return "Volume +"


def volume_down():
    if not PYAUTOGUI:
        return "PyAutoGUI indisponível"
    pyautogui.press("volumedown")
    return "Volume -"


def volume_mute():
    if not PYAUTOGUI:
        return "PyAutoGUI indisponível"
    pyautogui.press("volumemute")
    return "Mudo alternado"


ACTIONS: Dict[str, Callable[..., str]] = {
    "open_app": open_app,
    "web_search": web_search,
    "volume_up": volume_up,
    "volume_down": volume_down,
    "volume_mute": volume_mute,
}


def dispatch(action: str, **kwargs) -> str:
    fn = ACTIONS.get(action)
    if not fn:
        return f"Ação desconhecida: {action}"
    return fn(**kwargs)
