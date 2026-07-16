@echo off
REM ==============================================================
REM  J.A.R.V.I.S. — Build ALL release artifacts (Windows)
REM  Produces:
REM    release\JARVIS-Desktop-Setup-1.0.0-x64.exe   (~90 MB, NSIS installer)
REM    release\JARVIS-Desktop-1.0.0-portable.exe    (~85 MB, single-file EXE)
REM    release\JARVIS-standalone.zip                (~60 MB, PyInstaller folder zipped)
REM    release\jarvis-autofill-extension.zip        (~30 KB, Chrome extension)
REM ==============================================================
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

set APP_VERSION=1.0.0
set ROOT=%~dp0..
set RELEASE=%ROOT%\release
set FAILED=0

echo.
echo ==============================================================
echo  J.A.R.V.I.S. build-all.bat  (versao %APP_VERSION%)
echo ==============================================================
echo.

REM ---- Prep release folder ----
if not exist "%RELEASE%" mkdir "%RELEASE%"
del /q "%RELEASE%\*.exe" 2>nul
del /q "%RELEASE%\*.zip" 2>nul

REM ---- Check Python ----
where python >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python 3.11+ nao encontrado no PATH.
  echo        Instale de https://www.python.org/downloads/ e marque "Add to PATH".
  set FAILED=1
  goto :END
)
python --version

REM ---- Install build deps ----
echo.
echo [1/6] Instalando dependencias de build...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERRO] Falha ao instalar dependencias do installer.
  set FAILED=1
  goto :END
)

echo.
echo [2/6] Instalando dependencias do edge agent (para embed no exe)...
pip install -r ..\edge_agent\requirements-v2.txt
if errorlevel 1 (
  echo [AVISO] Alguma dependencia do edge agent falhou. Continuando.
)

REM ---- Build folder version (dist\JARVIS\) ----
echo.
echo [3/6] PyInstaller: build folder version (dist\JARVIS\)...
pyinstaller jarvis.spec --clean --noconfirm
if errorlevel 1 (
  echo [ERRO] pyinstaller jarvis.spec falhou.
  set FAILED=1
  goto :ZIP_EXTENSION
)
if not exist "dist\JARVIS\JARVIS.exe" (
  echo [ERRO] dist\JARVIS\JARVIS.exe nao foi criado.
  set FAILED=1
  goto :ZIP_EXTENSION
)

REM ---- Standalone ZIP ----
echo.
echo [4/6] Compactando JARVIS-standalone.zip...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\JARVIS\*' -DestinationPath '%RELEASE%\JARVIS-standalone.zip' -Force"
if errorlevel 1 (
  echo [ERRO] Falha ao compactar standalone zip.
  set FAILED=1
)

REM ---- Portable single-file exe ----
echo.
echo [5/6] PyInstaller: build portable (single-file)...
pyinstaller jarvis-portable.spec --clean --noconfirm
if errorlevel 1 (
  echo [AVISO] pyinstaller jarvis-portable.spec falhou. Portable nao sera gerado.
) else (
  if exist "dist\JARVIS-Desktop-%APP_VERSION%-portable.exe" (
    copy /Y "dist\JARVIS-Desktop-%APP_VERSION%-portable.exe" "%RELEASE%\JARVIS-Desktop-%APP_VERSION%-portable.exe" >nul
    echo   -^> %RELEASE%\JARVIS-Desktop-%APP_VERSION%-portable.exe
  ) else (
    echo [AVISO] portable exe nao encontrado em dist\.
  )
)

REM ---- NSIS installer ----
echo.
echo [6/6] NSIS: build installer setup.exe...
set MAKENSIS=
where makensis >nul 2>&1
if not errorlevel 1 set MAKENSIS=makensis
if "!MAKENSIS!"=="" if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set MAKENSIS="%ProgramFiles(x86)%\NSIS\makensis.exe"
if "!MAKENSIS!"=="" if exist "%ProgramFiles%\NSIS\makensis.exe" set MAKENSIS="%ProgramFiles%\NSIS\makensis.exe"

if "!MAKENSIS!"=="" (
  echo [AVISO] makensis.exe nao encontrado no PATH.
  echo         Instale NSIS: https://nsis.sourceforge.io/Download
  echo         O instalador setup.exe NAO sera gerado.
) else (
  REM Cria icone .ico a partir do PNG se nao existir
  if not exist "resources\jarvis.ico" (
    echo   -^> Gerando resources\jarvis.ico a partir do PNG...
    python -c "from PIL import Image; Image.open('resources/jarvis.png').save('resources/jarvis.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>nul
  )
  !MAKENSIS! /V2 installer.nsi
  if errorlevel 1 (
    echo [ERRO] makensis falhou.
    set FAILED=1
  ) else (
    if exist "%RELEASE%\JARVIS-Desktop-Setup-%APP_VERSION%-x64.exe" (
      echo   -^> %RELEASE%\JARVIS-Desktop-Setup-%APP_VERSION%-x64.exe
    )
  )
)

:ZIP_EXTENSION
REM ---- Chrome extension ZIP (independent of pyinstaller) ----
echo.
echo [+] Compactando jarvis-autofill-extension.zip...
if exist "..\extension\manifest.json" (
  powershell -NoProfile -Command "Compress-Archive -Path '..\extension\*' -DestinationPath '%RELEASE%\jarvis-autofill-extension.zip' -Force"
  if errorlevel 1 (
    echo [ERRO] Falha ao compactar extensao.
    set FAILED=1
  ) else (
    echo   -^> %RELEASE%\jarvis-autofill-extension.zip
  )
) else (
  echo [AVISO] Pasta ..\extension nao encontrada.
)

:END
echo.
echo ==============================================================
echo  Resultado final em: %RELEASE%
echo ==============================================================
if exist "%RELEASE%" dir /b "%RELEASE%"
echo.
if "%FAILED%"=="1" (
  echo  [!] Build terminou com ERROS. Veja mensagens acima.
) else (
  echo  [OK] Build concluido com sucesso.
)
echo.
echo Pressione qualquer tecla para fechar...
pause >nul
endlocal
