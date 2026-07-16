// J.A.R.V.I.S. Autofill — background service worker
// Handles config storage, vault fetches and context-menu action.

const DEFAULT_BRAIN = "https://jarvis-brain-29.preview.emergentagent.com";

async function getConfig() {
  const { brainUrl, token } = await chrome.storage.local.get(["brainUrl", "token"]);
  return { brainUrl: brainUrl || DEFAULT_BRAIN, token: token || "" };
}

async function fetchCredential(site) {
  const { brainUrl, token } = await getConfig();
  if (!token) {
    return { ok: false, error: "Token não configurado. Abra o popup da extensão." };
  }
  try {
    const res = await fetch(`${brainUrl.replace(/\/$/, "")}/api/vault/get/${encodeURIComponent(site)}`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

async function listSites() {
  const { brainUrl, token } = await getConfig();
  if (!token) return { ok: false, error: "Token não configurado." };
  try {
    const res = await fetch(`${brainUrl.replace(/\/$/, "")}/api/vault/list`, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const data = await res.json();
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

function hostnameToSite(host) {
  if (!host) return "";
  const parts = host.replace(/^www\./, "").split(".");
  if (parts.length <= 1) return parts[0];
  return parts.slice(0, -1).join(".");
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "jarvis:getCredential") {
    const site = msg.site || hostnameToSite(new URL(sender.tab?.url || "http://x").hostname);
    fetchCredential(site).then(sendResponse);
    return true;
  }
  if (msg?.type === "jarvis:listSites") {
    listSites().then(sendResponse);
    return true;
  }
  if (msg?.type === "jarvis:autofillHere") {
    (async () => {
      const tab = await chrome.tabs.query({ active: true, currentWindow: true }).then(t => t[0]);
      if (!tab) { sendResponse({ ok: false, error: "aba inválida" }); return; }
      const host = new URL(tab.url).hostname;
      const site = msg.site || hostnameToSite(host);
      const cred = await fetchCredential(site);
      if (!cred.ok) { sendResponse(cred); return; }
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: (username, password) => window.__jarvisFill && window.__jarvisFill(username, password),
          args: [cred.data.username || cred.data.login || "", cred.data.password || ""]
        });
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  }
});

// Context menu: right-click → "Preencher com JARVIS"
chrome.runtime.onInstalled.addListener(() => {
  try {
    chrome.contextMenus.create({
      id: "jarvis-autofill",
      title: "Preencher com J.A.R.V.I.S.",
      contexts: ["page", "editable"]
    });
  } catch (_) { /* already exists */ }
});

chrome.contextMenus?.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "jarvis-autofill" || !tab) return;
  const site = hostnameToSite(new URL(tab.url).hostname);
  const cred = await fetchCredential(site);
  if (!cred.ok) {
    chrome.notifications?.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "J.A.R.V.I.S. Autofill",
      message: cred.error || "Falha ao buscar credencial."
    });
    return;
  }
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (u, p) => window.__jarvisFill && window.__jarvisFill(u, p),
    args: [cred.data.username || cred.data.login || "", cred.data.password || ""]
  }).catch(() => {});
});
