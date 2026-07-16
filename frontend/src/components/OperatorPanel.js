import React, { useEffect, useState } from "react";
import { Terminal, Play, Copy, Loader2, Cpu, Link2, Send, Download, CheckCircle2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { listAgents, sendAgentCommand } from "@/lib/auth";
import { API } from "@/lib/api";
import { getToken } from "@/lib/auth";

const QUICK_COMMANDS = [
  { command: "system_info", label: "Info do sistema", args: () => ({}) },
  { command: "list_apps", label: "Listar apps abertos", args: () => ({}) },
  { command: "screenshot", label: "Screenshot do desktop", args: () => ({}) },
  { command: "open_app", label: "Abrir app…", args: (v) => ({ name: v || "spotify" }), prompt: "Nome do app" },
  { command: "open_url", label: "Abrir URL…", args: (v) => ({ url: v || "https://google.com" }), prompt: "URL" },
  { command: "volume", label: "Volume +", args: () => ({ action: "up", steps: 3 }) },
  { command: "volume", label: "Volume –", args: () => ({ action: "down", steps: 3 }) },
  { command: "browser_search", label: "Buscar no Google…", args: (v) => ({ engine: "google", query: v }), prompt: "O que buscar?" },
  { command: "spotify_play", label: "Tocar no Spotify…", args: (v) => ({ query: v }), prompt: "Música ou artista" },
];

export default function OperatorPanel({ open, onOpenChange }) {
  const [agents, setAgents] = useState([]);
  const [selected, setSelected] = useState("");
  const [agentName, setAgentName] = useState("Home-PC");
  const [command, setCommand] = useState("open_app");
  const [argsJson, setArgsJson] = useState('{"name":"spotify"}');
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    setCopied(false);
    (async () => {
      const a = await listAgents();
      setAgents(a);
      if (a[0]) setSelected(a[0]);
    })();
  }, [open]);

  async function runQuick(q) {
    let val = "";
    if (q.prompt) {
      val = window.prompt(q.prompt) || "";
      if (!val) return;
    }
    await runCommand(q.command, q.args(val));
  }

  async function runCommand(cmd, args) {
    setRunning(true); setOutput(null);
    try {
      const r = await sendAgentCommand(cmd, args, { agentId: selected || undefined, timeout: 60 });
      setOutput(r);
    } catch (e) {
      setOutput({ ok: false, error: e?.response?.data?.detail || e.message });
    } finally { setRunning(false); }
  }

  async function runCustom() {
    let parsed = {};
    try { parsed = JSON.parse(argsJson || "{}"); }
    catch (_) { return setOutput({ ok: false, error: "JSON de args inválido" }); }
    await runCommand(command, parsed);
  }

  // ---- 1-click pairing helpers ----
  async function downloadConfig() {
    const tok = getToken();
    const url = `${API}/agent/download-config?agent_name=${encodeURIComponent(agentName)}&token=${encodeURIComponent(tok)}`;
    // The endpoint already sends Content-Disposition: attachment; the browser will save it.
    window.open(url, "_blank");
  }

  async function copyPowerShell() {
    const tok = getToken();
    // The command downloads the install-script from the backend and pipes it into iex.
    const base = API.replace(/\/api$/, "");
    const oneLiner =
      `powershell -Command "iwr -UseBasicParsing '${API}/agent/install-script?agent_name=${encodeURIComponent(agentName)}&token=${tok}' | Select-Object -ExpandProperty Content | iex"`;
    await navigator.clipboard.writeText(oneLiner);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl bg-[#04101c] border border-cyan-500/30 text-cyan-100">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 tracking-widest text-cyan-200">
            <Terminal size={18} /> OPERADOR REMOTO
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-[11px] tracking-widest text-cyan-400/70">EDGE AGENT</Label>
            {agents.length === 0 ? (
              <div className="text-xs text-amber-300/80 p-2 rounded border border-amber-500/30 bg-amber-500/5">
                Nenhum agente conectado.
              </div>
            ) : (
              <Select value={selected} onValueChange={setSelected}>
                <SelectTrigger className="bg-black/40 border-cyan-500/30"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#04101c] border-cyan-500/30 text-cyan-100">
                  {agents.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>
          <div>
            <Label className="text-[11px] tracking-widest text-cyan-400/70">STATUS</Label>
            <div className="flex items-center gap-2 h-9 px-3 rounded border border-cyan-500/25 bg-black/30 text-xs">
              <Cpu size={14} className={agents.length ? "text-emerald-400" : "text-red-400"} />
              {agents.length ? `${agents.length} agente(s) online` : "nenhum agente"}
            </div>
          </div>
        </div>

        {/* ------- Simplified 1-click pairing ------- */}
        {agents.length === 0 && (
          <div className="p-4 rounded border border-cyan-500/25 bg-cyan-500/5 space-y-3">
            <div className="flex items-center gap-2 text-cyan-200 text-sm tracking-wider">
              <Link2 size={14} /> Parear este PC ao J.A.R.V.I.S.
            </div>
            <div className="grid grid-cols-3 gap-2 items-end">
              <div className="col-span-1">
                <Label className="text-[10px] tracking-widest text-cyan-400/70">NOME DO PC</Label>
                <Input value={agentName} onChange={(e) => setAgentName(e.target.value)}
                       className="bg-black/40 border-cyan-500/30 h-9" />
              </div>
              <Button onClick={downloadConfig}
                      className="col-span-1 h-9 bg-cyan-500/20 border border-cyan-400/40 text-cyan-100 hover:bg-cyan-500/30">
                <Download size={14} className="mr-2" /> Baixar agent.json
              </Button>
              <Button onClick={copyPowerShell} variant="outline"
                      className="col-span-1 h-9 border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/10">
                {copied ? <><CheckCircle2 size={14} className="mr-2 text-emerald-400" /> Copiado!</> :
                          <><Copy size={14} className="mr-2" /> Copiar 1-liner PowerShell</>}
              </Button>
            </div>
            <div className="text-[11px] text-cyan-400/60 leading-relaxed">
              <b className="text-cyan-300">Opção A</b> — baixe o <code>agent.json</code> e coloque em <code>C:\Users\SEU_USUARIO\.jarvis\</code>.<br />
              <b className="text-cyan-300">Opção B</b> — cole o 1-liner num PowerShell (Windows) e ele grava o arquivo pra você.<br />
              Depois execute uma única vez: <code>install.bat</code> (dentro de <code>edge_agent/</code>) e finalmente <code>python agent_v2.py</code>.
            </div>
          </div>
        )}

        <div>
          <Label className="text-[11px] tracking-widest text-cyan-400/70">AÇÕES RÁPIDAS</Label>
          <div className="flex flex-wrap gap-2 mt-2">
            {QUICK_COMMANDS.map((q, i) => (
              <Button key={i} size="sm" variant="outline" onClick={() => runQuick(q)}
                      disabled={running || agents.length === 0}
                      className="border-cyan-500/30 text-cyan-200 hover:bg-cyan-500/10 text-xs">
                <Play size={11} className="mr-1" /> {q.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-1">
            <Label className="text-[11px] tracking-widest text-cyan-400/70">COMMAND</Label>
            <Input value={command} onChange={(e) => setCommand(e.target.value)} className="bg-black/40 border-cyan-500/30 font-mono text-xs" />
          </div>
          <div className="col-span-2">
            <Label className="text-[11px] tracking-widest text-cyan-400/70">ARGS (JSON)</Label>
            <Textarea rows={2} value={argsJson} onChange={(e) => setArgsJson(e.target.value)}
                      className="bg-black/40 border-cyan-500/30 font-mono text-xs" />
          </div>
        </div>

        <div className="flex justify-end">
          <Button onClick={runCustom} disabled={running || agents.length === 0}
                  className="bg-cyan-500/20 border border-cyan-400/40 text-cyan-100 hover:bg-cyan-500/30">
            {running ? <Loader2 className="animate-spin mr-2" size={14} /> : <Send size={14} className="mr-2" />}
            Executar
          </Button>
        </div>

        {output && (
          <div className={`p-3 rounded border text-xs font-mono ${output.ok ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-200" : "border-red-500/30 bg-red-500/5 text-red-200"}`}>
            <div className="opacity-70 mb-2">{output.ok ? "OK" : "ERRO"} • request_id={output.request_id || "—"}</div>
            <pre className="whitespace-pre-wrap break-words max-h-64 overflow-auto">
              {JSON.stringify(output, null, 2)}
            </pre>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
