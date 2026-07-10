"use client";

import { useEffect, useState } from "react";

const CLAVE_SESSION_ID = "macacha_session_id";

export function useSession(): { sessionId: string | null } {
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    const existente = localStorage.getItem(CLAVE_SESSION_ID);
    if (existente) {
      setSessionId(existente);
      return;
    }
    const nuevo = crypto.randomUUID();
    localStorage.setItem(CLAVE_SESSION_ID, nuevo);
    setSessionId(nuevo);
  }, []);

  return { sessionId };
}
