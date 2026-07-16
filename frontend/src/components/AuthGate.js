import React, { useEffect, useState } from "react";
import { LogIn, Cpu, Shield, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { startGoogleLogin, consumeTokenFromUrl, fetchMe, setToken } from "@/lib/auth";

export default function AuthGate({ onAuthed, children }) {
  const [state, setState] = useState({ loading: true, user: null });

  useEffect(() => {
    (async () => {
      // 1) If we just returned from Google, capture the token
      consumeTokenFromUrl();
      // 2) Ask the backend who I am
      const me = await fetchMe();
      setState({ loading: false, user: me });
      if (me && onAuthed) onAuthed(me);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state.loading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[#02060d] text-cyan-300">
        <Loader2 className="animate-spin mr-3" size={22} />
        <span className="tracking-widest text-sm">CARREGANDO JARVIS…</span>
      </div>
    );
  }

  if (state.user) {
    return typeof children === "function" ? children(state.user) : children;
  }

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-[#02060d] relative overflow-hidden">
      {/* Ambient rings */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <div className="w-[720px] h-[720px] rounded-full border border-cyan-500/10 animate-[spin_60s_linear_infinite]" />
        <div className="absolute w-[520px] h-[520px] rounded-full border border-cyan-500/20" />
        <div className="absolute w-[320px] h-[320px] rounded-full border border-cyan-400/30" />
      </div>

      <div className="relative z-10 max-w-md w-full mx-6 p-8 rounded-lg border border-cyan-500/30 bg-[#04101c]/80 backdrop-blur-xl shadow-[0_0_60px_-10px_rgba(34,211,238,0.25)]">
        <div className="flex items-center gap-3 mb-6">
          <Cpu className="text-cyan-300" size={28} />
          <div>
            <h1 className="text-cyan-200 text-2xl tracking-[0.35em] font-light">J.A.R.V.I.S.</h1>
            <p className="text-cyan-500/60 text-[10px] tracking-widest uppercase">Just A Rather Very Intelligent System</p>
          </div>
        </div>
        <p className="text-cyan-300/80 text-sm leading-relaxed mb-6">
          Faça login com sua conta Google para ativar seu assistente. Cada usuário tem sessão, memória
          e cofre de credenciais isolados.
        </p>
        <Button
          onClick={startGoogleLogin}
          className="w-full bg-cyan-500/10 border border-cyan-400/40 text-cyan-200 hover:bg-cyan-500/20 hover:text-cyan-100 h-12 tracking-widest text-[13px]"
        >
          <LogIn size={18} className="mr-2" /> ENTRAR COM GOOGLE
        </Button>
        <div className="mt-6 flex items-start gap-2 text-[11px] text-cyan-400/50">
          <Shield size={14} className="mt-0.5 shrink-0" />
          <span>
            Suas credenciais de sites (Spotify, etc.) são criptografadas com AES‑GCM usando uma chave
            derivada exclusivamente para você. Somente seu Edge Agent pareado consegue descriptografá-las.
          </span>
        </div>
      </div>
    </div>
  );
}
