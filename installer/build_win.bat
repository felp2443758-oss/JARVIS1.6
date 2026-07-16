@echo off
REM ==============================================================
REM  JARVIS — Build Windows installer
 REM ==============================================================
setlocal enabledelayedexpansion
cd /d %~dp0

where python >nul 2>&1
if errorlevel 1 (
  echo [!] Python 3.11+ não encontrado no PATH.
  exit /b 2
)

echo [1/3] Instalando dependências de build...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

echo [2/3] Instalando dependências do agente (para embed)...
pip install -r ..\edge_agent\requirements-v2.txt

echo [3/3] Empacotando executavel...
pyinstaller jarvis.spec --clean --noconfirm

echo.
echo ==============================================================
echo  Build concluído. Executavel em: dist\JARVIS\JARVIS.exe
echo ==============================================================
endlocal
