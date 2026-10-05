"use client";

import { useEffect, useRef, useState } from "react";
import { useMicrophoneRecorder } from "../hooks/useMicrophoneRecorder";
import { transcribirAudio, type AudioTranscriptionResult } from "../lib/audio-api";
import {
  combinarTexto,
  DURACION_MAXIMA_GRABACION_MS,
  textoAyudaAudio,
  type EstadoTranscripcion,
} from "../lib/audio-ui";

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
  const [soportaMicrofono, setSoportaMicrofono] = useState(false);
  const [transcripcion, setTranscripcion] = useState<EstadoTranscripcion>("idle");
  const [resultado, setResultado] = useState<AudioTranscriptionResult | null>(null);
  const [errorTranscripcion, setErrorTranscripcion] = useState<string | null>(null);

  const microfono = useMicrophoneRecorder();
  const procesadaRef = useRef<Blob | null>(null);

  useEffect(() => {
    setSoportaMicrofono(
      Boolean(navigator.mediaDevices?.getUserMedia) && typeof MediaRecorder !== "undefined"
    );
  }, []);

  const ocupado =
    microfono.status === "requesting" ||
    microfono.status === "recording" ||
    transcripcion === "transcribing";

  async function procesarGrabacion() {
    const grabacion = microfono.recording;
    if (!grabacion || procesadaRef.current === grabacion.blob) return;

    procesadaRef.current = grabacion.blob;
    setTranscripcion("transcribing");
    setResultado(null);
    setErrorTranscripcion(null);

    try {
      const respuesta = await transcribirAudio(grabacion.blob, grabacion.mimeType);
      // La transcripción nunca se envía sola: queda en el campo y la persona decide.
      setTexto((previo) => combinarTexto(previo, respuesta.text.trim()));
      setResultado(respuesta);
      setTranscripcion(respuesta.review_required ? "review" : "ready");
      microfono.clearRecording();
    } catch (error) {
      setErrorTranscripcion(
        error instanceof Error ? error.message : "No pude transcribir el audio. Probá nuevamente."
      );
      setTranscripcion("error");
    }
  }

  useEffect(() => {
    if (microfono.status === "ready" && microfono.recording) {
      void procesarGrabacion();
    }
    // procesarGrabacion solo usa la grabación correspondiente a este cambio.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [microfono.status, microfono.recording]);

  useEffect(() => {
    if (microfono.status === "recording" && microfono.elapsedMs >= DURACION_MAXIMA_GRABACION_MS) {
      microfono.stopRecording();
    }
    // stopRecording es estable en la práctica; solo reaccionamos al tiempo transcurrido.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [microfono.status, microfono.elapsedMs]);

  function enviar() {
    const limpio = texto.trim();
    if (!limpio || disabled || ocupado) return;
    onEnviar(limpio);
    setTexto("");
    setTranscripcion("idle");
    setResultado(null);
    setErrorTranscripcion(null);
  }

  function alternarMicrofono() {
    if (disabled || transcripcion === "transcribing" || microfono.status === "requesting") return;
    if (microfono.status === "recording") {
      microfono.stopRecording();
      return;
    }
    setTranscripcion("idle");
    setResultado(null);
    setErrorTranscripcion(null);
    procesadaRef.current = null;
    void microfono.startRecording();
  }

  function cerrarAviso() {
    microfono.clearRecording();
    procesadaRef.current = null;
    setTranscripcion("idle");
    setResultado(null);
    setErrorTranscripcion(null);
  }

  const hayError = transcripcion === "error" || microfono.status === "error";
  const grabando = microfono.status === "recording";
  const transcribiendo = transcripcion === "transcribing";
  const ayuda = textoAyudaAudio({
    microfono: microfono.status,
    transcripcion,
    duracionMs: microfono.elapsedMs,
    errorMicrofono: microfono.errorMessage,
    errorTranscripcion,
  });
  const otraLectura =
    transcripcion === "review" &&
    resultado?.alternative_text?.trim() &&
    resultado.alternative_text.trim() !== texto.trim()
      ? resultado.alternative_text.trim()
      : null;
  const claseAyuda = hayError
    ? "texto-error"
    : transcripcion === "review"
      ? "text-amber-600 dark:text-amber-300"
      : transcripcion === "ready"
        ? "text-emerald-600 dark:text-emerald-400"
        : "texto-secundario";

  return (
    <div className="border-t border-gray-200 p-4 dark:border-white/10">
      <div className="flex gap-2">
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
          disabled={disabled || ocupado}
          onChange={(e) => {
            setTexto(e.target.value);
            if (transcripcion === "ready" || transcripcion === "review") {
              setTranscripcion("idle");
              setResultado(null);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
          placeholder={
            grabando
              ? "Grabando…"
              : transcribiendo
                ? "Transcribiendo…"
                : "Escribí tu consulta sobre un trámite..."
          }
          aria-label="Escribí tu consulta"
        />
        {soportaMicrofono && (
          <>
            {grabando && (
              <button
                type="button"
                onClick={microfono.cancelRecording}
                aria-label="Cancelar grabación"
                title="Cancelar grabación"
                className="boton-neutro flex h-10 w-10 flex-none items-center justify-center px-0 text-lg"
              >
                ×
              </button>
            )}
            <button
              type="button"
              onClick={alternarMicrofono}
              disabled={disabled || microfono.status === "requesting" || transcribiendo}
              aria-label={
                grabando
                  ? "Detener grabación"
                  : transcribiendo
                    ? "Transcribiendo audio"
                    : "Grabar consulta con micrófono"
              }
              title={grabando ? "Detener grabación" : transcribiendo ? "Transcribiendo audio" : "Usar micrófono"}
              className={`boton-neutro flex h-10 w-10 flex-none items-center justify-center px-0 ${
                grabando ? "animate-pulse text-rose-500 ring-2 ring-rose-400" : ""
              }`}
            >
              {grabando ? (
                <span aria-hidden="true" className="h-3.5 w-3.5 rounded-sm bg-current" />
              ) : microfono.status === "requesting" || transcribiendo ? (
                <span
                  aria-hidden="true"
                  className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
                />
              ) : (
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  className="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.9"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 14.25a4 4 0 0 0 4-4v-4a4 4 0 1 0-8 0v4a4 4 0 0 0 4 4Zm7-4a7 7 0 0 1-14 0M12 17.25v3.5M8.75 20.75h6.5" />
                </svg>
              )}
            </button>
          </>
        )}
        <button
          className={`boton-primario ${ocupado ? "max-[480px]:hidden" : ""}`}
          disabled={disabled || ocupado || !texto.trim()}
          onClick={enviar}
        >
          Enviar
        </button>
      </div>

      {soportaMicrofono && (
        <div className="mt-2 flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
          <div className="min-w-0 flex-1">
            <p
              className={`text-xs ${claseAyuda}`}
              role={hayError ? "alert" : "status"}
              aria-live="polite"
            >
              {ayuda}
            </p>
            {otraLectura && (
              <p className="mt-1 text-xs texto-secundario">Otra lectura detectada: “{otraLectura}”</p>
            )}
          </div>
          {hayError && (
            <div className="flex gap-3 text-xs">
              {transcripcion === "error" && microfono.recording && (
                <button
                  type="button"
                  className="underline"
                  onClick={() => {
                    procesadaRef.current = null;
                    void procesarGrabacion();
                  }}
                >
                  Reintentar
                </button>
              )}
              <button type="button" className="underline" onClick={cerrarAviso}>
                Cerrar aviso
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
