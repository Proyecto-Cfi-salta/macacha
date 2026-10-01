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

export type Casilla = {
  id: number;
  nombre: string;
  email_contacto: string | null;
};

export async function listarCasillas(): Promise<Casilla[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/casillas`, { credentials: "include" });
  if (!respuesta.ok) {
    throw new Error("No se pudieron cargar las casillas de contacto");
  }
  return respuesta.json();
}

export async function guardarCasilla(organismoId: number, email: string | null): Promise<Casilla> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/casillas/${organismoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email_contacto: email }),
  });
  if (!respuesta.ok) {
    let mensaje = "No se pudo guardar la casilla";
    try {
      const cuerpo = await respuesta.json();
      if (typeof cuerpo.detail === "string") mensaje = cuerpo.detail;
    } catch {
      // el cuerpo no era JSON: se usa el mensaje genérico
    }
    throw new Error(mensaje);
  }
  return respuesta.json();
}
