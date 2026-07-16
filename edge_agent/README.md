# J.A.R.V.I.S. Edge Agent v2

O Edge Agent é o "corpo" do JARVIS: um pequeno programa Python que roda no
computador do usuário e recebe comandos do cérebro cloud via WebSocket para:

- Abrir apps (Spotify, Chrome, VSCode, Word…)
- Abrir URLs
- Controlar navegador via Playwright (login automático usando o cofre)
- Digitar / pressionar teclas / mouse
- Tirar screenshot
- Ler/escrever arquivos, editar documentos `.docx`
- Executar comandos shell (desabilitado por padrão)
- Ler informações do sistema (CPU/RAM/bateria)

## Requisitos
- Windows 10/11 (foco desta versão)
- Python 3.11+
- Chrome/Chromium (para Playwright, instalado automaticamente pelo pip)

## Instalação
```bash
cd edge_agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-v2.txt
python -m playwright install chromium
```

## Pareamento (uma vez por PC)
```bash
python pair.py --brain https://SEU-JARVIS.example.com --agent-name Home-PC
```
1. Abre o login do JARVIS no navegador (Google OAuth).
2. Após logar, o SPA guarda `?token=...` na URL.
3. Cole esse `token` no prompt.
4. O script grava `~/.jarvis/agent.json` com um agent_token de 365 dias.

## Rodar o agente
```bash
python agent_v2.py
```
O cabo abre em `wss://.../api/ws/agent/{user_id}:Home-PC?token=<agent_token>`.
Agora o dashboard do JARVIS vê seu PC como online e você pode disparar comandos.

## Segurança
- `JARVIS_ALLOW_SHELL=1` — habilita `shell_exec` (desligado por padrão)
- `JARVIS_ALLOW_FS=1` — habilita leitura/escrita de arquivos (ligado por padrão)
- Cofre AES-GCM por usuário (chave derivada de server_secret + user_id)
- Persistent Chromium profile em `~/.jarvis/chrome_profile` — cookies e sessões
  ficam salvas para reuso (Spotify/Google/YouTube só logam uma vez)

## Comandos disponíveis
Consulte `GET /api/agent/commands` no backend para lista completa.
Exemplo via HTTP:
```bash
curl -X POST https://SEU-JARVIS.example.com/api/agent/command \
     -H 'Authorization: Bearer <session_token>' \
     -H 'Content-Type: application/json' \
     -d '{"command":"open_app","args":{"name":"spotify"}}'
```
