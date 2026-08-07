export type Faq = { pregunta: string; respuesta: string };

export type Organismo = { id: number; nombre: string };

export type TramiteResumen = {
  id: string;
  nombre_oficial: string;
  organismo: string;
  categoria: string;
  veces_consultado: number;
  numero_version: number | null;
};

export type TramiteDetalleAdmin = {
  organismo: string;
  categoria: string;
  nombre_oficial: string;
  descripcion: string;
  objetivo: string;
  requisitos: string[];
  pasos: string[];
  costo: string;
  modalidad: string;
  duracion: string;
  telefono_contacto: string;
  email_contacto: string;
  problemas_frecuentes: string[];
  sinonimos: string[];
  keywords: string[];
  enlaces_oficiales: string[];
  preguntas_frecuentes: Faq[];
};

export type GuardarTramiteResultado = {
  tramite_id: string;
  numero_version: number;
  cambios: boolean;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listarTramites(): Promise<TramiteResumen[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/tramites`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la lista de trámites");
  }
  return respuesta.json();
}

export async function listarOrganismos(): Promise<Organismo[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/organismos`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    throw new Error("No se pudieron cargar los organismos");
  }
  return respuesta.json();
}

export async function obtenerTramiteAdmin(id: string): Promise<TramiteDetalleAdmin | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/tramites/${id}`, {
    credentials: "include",
  });
  if (respuesta.status === 404) {
    return null;
  }
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar el trámite");
  }
  return respuesta.json();
}

async function guardarTramite(
  url: string,
  method: "POST" | "PUT",
  datos: TramiteDetalleAdmin
): Promise<GuardarTramiteResultado> {
  const respuesta = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => null);
    throw new Error(cuerpo?.detail ?? "No se pudo guardar el trámite");
  }
  return respuesta.json();
}

export async function crearTramite(datos: TramiteDetalleAdmin): Promise<GuardarTramiteResultado> {
  return guardarTramite(`${BASE_URL}/admin/tramites`, "POST", datos);
}

export async function editarTramite(
  id: string,
  datos: TramiteDetalleAdmin
): Promise<GuardarTramiteResultado> {
  return guardarTramite(`${BASE_URL}/admin/tramites/${id}`, "PUT", datos);
}
