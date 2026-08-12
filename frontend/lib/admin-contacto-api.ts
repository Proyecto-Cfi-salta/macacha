import type { MensajeAdmin } from "./admin-api";

export type SolicitudContacto = {
  id: string;
  session_id: string;
  tramite_id: string | null;
  tramite_nombre: string | null;
  organismo_id: number | null;
  organismo: string | null;
  nombre: string;
  email: string;
  telefono: string;
  consulta: string;
  estado: "pendiente" | "resuelto";
  creado_en: string;
};

export type SolicitudContactoDetalle = SolicitudContacto & {
  mensajes: MensajeAdmin[];
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listarSolicitudesContacto(): Promise<SolicitudContacto[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto`, { credentials: "include" });
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la lista de contacto");
  }
  return respuesta.json();
}

export async function obtenerSolicitudContacto(
  id: string
): Promise<SolicitudContactoDetalle | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/${id}`, {
    credentials: "include",
  });
  if (respuesta.status === 404) {
    return null;
  }
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la solicitud");
  }
  return respuesta.json();
}

export async function editarEstadoContacto(
  id: string,
  estado: "pendiente" | "resuelto"
): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ estado }),
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo actualizar el estado");
  }
}
