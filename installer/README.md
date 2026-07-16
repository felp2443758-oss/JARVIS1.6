# J.A.R.V.I.S. — Installer (Windows)

Empacota o Edge Agent + Setup Wizard + Ícone de bandeja e gera todos os
artefatos de release do J.A.R.V.I.S. Desktop.

## Artefatos produzidos por `build-all.bat`

```
release\
├── JARVIS-Desktop-Setup-1.0.0-x64.exe    (~90 MB, instalador NSIS)
├── JARVIS-Desktop-1.0.0-portable.exe     (~85 MB, EXE único portable)
├── JARVIS-standalone.zip                 (~60 MB, pasta PyInstaller zipada)
└── jarvis-autofill-extension.zip         (~30 KB, extensão Chrome MV3)
```

## Pré-requisitos (na máquina de build — Windows 10/11 x64)

- **Python 3.11+** no PATH (marque "Add Python to PATH" no instalador)
- **NSIS 3.x** — https://nsis.sourceforge.io/Download
  - Necessário para gerar o `Setup-x64.exe`. Se ausente, os outros 3 artefatos ainda são gerados; o script apenas avisa.
- **PowerShell** (nativo do Windows) — usado para `Compress-Archive`

## Build completo — one command

```powershell
cd installer
build-all.bat
```

O script:
1. Instala dependências (`requirements.txt` + `edge_agent\requirements-v2.txt`)
2. Roda `pyinstaller jarvis.spec` → gera `dist\JARVIS\JARVIS.exe`
3. Compacta `dist\JARVIS\*` → `release\JARVIS-standalone.zip`
4. Roda `pyinstaller jarvis-portable.spec` → gera EXE portable único
5. Roda `makensis installer.nsi` → gera o setup.exe assinado no menu Iniciar
6. Compacta `extension\*` → `release\jarvis-autofill-extension.zip`

O `build-all.bat` **nunca fecha sozinho** em caso de erro: mostra um resumo final
e pede `pause` para você inspecionar. Cada etapa é isolada — se o NSIS falhar,
o ZIP da extensão ainda é gerado.

## Build parcial

- Só a pasta PyInstaller: `build_win.bat` (script legado, mantido)
- Só a extensão: `powershell Compress-Archive -Path ..\extension\* -DestinationPath ..\release\jarvis-autofill-extension.zip -Force`

## Distribuição

- **Setup-x64.exe** — usuário final típico. Instala em `Program Files`, cria atalhos, autostart opcional.
- **portable.exe** — usuário que não quer instalar (roda de pendrive).
- **standalone.zip** — power user; extrai e roda `JARVIS.exe` direto.
- **autofill-extension.zip** — publicar na Chrome Web Store ou instalar em modo dev.

## Fluxo do usuário final

1. Baixa o `Setup-x64.exe` do GitHub Releases.
2. Duplo-clique → assistente NSIS → **Instalar**.
3. Ao final, marca "Iniciar J.A.R.V.I.S. agora" → tray icon aparece.
4. Se for a 1ª vez, o **Setup Wizard** abre pedindo:
   - URL do backend
   - Login com Google → cola o `?token=...`
   - Nome do PC
5. Ícone fica ativo na bandeja — pronto para receber comandos do dashboard.

## Debug

- Logs do agente: `%USERPROFILE%\.jarvis\agent.log`
- Config: `%USERPROFILE%\.jarvis\agent.json`
- Perfil persistente do Chromium: `%USERPROFILE%\.jarvis\chrome_profile`

## Arquitetura do executável

```
JARVIS.exe (tray)
 ├─ abre setup_wizard.py se não achar ~/.jarvis/agent.json
 └─ spawna agent_v2.py em background (logs em agent.log)
         ├─ conecta WSS ao cloud brain (JWT agent_token)
         └─ executa comandos: actions_v2 + browser_manager (Playwright)
```

## Troubleshooting build-all.bat

| Sintoma | Causa | Solução |
|---|---|---|
| Janela fecha imediatamente | (não deveria mais — tem `pause` no final) | Rode `cmd /k build-all.bat` para forçar shell persistente |
| `Python nao encontrado` | Python fora do PATH | Reinstalar Python marcando "Add to PATH" |
| `pyinstaller` falha em `websockets` | dep não instalada | `pip install -r ..\edge_agent\requirements-v2.txt` |
| `makensis` não encontrado | NSIS não instalado | Instalar NSIS 3.x — script continua e gera os outros 3 artefatos |
| Falta `resources\jarvis.ico` | Pillow não conseguiu gerar | Já vem pré-gerado no repositório |
