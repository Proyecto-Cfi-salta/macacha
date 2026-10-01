import { BASE_URL } from "./api";

export const MOTIVOS = [
  { valor: "no_respondio", texto: "No respondió mi pregunta" },
  { valor: "info_incorrecta", texto: "La información era incorrecta" },
  { valor: "faltaba_info", texto: "Faltaba información" },
  { valor: "otro_tramite", texto: "Me mostró otro trámite" },
  { valor: "desactualizada", texto: "La información estaba desactualizada" },
  { valor: "poco_clara", texto: "La respuesta no fue clara" },
  { valor: "otro", texto: "Otro" },
] as const;

export type MotivoFeedback = (typeof MOTIVOS)[number]["valor"];

export const MAX_COMENTARIO = 500;

export type FeedbackVoto = {
  util: boolean;
  motivo: MotivoFeedback | null;
  comentario: string | null;
};

export type EstadoFeedback = "pregunta" | "detalle" | "gracias_si" | "gracias_no";

export type PayloadFeedback = {
  session_id: string;
  mensaje_id: string;
  util: boolean;
  motivo?: MotivoFeedback;
  comentario?: string;
};

export function estadoInicialFeedback(
  feedback: FeedbackVoto | null | undefined
): EstadoFeedback {
  if (!feedback) return "pregunta";
  if (feedback.util) return "gracias_si";
  return feedback.motivo || feedback.comentario ? "gracias_no" : "detalle";
}

export function textoMotivo(valor: string | null): string {
  return MOTIVOS.find((m) => m.valor === valor)?.texto ?? "";
}

export async function enviarFeedback(payload: PayloadFeedback): Promise<boolean> {
  try {
    const respuesta = await fetch(`${BASE_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return respuesta.ok;
  } catch {
    return false;
  }
}
