"use client";

import { useState } from "react";

export function CopyButton({ texto }: { texto: string }) {
  const [estado, setEstado] = useState<"idle" | "copiado" | "error">("idle");

  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto);
      setEstado("copiado");
    } catch {
      setEstado("error");
    }
    setTimeout(() => setEstado("idle"), 1500);
  }

  return (
    <button
      type="button"
      onClick={copiar}
      className="ml-2 text-xs text-blue-700 underline"
      aria-label={`Copiar ${texto}`}
    >
      {estado === "idle" && "Copiar"}
      {estado === "copiado" && "Copiado ✓"}
      {estado === "error" && "No se pudo copiar"}
    </button>
  );
}
