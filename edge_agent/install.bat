@echo off
REM ============================================================
REM  J.A.R.V.I.S. Edge Agent — install helper (Windows)
REM ============================================================
setlocal enabledelayedexpansion

cd /d %~dp0

where python >nul 2>&1
if errorlevel 1 (
  echo [!] Python 3.11+ não encontrado no PATH. Instale antes de continuar.
  exit /b 2
)

echo [1/4] Criando ambiente virtual...
python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/4] Instalando dependências...
python -m pip install --upgrade pip
pip install -r requirements-v2.txt

echo [3/4] Instalando navegador Chromium (Playwright)...
python -m playwright install chromium

echo [4/4] Pronto! Para parear com o cérebro rode:
echo     python pair.py --brain https://SEU-JARVIS.example.com --agent-name Home-PC
echo.
echo Depois de parear:
echo     python agent_v2.py

endlocal
