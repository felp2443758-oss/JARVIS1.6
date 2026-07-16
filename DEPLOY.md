# J.A.R.V.I.S. Cloud Brain — Railway deployment guide

This directory is set up to deploy the backend to **Railway.app** (or any
other Docker-based PaaS: Render, Fly.io, DigitalOcean App Platform, Google
Cloud Run, AWS App Runner).

## Arquitetura recomendada

```
 Railway project
  ├── backend service    (este repo, este Dockerfile) → https://SEUAPP.up.railway.app
  └── MongoDB           (Railway Add-on "MongoDB")     → mongodb://...

 Vercel (ou Netlify)
  └── frontend           (React CRA)                    → https://SEUAPP.vercel.app
```

Misturar Python + Node no mesmo serviço Railway confunde o Nixpacks e falha o
build — por isso o **Dockerfile deste repo builda SO o backend**, e o
`.dockerignore` exclui `frontend/`, `installer/`, `edge_agent/` etc.

## Passo-a-passo Railway

### 1. Novo projeto
1. Acesse https://railway.app/new → **Deploy from GitHub repo**
2. Selecione o repositório deste projeto
3. Railway detecta o `railway.json` e o `Dockerfile` na raiz

### 2. Adicionar MongoDB
1. No painel do projeto → **+ New → Database → Add MongoDB**
2. Isso cria um serviço `MongoDB` e expor a variável `MONGO_URL` no scope do projeto

### 3. Variáveis de ambiente do backend
Em **Backend service → Variables**, cole (adaptando):

```env
# Mongo — pode usar a var Railway (recomendado) OU MongoDB Atlas
MONGO_URL=${{MongoDB.MONGO_URL}}
DB_NAME=jarvis_database
CORS_ORIGINS=*

EMERGENT_LLM_KEY=sk-emergent-b486f556898Ed86D76

GOOGLE_API_KEY=AQ.Ab8RN6LPcKyi2nlJotbdlNNIE9F0scD2VlAMhBbrxf47FD9-GQ
GOOGLE_CLIENT_ID=154505935171-38mouh7dihbbcvpvr4qv216vg4d8t8ri.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
# ATENCAO: trocar pela URL publica do Railway apos primeiro deploy:
GOOGLE_REDIRECT_URI=https://SEUAPP.up.railway.app/api/auth/google/callback

TAVILY_API_KEY=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
FAL_KEY=df4892e1-bf58-4838-8adb-f690ccf1bcbf:cf840210b40a25d579f1dc575aa6928f

DEFAULT_CITY=Belo Horizonte, MG
JARVIS_SERVER_SECRET=3ad09397b42ac09855f678405e4b3af88e665b523c437041d51bff6b7700a4da
```

> `${{MongoDB.MONGO_URL}}` é referência dinâmica do Railway — pega a URL do
> serviço MongoDB automaticamente. Se preferir MongoDB Atlas (Free Tier), cole
> a connection string dele em `MONGO_URL` normalmente.

### 4. Gerar domínio público
1. **Backend service → Settings → Networking → Generate Domain**
2. Copie a URL gerada (ex: `https://jarvis-brain.up.railway.app`)
3. Volte em **Variables** e atualize `GOOGLE_REDIRECT_URI` com essa URL

### 5. Google Cloud Console
Em https://console.cloud.google.com/apis/credentials → seu OAuth Client:
- **Authorized JavaScript origins**: `https://jarvis-brain.up.railway.app`
- **Authorized redirect URIs**: `https://jarvis-brain.up.railway.app/api/auth/google/callback`

### 6. Deploy do frontend (Vercel)
1. https://vercel.com/new → importar o mesmo repositório
2. **Root Directory**: `frontend`
3. **Framework Preset**: Create React App
4. **Environment Variables**: `REACT_APP_BACKEND_URL=https://jarvis-brain.up.railway.app`
5. Deploy → pega a URL (ex: `https://jarvis.vercel.app`)

Adicione também no CORS do backend (Railway variables):
```
CORS_ORIGINS=https://jarvis.vercel.app
```
E em **Google Cloud Console → Authorized JavaScript origins**, adicione
também `https://jarvis.vercel.app`.

### 7. Rebuild do JARVIS Desktop com nova URL

Atualize essas duas linhas com a URL do Railway ou (melhor) o domínio Vercel:

`installer/desktop_app.py`:
```python
DEFAULT_BRAIN = "https://jarvis-brain.up.railway.app"
```

`extension/background.js`:
```javascript
const DEFAULT_BRAIN = "https://jarvis-brain.up.railway.app";
```

Depois:
```powershell
cd installer
build-all.bat
```

## Debug do build Railway

### "Failed to build an image" no primeiro deploy

Causas comuns:
1. **Nixpacks tentou builder Node+Python juntos** → já resolvido com o Dockerfile
2. **emergentintegrations não encontrado** → já resolvido com `--extra-index-url` no Dockerfile
3. **Falta memoria no builder** → Railway free tier tem 512MB, requirements.txt pesado. Se acontecer, remova deps desnecessárias do requirements.txt.
4. **`fal_client` ou `google-generativeai` quebrado** → vide **Build Logs** no Railway.

### Como ver o log real do build no Railway
No painel → **Deployments → clique no failed → View Build Logs**. 
Cole aqui o log completo e eu ajusto o Dockerfile pontualmente.

## Alternativa: manter deploy no Emergent

Se preferir não usar o Railway, clique no botão **Publish/Deploy** do Emergent
que promove seu preview atual para uma URL permanente `*.emergent.host`. Mais
simples, mas custa o plano do Emergent.
