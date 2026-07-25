export type ToolCall = {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
};

export type MensajeAdmin = {
  rol: "user" | "assistant" | "tool";
  contenido: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  creado_en: string;
};

export type SesionResumen = {
  id: string;
  creado_en: string;
  cantidad_mensajes: number;
  ultimo_mensaje: string | null;
  tramites_citados: string[];
};

export type ListaSesiones = {
  sesiones: SesionResumen[];
  total: number;
  page: number;
  page_size: number;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function login(
  email: string,
  password: string
): Promise<{ ok: true } | { ok: false }> {
  const respuesta = await fetch(`${BASE_URL}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  return respuesta.ok ? { ok: true } : { ok: false };
}

export async function logout(): Promise<void> {
  await fetch(`${BASE_URL}/admin/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function obtenerSesiones(
  page: number,
  pageSize: number
): Promise<ListaSesiones> {
  const respuesta = await fetch(
    `${BASE_URL}/admin/sesiones?page=${page}&page_size=${pageSize}`,
    { credentials: "include" }
  );
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la lista de chats");
  }
  return respuesta.json();
}

export async function obtenerSesion(id: string): Promise<MensajeAdmin[] | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/sesiones/${id}`, {
    credentials: "include",
  });
  if (respuesta.status === 404) {
    return null;
  }
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la sesión");
  }
  return respuesta.json();
}
