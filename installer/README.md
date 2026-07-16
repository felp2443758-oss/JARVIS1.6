# J.A.R.V.I.S. Desktop — Installer (Windows)

Empacota o app desktop completo: janela de login com Google, dashboard
embutido em WebView2 e Edge Agent rodando em background — **sem parear
manualmente, sem copiar/colar tokens, sem navegador externo**.

## Novo fluxo de login (OAuth 2.0 Loopback — RFC 8252)

```
     JARVIS.exe                              backend (nuvem)                Google
        |                                         |                            |
    [botao: Entrar com Google]                    |                            |
    sobe HTTP server em 127.0.0.1:PORT            |                            |
    abre browser em                               |                            |
      /api/auth/google/desktop                    |                            |
      ?redirect=http://127.0.0.1:PORT/callback -->|                            |
        |                                    guarda redirect                   |
        |                                    (state)                           |
        |                                         |--- redirect Google OAuth ->|
        |                                         |                     usuario loga
        |                                         |<--- callback com code -----|
        |                                    troca code por token              |
        |                                    cria/atualiza user                |
        |                                    gera session_jwt + agent_token    |
        |<--- redirect http://127.0.0.1:PORT/callback?token=&agent_token=&...  |
    captura tokens                                |                            |
    grava ~/.jarvis/agent.json                    |                            |
    abre webview embutido com dashboard           |                            |
    spawna edge_agent v2 em background            |                            |
```

**Vantagens sobre o fluxo antigo (pair.py + copy/paste URL):**
- Nada de tokens visiveis na URL do navegador do usuario
- Nada de copiar/colar
- Google Cloud Console **nao** precisa aceitar `http://127.0.0.1:*` como
  redirect — o Google so redireciona para a URL do backend (que ja esta
  registrada). O loopback e um segundo redirect feito pelo backend.
- Dashboard abre em janela nativa (WebView2), nao em aba do browser

## Artefatos produzidos por `build-all.bat`

```
release\
├── JARVIS-Desktop-Setup-1.0.0-x64.exe    (~90 MB, instalador NSIS)
├── JARVIS-Desktop-1.0.0-portable.exe     (~85 MB, EXE unico portable)
├── JARVIS-standalone.zip                 (~60 MB, pasta PyInstaller zipada)
└── jarvis-autofill-extension.zip         (~30 KB, extensao Chrome MV3)
```

## Pre-requisitos (na maquina de build — Windows 10/11 x64)

- **Python 3.11+** no PATH
- **NSIS 3.x** — https://nsis.sourceforge.io/Download (opcional; sem NSIS, os
  outros 3 artefatos ainda sao gerados)
- **PowerShell** (nativo do Windows)
- **Edge WebView2 Runtime** (ja vem no Windows 10 21H2+ e Windows 11; se o
  usuario tiver Windows 10 antigo, o pywebview cai pro fallback IE — nao ideal)

## Build one-shot

```powershell
cd installer
build-all.bat
```

## Modos do EXE (argv dispatch — evita fork bomb do PyInstaller)

```
JARVIS.exe                 -> app completo (login + dashboard + tray + agent)
JARVIS.exe --agent         -> so o edge agent (usado internamente pelo tray)
JARVIS.exe --dashboard     -> reabre so a janela do dashboard
JARVIS.exe --tray-only     -> so o icone do tray
```

## Fluxo do usuario final

1. Baixa o `Setup-x64.exe` ou o portable, instala/roda.
2. Janela cyan "J.A.R.V.I.S." aparece com botao **Entrar com Google**.
3. Clica -> navegador padrao abre no Google, usuario loga.
4. Navegador mostra "AUTENTICADO — pode fechar", fecha sozinho em ~1.5s.
5. Janela do JARVIS carrega o dashboard embutido (WebView2).
6. Icone na bandeja fica ativo com menu:
   - Abrir dashboard
   - Iniciar/Parar/Reiniciar agente
   - Trocar de conta / Reautenticar
   - Abrir logs
   - Sair

## O que **voce (dono)** precisa configurar no Google Cloud Console

Apenas uma vez (Console -> APIs & Services -> Credentials -> seu OAuth 2.0 Client ID):

- **Authorized JavaScript origins**: `https://cloud-mind-2.preview.emergentagent.com`
- **Authorized redirect URIs**: `https://cloud-mind-2.preview.emergentagent.com/api/auth/google/callback`

Nao precisa cadastrar `http://127.0.0.1:*` — o loopback e feito pelo backend
apos o Google devolver o code.

## Debug

- Logs do agente: `%USERPROFILE%\.jarvis\agent.log`
- Config gravada apos login: `%USERPROFILE%\.jarvis\agent.json`
- Perfil persistente do Chromium (Playwright): `%USERPROFILE%\.jarvis\chrome_profile`

## Troubleshooting

| Sintoma | Causa provavel | Fix |
|---|---|---|
| Janela do JARVIS abre e fecha na hora | Antivirus bloqueou / DLL faltou | Add exclusao no Defender pra pasta de instalacao, veja `%USERPROFILE%\.jarvis\agent.log` |
| Dashboard aparece em branco | WebView2 Runtime nao instalado | Instalar Evergreen: https://developer.microsoft.com/en-us/microsoft-edge/webview2/ |
| Login abre navegador mas nao volta | Firewall bloqueou 127.0.0.1 | Liberar loopback no Firewall Windows |
| Google devolve "redirect_uri_mismatch" | Cloud Console fora de sincronia | Adicionar as URLs acima em Authorized redirect URIs |
| `messagebox` / outro ImportError | PyInstaller pulou um submodulo | Adicionar em `hiddenimports` no `jarvis.spec` |
| Setup falha "erro para gravacao" | Processos JARVIS.exe travados | O novo `installer.nsi` mata processos antes; se ainda persistir, reboot |

## Arquitetura de dependencias

```
JARVIS.exe (jarvis_tray.py — argv dispatch)
 ├─ default -> full_app()
 |    ├─ tray_main() em thread (pystray)
 |    └─ run_desktop_inproc() -> desktop_app.py
 |         ├─ show_login_screen()  (tkinter, se sem agent.json)
 |         ├─ do_login_flow()      (loopback HTTP + webbrowser.open)
 |         └─ open_dashboard_window()  (pywebview + Edge WebView2)
 ├─ --agent -> run_agent_inproc() -> edge_agent/agent_v2.py (WS loop)
 ├─ --dashboard -> so a janela do webview
 └─ --tray-only -> so o icone
```

## Testes manuais recomendados

1. Instalar em Windows limpo, sem Python -> deve rodar (tudo bundlado).
2. Clicar Entrar com Google -> deve abrir Google login e retornar sozinho.
3. Fechar dashboard -> icone do tray continua vivo.
4. Menu do tray "Abrir dashboard" -> reabre janela.
5. Menu "Trocar de conta" -> apaga `agent.json` e reabre login.
6. Menu "Sair" -> mata agent + fecha tudo.
