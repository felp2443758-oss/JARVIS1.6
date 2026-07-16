import React, { useEffect, useState } from "react";
import { Trash2, Plus, Shield, Loader2, Eye, EyeOff, KeyRound } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { vaultList, vaultPut, vaultDelete } from "@/lib/auth";

export default function CredentialVault({ open, onOpenChange }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ site: "", username: "", password: "", url: "", notes: "" });
  const [showPwd, setShowPwd] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const arr = await vaultList();
      setItems(arr);
    } finally { setLoading(false); }
  }
  useEffect(() => { if (open) { reload(); setShowForm(false); } }, [open]);

  async function save() {
    if (!form.site || !form.username || !form.password) return;
    await vaultPut(form);
    setForm({ site: "", username: "", password: "", url: "", notes: "" });
    setShowForm(false);
    reload();
  }

  async function remove(site) {
    if (!window.confirm(`Remover credencial de ${site}?`)) return;
    await vaultDelete(site);
    reload();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-[#04101c] border border-cyan-500/30 text-cyan-100">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 tracking-widest text-cyan-200">
            <KeyRound size={18} /> COFRE DE CREDENCIAIS
          </DialogTitle>
        </DialogHeader>

        <div className="flex items-center justify-between">
          <p className="text-xs text-cyan-400/60 flex items-center gap-2">
            <Shield size={13} /> AES-GCM, chave derivada só do lado do servidor. Somente seu agente pareado descriptografa.
          </p>
          <Button variant="outline" size="sm" onClick={() => setShowForm((v) => !v)}
                  className="border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/10">
            <Plus size={14} className="mr-1" /> Nova
          </Button>
        </div>

        {showForm && (
          <div className="mt-3 p-4 rounded border border-cyan-500/25 bg-cyan-500/5 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[11px] tracking-widest text-cyan-400/70">SITE (ex: spotify)</Label>
                <Input value={form.site} onChange={(e) => setForm({ ...form, site: e.target.value })}
                       className="bg-black/40 border-cyan-500/30" />
              </div>
              <div>
                <Label className="text-[11px] tracking-widest text-cyan-400/70">URL (opcional)</Label>
                <Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
                       placeholder="https://accounts.spotify.com/login"
                       className="bg-black/40 border-cyan-500/30" />
              </div>
              <div>
                <Label className="text-[11px] tracking-widest text-cyan-400/70">USUÁRIO / E-MAIL</Label>
                <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                       className="bg-black/40 border-cyan-500/30" />
              </div>
              <div>
                <Label className="text-[11px] tracking-widest text-cyan-400/70">SENHA</Label>
                <div className="relative">
                  <Input type={showPwd ? "text" : "password"} value={form.password}
                         onChange={(e) => setForm({ ...form, password: e.target.value })}
                         className="bg-black/40 border-cyan-500/30 pr-8" />
                  <button type="button" onClick={() => setShowPwd(v => !v)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-cyan-400/70">
                    {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </div>
            <div>
              <Label className="text-[11px] tracking-widest text-cyan-400/70">NOTAS</Label>
              <Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                        className="bg-black/40 border-cyan-500/30" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setShowForm(false)} className="text-cyan-300/70">Cancelar</Button>
              <Button onClick={save} className="bg-cyan-500/20 border border-cyan-400/40 text-cyan-100 hover:bg-cyan-500/30">
                Salvar
              </Button>
            </div>
          </div>
        )}

        <div className="mt-4 min-h-[180px]">
          {loading ? (
            <div className="flex items-center gap-2 text-cyan-400/70 text-sm">
              <Loader2 className="animate-spin" size={14} /> carregando…
            </div>
          ) : items.length === 0 ? (
            <div className="text-cyan-400/50 text-sm italic">Nenhuma credencial salva ainda.</div>
          ) : (
            <div className="space-y-2">
              {items.map((it) => (
                <div key={it.site} className="flex items-center justify-between p-3 rounded border border-cyan-500/20 bg-black/30">
                  <div>
                    <div className="text-cyan-100 tracking-wider text-sm">{it.site_display || it.site}</div>
                    <div className="text-cyan-500/50 text-[10px]">atualizado em {(it.updated_at || "").slice(0, 19).replace("T", " ")}</div>
                  </div>
                  <Button size="icon" variant="ghost" onClick={() => remove(it.site)} className="text-red-400/70 hover:text-red-300">
                    <Trash2 size={16} />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter className="text-[10px] text-cyan-500/40">
          Total: {items.length} credencial(is)
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
