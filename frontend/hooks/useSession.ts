"use client";

import { useEffect, useState } from "react";

export function useSession(): { sessionId: string | null } {
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    setSessionId(crypto.randomUUID());
  }, []);

  return { sessionId };
}
