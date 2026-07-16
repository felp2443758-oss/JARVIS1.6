# J.A.R.V.I.S. — PRD (v2, multi-user + operator)

## Visão
Assistente pessoal estilo Tony Stark: cérebro cloud (FastAPI + LLM) + "corpo"
na máquina do usuário (Edge Agent Python) que abre apps, controla navegador,
edita documentos e conecta em serviços web — tudo multi-tenant.

## Arquitetura
```
 [Browser SPA]  ─── HTTPS + JWT ───▶  [Cloud Brain / FastAPI]
     │                                    │
     │     (Google OAuth login)            │  ─ MongoDB (users, sessions, vault, google_tokens)
     │                                    │  ─ Emergent LLM (Gemini/GPT/Claude)
     │                                    │  ─ Tavily / Fal.ai (opcional)
     │                                    │
     │              wss + agent_token      │
     ▼                                    ▼
 [Edge Agent (Windows)] ◄─ WebSocket ─▶ [Command Dispatcher]
  ├─ actions_v2  (open_app, mouse, keys, files, volume, screenshot)
  ├─ browser_manager  (Playwright persistente por usuário)
  └─ vault_client  (busca senhas do cofre AES-GCM sob demanda)
```

## Componentes entregues (Fase 1)
### Backend
- `auth_service.py` — Google OAuth multi-user, JWT session (30d), agent_token (365d), derivação de chave AES por usuário.
- `vault_service.py` — cofre AES-GCM (`db.vault`), CRUD por usuário, decrypt via session ou agent_token.
- `agent_commands.py` — dispatcher async (request_id -> Future) para correlar comandos WS.
- `server.py` — rotas novas: `/auth/me`, `/auth/logout`, `/auth/agent/pair`, `/vault/*`, `/agent/command`, `/agent/list`, `/agent/commands`. WS agora aceita `?token=<agent_token>` e resolve `command_result`.

### Edge Agent (Windows-first)
- `actions_v2.py` — open_app, close_app, list_apps, open_url, type_text, press_keys, hotkey, screenshot, mouse_click/move, volume, file_read/write, doc_edit, shell_exec, system_info.
- `browser_manager.py` — Playwright persistente (user_data_dir em `~/.jarvis/chrome_profile`), ações de browser + login genérico + spotify_play.
- `vault_client.py` — GET `/api/vault/get/{site}` com `X-Agent-Token`.
- `command_handler.py` — despacha 20+ comandos, roda ações síncronas em thread.
- `pair.py` — wizard de pareamento (abre login → grava `~/.jarvis/agent.json`).
- `agent_v2.py` — loop WS autenticado + command_result.
- `requirements-v2.txt` + `README.md`.

### Frontend
- `lib/auth.js` — storage do JWT, interceptor axios, helpers de vault + agent commands.
- `AuthGate.js` — tela de login HUD (Google button).
- `CredentialVault.js` — UI CRUD do cofre (add/list/delete).
- `OperatorPanel.js` — painel para disparar comandos ao agente (quick actions + JSON args + resultado).
- `App.js` — gate de auth.
- `Dashboard.js` — chip do usuário no header, botões "Operador Remoto" + "Cofre", logout.

## Comandos suportados (agent v2)
`open_app`, `close_app`, `list_apps`, `open_url`, `type_text`, `press_keys`, `hotkey`, `screenshot`, `mouse_click`, `mouse_move`, `volume`, `browser_open`, `browser_navigate`, `browser_evaluate`, `browser_screenshot`, `browser_search`, `browser_login`, `spotify_play`, `file_read`, `file_write`, `doc_edit`, `shell_exec` (opt-in), `system_info`.

## Fluxo do usuário
1. Acessa a URL do JARVIS → tela de login → clica "Entrar com Google".
2. Google OAuth → backend cria/atualiza user + emite JWT → redirect com `?token=`.
3. SPA guarda em localStorage. Dashboard mostra o rosto + nome no canto superior.
4. Menu "Cofre" → usuário adiciona site (Spotify, Instagram, etc.) com login/senha.
5. Menu "Operador Remoto" → gera agent_token → usuário salva em `~/.jarvis/agent.json` no PC dele.
6. `python agent_v2.py` conecta o WS → dashboard vê o agente online.
7. Usuário clica "Abrir Spotify" → backend envia comando → agente abre o app.

## Fase 2 (próxima)
- Empacotar o projeto inteiro (backend + frontend + edge agent) em um único instalador Windows (`.exe`) via PyInstaller/Electron.
- Assistente gráfico de pareamento (sem `python pair.py`).
- Icônezinho na system tray.

## Fase 3
- Electron/Tauri shell unificado.
- Extensão Chrome com Native Messaging (preencher senhas em qualquer site sem Playwright).
