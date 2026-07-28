export type MensajeVisible = {
  rol: "user" | "assistant";
  contenido: string;
  creado_en: string;
};

export type TramiteDetalle = {
  tramite_id: string;
  nombre_oficial: string;
  organismo: string;
  categoria: string;
  requisitos: string[];
  costo: string;
  modalidad: string;
  duracion: string;
  pasos: string[];
  enlaces_oficiales: string[];
  telefono_contacto: string;
  email_contacto: string;
};

export type TramiteFrecuente = {
  tramite_id: string;
  nombre_oficial: string;
  veces_consultado: number;
};

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function obtenerHistorial(
  sessionId: string
): Promise<MensajeVisible[]> {
  const respuesta = await fetch(`${BASE_URL}/sesiones/${sessionId}/mensajes`);
  if (!respuesta.ok) {
    return [];
  }
  return respuesta.json();
}

export async function obtenerTramite(
  tramiteId: string
): Promise<TramiteDetalle | null> {
  const respuesta = await fetch(`${BASE_URL}/tramites/${tramiteId}`);
  if (!respuesta.ok) {
    return null;
  }
  return respuesta.json();
}

export async function obtenerTramitesFrecuentes(
  organismo: string
): Promise<TramiteFrecuente[]> {
  const respuesta = await fetch(
    `${BASE_URL}/organismos/${encodeURIComponent(organismo)}/tramites-frecuentes`
  );
  if (!respuesta.ok) {
    return [];
  }
  return respuesta.json();
}
