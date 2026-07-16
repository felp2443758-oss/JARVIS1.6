// Multi-user auth client for the JARVIS SPA.
// Stores the session JWT in localStorage and attaches it to axios/fetch calls.
import axios from "axios";
import { API } from "./api";

const TOKEN_KEY = "jarvis.session";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (_) { return ""; }
}
export function setToken(t) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch (_) {}
}

// Global axios interceptor: attach bearer to every request.
axios.interceptors.request.use((config) => {
  const t = getToken();
  if (t && config.url && String(config.url).startsWith(API)) {
    config.headers = { ...(config.headers || {}), Authorization: `Bearer ${t}` };
  }
  return config;
});

// Pick up ?token=... from the URL after Google OAuth redirect and persist it.
export function consumeTokenFromUrl() {
  const url = new URL(window.location.href);
  const t = url.searchParams.get("token");
  if (t) {
    setToken(t);
    url.searchParams.delete("token");
    url.searchParams.delete("connected");
    window.history.replaceState({}, "", url.toString());
    return t;
  }
  return null;
}

export async function fetchMe() {
  const t = getToken();
  if (!t) return null;
  try {
    const r = await axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${t}` } });
    return r.data;
  } catch (_) {
    return null;
  }
}

export async function startGoogleLogin() {
  const r = await axios.get(`${API}/auth/google/login`);
  window.location.href = r.data.auth_url;
}

export function logout() {
  setToken("");
  window.location.href = "/";
}

// ---------------- Vault ----------------
export async function vaultList() {
  const r = await axios.get(`${API}/vault/list`);
  return r.data.items || [];
}
export async function vaultPut(entry) {
  const r = await axios.post(`${API}/vault/put`, entry);
  return r.data;
}
export async function vaultDelete(site) {
  const r = await axios.delete(`${API}/vault/${encodeURIComponent(site)}`);
  return r.data;
}

// ---------------- Agent commands ----------------
export async function listAgents() {
  const r = await axios.get(`${API}/agent/list`);
  return r.data.agents || [];
}
export async function sendAgentCommand(command, args = {}, opts = {}) {
  const r = await axios.post(`${API}/agent/command`, {
    command, args,
    agent_id: opts.agentId,
    timeout: opts.timeout || 30,
  }, { timeout: (opts.timeout || 30) * 1000 + 5000 });
  return r.data;
}
export async function fetchAgentPairToken(agentName = "Home-PC") {
  const r = await axios.post(`${API}/auth/agent/pair`, null, { params: { agent_name: agentName } });
  return r.data;
}
