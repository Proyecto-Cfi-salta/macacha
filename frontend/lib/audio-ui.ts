export type EstadoMicrofono = "idle" | "requesting" | "recording" | "ready" | "error";
export type EstadoTranscripcion = "idle" | "transcribing" | "ready" | "review" | "error";

export const AVISO_PRIVACIDAD_AUDIO =
  "El audio se envía a un servicio externo para transcribirlo y no queda guardado en Macacha.";

export function formatearDuracion(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutos = Math.floor(total / 60);
  const segundos = total % 60;
  return `${minutos}:${segundos.toString().padStart(2, "0")}`;
}

export function extensionPorMime(mime: string): string {
  const m = mime.toLowerCase();
  if (m.includes("ogg")) return "ogg";
  if (m.includes("mp4") || m.includes("m4a")) return "mp4";
  if (m.includes("wav")) return "wav";
  if (m.includes("mpeg") || m.includes("mp3")) return "mp3";
  return "webm";
}

export function textoAyudaAudio(estado: {
  microfono: EstadoMicrofono;
  transcripcion: EstadoTranscripcion;
  duracionMs: number;
  errorMicrofono: string | null;
  errorTranscripcion: string | null;
}): string {
  if (estado.microfono === "requesting") {
    return `Esperando permiso para usar el micrófono… ${AVISO_PRIVACIDAD_AUDIO}`;
  }
  if (estado.microfono === "recording") {
    return `Grabando ${formatearDuracion(estado.duracionMs)} · Tocá detener cuando termines. ${AVISO_PRIVACIDAD_AUDIO}`;
  }
  if (estado.transcripcion === "transcribing") return "Transcribiendo tu audio…";
  if (estado.transcripcion === "review") {
    return "La transcripción necesita revisión. Leé el texto antes de enviarlo.";
  }
  if (estado.transcripcion === "ready") return "Transcripción lista. Revisá el texto y presioná Enviar.";
  if (estado.transcripcion === "error" && estado.errorTranscripcion) return estado.errorTranscripcion;
  if (estado.microfono === "error" && estado.errorMicrofono) return estado.errorMicrofono;
  return "Podés escribir tu consulta o grabarla con el micrófono.";
}
