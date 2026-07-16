const $ = (id) => document.getElementById(id);
const statusEl = $("status");

function setStatus(msg, kind = "") {
  statusEl.className = "status " + kind;
  statusEl.textContent = msg;
}

async function load() {
  const { brainUrl, token } = await chrome.storage.local.get(["brainUrl", "token"]);
  $("brainUrl").value = brainUrl || "";
  $("token").value = token || "";
}

$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({
    brainUrl: $("brainUrl").value.trim(),
    token: $("token").value.trim()
  });
  setStatus("Configuração salva.", "ok");
});

$("fill").addEventListener("click", async () => {
  setStatus("Buscando credencial...");
  const res = await chrome.runtime.sendMessage({ type: "jarvis:autofillHere" });
  if (res?.ok) setStatus("Preenchido com sucesso.", "ok");
  else setStatus(res?.error || "Falha ao preencher.", "err");
});

$("list").addEventListener("click", async () => {
  setStatus("Listando sites do cofre...");
  const res = await chrome.runtime.sendMessage({ type: "jarvis:listSites" });
  const ul = $("sites");
  ul.innerHTML = "";
  if (!res?.ok) { setStatus(res?.error || "Falha", "err"); ul.hidden = true; return; }
  const items = Array.isArray(res.data) ? res.data : (res.data?.sites || []);
  if (items.length === 0) { setStatus("Cofre vazio.", ""); ul.hidden = true; return; }
  for (const it of items) {
    const li = document.createElement("li");
    const site = typeof it === "string" ? it : (it.site || it.name || "");
    li.textContent = site;
    li.addEventListener("click", async () => {
      setStatus(`Preenchendo ${site}...`);
      const r = await chrome.runtime.sendMessage({ type: "jarvis:autofillHere", site });
      if (r?.ok) setStatus(`Preenchido: ${site}`, "ok");
      else setStatus(r?.error || "Falha.", "err");
    });
    ul.appendChild(li);
  }
  ul.hidden = false;
  setStatus(`${items.length} site(s) no cofre.`, "ok");
});

load();
