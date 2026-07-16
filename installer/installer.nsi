; J.A.R.V.I.S. Desktop — NSIS installer script (robust)
; Builds JARVIS-Desktop-Setup-1.0.0-x64.exe from dist\JARVIS\ (PyInstaller output).
; Requires: makensis (NSIS 3.x) in PATH.

!define APP_NAME       "J.A.R.V.I.S. Desktop"
!define APP_VERSION    "1.0.0"
!define APP_PUBLISHER  "J.A.R.V.I.S. Team"
!define APP_EXE        "JARVIS.exe"
!define APP_ID         "JARVIS.Desktop"

!define OUT_DIR        "..\release"
!define SOURCE_DIR     "dist\JARVIS"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "${OUT_DIR}\JARVIS-Desktop-Setup-${APP_VERSION}-x64.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${APP_ID}" "InstallDir"
RequestExecutionLevel admin
Unicode true
SetCompressor /SOLID lzma

; --- Robust file writing ---------------------------------------------------
; try = if a file is locked, mark it for replace-on-reboot instead of aborting
SetOverwrite try
AllowSkipFiles off

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON       "resources\jarvis.ico"
!define MUI_UNICON     "resources\jarvis.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Iniciar J.A.R.V.I.S. agora"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "English"

; ===========================================================================
;  .onInit — runs BEFORE the wizard is shown.
;  - Kills any running JARVIS.exe (leftover from a previous install / fork bomb)
;  - Detects existing installation and runs the old uninstaller silently
; ===========================================================================
Function .onInit
  ; 1. Kill leftover processes so files aren't locked
  DetailPrint "Verificando processos J.A.R.V.I.S. em execucao..."
  nsExec::Exec 'taskkill /F /IM JARVIS.exe /T'
  Pop $0
  nsExec::Exec 'taskkill /F /IM "JARVIS-Desktop-1.0.0-portable.exe" /T'
  Pop $0
  Sleep 800

  ; 2. Detect previous install via registry
  ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString"
  ${If} $0 != ""
    MessageBox MB_OKCANCEL|MB_ICONQUESTION \
      "Uma versao anterior do ${APP_NAME} foi detectada.$\r$\n$\r$\nDeseja remove-la antes de continuar?$\r$\n(Recomendado — evita conflitos de arquivo.)" \
      IDOK do_uninstall IDCANCEL skip_uninstall
    do_uninstall:
      DetailPrint "Removendo instalacao anterior..."
      ExecWait '$0 /S _?=$INSTDIR' $1
      ; Second kill in case uninstaller started the app
      nsExec::Exec 'taskkill /F /IM JARVIS.exe /T'
      Pop $0
      Sleep 500
      Goto init_done
    skip_uninstall:
  ${EndIf}
  init_done:
FunctionEnd

Function un.onInit
  ; Same treatment on uninstall
  nsExec::Exec 'taskkill /F /IM JARVIS.exe /T'
  Pop $0
  nsExec::Exec 'taskkill /F /IM "JARVIS-Desktop-1.0.0-portable.exe" /T'
  Pop $0
  Sleep 800
FunctionEnd

; ===========================================================================
;  Sections
; ===========================================================================
Section "J.A.R.V.I.S. (obrigatorio)" SEC_MAIN
  SectionIn RO

  ; One last kill right before writing files
  nsExec::Exec 'taskkill /F /IM JARVIS.exe /T'
  Pop $0
  Sleep 300

  SetOutPath "$INSTDIR"

  ; Clear the target if it exists (best-effort; ignore errors)
  ClearErrors
  RMDir /r "$INSTDIR\_internal"
  ClearErrors

  ; Write the PyInstaller output. `SetOverwrite try` (declared above) means
  ; locked files are queued for replace on next reboot instead of failing.
  File /r "${SOURCE_DIR}\*.*"

  ; Registry entries
  WriteRegStr HKLM "Software\${APP_ID}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\${APP_ID}" "Version" "${APP_VERSION}"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "DisplayIcon" "$\"$INSTDIR\${APP_EXE}$\""
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" \
    "NoRepair" 1

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Atalho no Menu Iniciar" SEC_STARTMENU
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Desinstalar.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Atalho na Area de Trabalho" SEC_DESKTOP
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Iniciar com o Windows" SEC_AUTOSTART
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_ID}" \
    "$\"$INSTDIR\${APP_EXE}$\""
SectionEnd

Section "Uninstall"
  ; Kill again just to be sure
  nsExec::Exec 'taskkill /F /IM JARVIS.exe /T'
  Pop $0
  Sleep 300

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Desinstalar.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_ID}"
  DeleteRegKey HKLM "Software\${APP_ID}"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

  RMDir /r "$INSTDIR"
SectionEnd
