# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for J.A.R.V.I.S. Windows installer.
# Produces a `dist/JARVIS/` folder with `JARVIS.exe` (tray) and everything it needs.
import os
from pathlib import Path

HERE = Path.cwd()  # installer/
ROOT = HERE.parent

agent_dir = str(ROOT / 'edge_agent')

a = Analysis(
    ['jarvis_tray.py'],
    pathex=[str(HERE), agent_dir],
    binaries=[],
    datas=[
        (str(ROOT / 'edge_agent' / 'agent_v2.py'), 'edge_agent'),
        (str(ROOT / 'edge_agent' / 'actions_v2.py'), 'edge_agent'),
        (str(ROOT / 'edge_agent' / 'browser_manager.py'), 'edge_agent'),
        (str(ROOT / 'edge_agent' / 'command_handler.py'), 'edge_agent'),
        (str(ROOT / 'edge_agent' / 'vault_client.py'), 'edge_agent'),
        (str(ROOT / 'edge_agent' / 'pair.py'), 'edge_agent'),
        (str(HERE / 'setup_wizard.py'), '.'),
        (str(HERE / 'resources' / 'jarvis.png'), 'resources'),
        (str(HERE / 'resources' / 'jarvis.ico'), 'resources'),
    ],
    hiddenimports=[
        'websockets', 'httpx', 'requests', 'pyautogui', 'psutil', 'docx',
        'playwright', 'playwright.async_api', 'PIL', 'PIL._imagingtk',
        'pystray', 'pystray._win32', 'tkinter', 'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JARVIS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # tray app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / 'resources' / 'jarvis.ico'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JARVIS',
)
