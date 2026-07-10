export type MensajeVisible = {
  rol: "user" | "assistant";
  contenido: string;
  creado_en: string;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function obtenerHistorial(
  sessionId: string
): Promise<MensajeVisible[]> {
  const respuesta = await fetch(`${BASE_URL}/sesiones/${sessionId}/mensajes`);
  if (!respuesta.ok) {
    return [];
  }
  return respuesta.json();
}
