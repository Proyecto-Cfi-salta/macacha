"use client";

import { useState } from "react";

export function ChatInput({
  disabled,
  onEnviar,
  onAbrirFicha,
}: {
  disabled: boolean;
  onEnviar: (texto: string) => void;
  onAbrirFicha?: () => void;
}) {
  const [texto, setTexto] = useState("");

  function enviar() {
    const limpio = texto.trim();
    if (!limpio || disabled) return;
    onEnviar(limpio);
    setTexto("");
  }

  return (
    <div className="flex gap-2 border-t border-gray-200 p-4 dark:border-white/10">
      {onAbrirFicha && (
        <button
          type="button"
          onClick={onAbrirFicha}
          aria-label="Ver ficha del trámite"
          className="boton-neutro flex w-14 flex-none flex-col items-center justify-center gap-0.5 px-1 min-[1051px]:hidden"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
            <path d="M14 3v5h5M9 13h6M9 17h6" />
          </svg>
          <span className="text-[11px] leading-none">Ficha</span>
        </button>
      )}
      <textarea
        className="campo-input flex-1 resize-none"
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
      <button className="boton-primario" disabled={disabled || !texto.trim()} onClick={enviar}>
        Enviar
      </button>
    </div>
  );
}
