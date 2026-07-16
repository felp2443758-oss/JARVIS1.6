import React, { useEffect, useMemo, useRef, useState } from "react";
import "@/App.css";
import "@/lib/auth"; // registers axios interceptor
import Dashboard from "@/components/Dashboard";
import AuthGate from "@/components/AuthGate";

export default function App() {
  return (
    <div className="App bg-grid bg-grain h-screen w-screen overflow-hidden relative" data-testid="jarvis-root">
      <AuthGate>
        {(user) => <Dashboard user={user} />}
      </AuthGate>
    </div>
  );
}
