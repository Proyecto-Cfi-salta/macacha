"use client";

import { useState } from "react";
import {
  MAX_COMENTARIO,
  MOTIVOS,
  enviarFeedback,
  estadoInicialFeedback,
  type EstadoFeedback,
  type FeedbackVoto,
  type MotivoFeedback,
} from "../lib/feedback";

export function FeedbackRespuesta({
  sessionId,
  mensajeId,
  feedbackInicial,
}: {
  sessionId: string;
  mensajeId: string;
  feedbackInicial?: FeedbackVoto | null;
}) {
  const [estado, setEstado] = useState<EstadoFeedback>(estadoInicialFeedback(feedbackInicial));
  const [util, setUtil] = useState<boolean | null>(feedbackInicial?.util ?? null);
  const [motivo, setMotivo] = useState<MotivoFeedback | "">(feedbackInicial?.motivo ?? "");
  const [comentario, setComentario] = useState(feedbackInicial?.comentario ?? "");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(false);

  async function votar(nuevoUtil: boolean) {
    if (enviando) return;
    setEnviando(true);
    setError(false);
    const ok = await enviarFeedback({ session_id: sessionId, mensaje_id: mensajeId, util: nuevoUtil });
    setEnviando(false);
    if (!ok) {
      setError(true);
      return;
    }
    setUtil(nuevoUtil);
    if (nuevoUtil) {
      setMotivo("");
      setComentario("");
      setEstado("gracias_si");
    } else {
      setEstado("detalle");
    }
  }

  async function enviarDetalle() {
    if (enviando) return;
    const comentarioLimpio = comentario.trim();
    if (!motivo && !comentarioLimpio) {
      setEstado("gracias_no");
      return;
    }
    setEnviando(true);
    setError(false);
    const ok = await enviarFeedback({
      session_id: sessionId,
      mensaje_id: mensajeId,
      util: false,
      ...(motivo ? { motivo } : {}),
      ...(comentarioLimpio ? { comentario: comentarioLimpio } : {}),
    });
    setEnviando(false);
    if (!ok) {
      setError(true);
      return;
    }
    setEstado("gracias_no");
  }

  const contenedor = "mt-3 border-t border-gray-300 pt-2 text-sm dark:border-white/20";

  if (estado === "gracias_si" || estado === "gracias_no") {
    return (
      <div className={`${contenedor} flex flex-wrap items-center gap-2`}>
        <span className="texto-secundario">
          {estado === "gracias_si"
            ? "¡Gracias por tu opinión!"
            : "Gracias, tu comentario nos ayuda a mejorar."}
        </span>
        <button type="button" onClick={() => setEstado("pregunta")} className="underline">
          Cambiar mi voto
        </button>
      </div>
    );
  }

  return (
    <div className={contenedor}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="texto-secundario">¿Te sirvió esta respuesta?</span>
        <button
          type="button"
          disabled={enviando}
          aria-pressed={util === true}
          onClick={() => votar(true)}
          className={`boton-neutro ${util === true ? "ring-2 ring-emerald-400" : ""}`}
        >
          👍 Sí
        </button>
        <button
          type="button"
          disabled={enviando}
          aria-pressed={util === false}
          onClick={() => votar(false)}
          className={`boton-neutro ${util === false ? "ring-2 ring-rose-400" : ""}`}
        >
          👎 No
        </button>
      </div>

      {estado === "detalle" && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <select
            value={motivo}
            onChange={(e) => setMotivo(e.target.value as MotivoFeedback | "")}
            aria-label="¿Por qué no te sirvió?"
            className="campo-input"
          >
            <option value="">¿Por qué no te sirvió?</option>
            {MOTIVOS.map((m) => (
              <option key={m.valor} value={m.valor}>
                {m.texto}
              </option>
            ))}
          </select>
          <textarea
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            maxLength={MAX_COMENTARIO}
            rows={2}
            placeholder="Comentario opcional"
            aria-label="Comentario opcional"
            className="campo-input resize-none"
          />
          <p className="text-xs texto-secundario sm:col-span-2">
            No incluyas datos personales en tu comentario.
          </p>
          <div className="sm:col-span-2">
            <button type="button" disabled={enviando} onClick={enviarDetalle} className="boton-secundario">
              Enviar
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-1 text-xs texto-error">No se pudo enviar tu opinión. Probá de nuevo.</p>
      )}
    </div>
  );
}
