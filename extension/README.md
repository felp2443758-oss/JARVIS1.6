# J.A.R.V.I.S. Autofill — Chrome Extension

Extensão Chrome Manifest V3 que preenche credenciais do cofre AES-GCM do
J.A.R.V.I.S. em qualquer página de login, sem precisar do Playwright.

## Instalação (dev)
1. Abra `chrome://extensions/`.
2. Ative o modo desenvolvedor.
3. Clique **Carregar sem compactação** e escolha esta pasta (`/app/extension`).

## Configuração
1. Clique no ícone da extensão.
2. Cole a URL pública do backend (mesma que o Dashboard usa).
3. Cole seu JWT (Dashboard → Operador Remoto → "Copiar token").
4. Salvar.

## Uso
- Vá para a página de login (ex.: `spotify.com/login`).
- Clique no ícone da extensão → **Preencher esta página**.
- Ou clique com o botão direito na página → **Preencher com J.A.R.V.I.S.**

O nome do site é inferido do hostname (`www.spotify.com` → `spotify`). Se o cofre
tiver essa entrada, ela é preenchida.

## Empacotamento
O `installer/build-all.bat` gera automaticamente `jarvis-autofill-extension.zip`
com o conteúdo desta pasta pronto para publicar na Chrome Web Store.
