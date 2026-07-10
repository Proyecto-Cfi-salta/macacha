"use client";

import { useState } from "react";

export function ChatInput({
  disabled,
  onEnviar,
}: {
  disabled: boolean;
  onEnviar: (texto: string) => void;
}) {
  const [texto, setTexto] = useState("");

  function enviar() {
    const limpio = texto.trim();
    if (!limpio || disabled) return;
    onEnviar(limpio);
    setTexto("");
  }

  return (
    <div className="flex gap-2 border-t border-gray-200 p-4">
      <textarea
        className="flex-1 resize-none rounded border border-gray-300 p-2"
        rows={2}
        value={texto}
        disabled={disabled}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            enviar();
          }
        }}
        placeholder="Escribí tu consulta sobre un trámite..."
      />
      <button
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        disabled={disabled || !texto.trim()}
        onClick={enviar}
      >
        Enviar
      </button>
    </div>
  );
}
