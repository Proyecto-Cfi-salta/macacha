import type { Organismo } from "./admin-tramites-api";

export type AdminUsuario = {
  id: string;
  email: string;
  rol: "super_admin" | "admin_organismo";
  organismo: string | null;
  activo: boolean;
};

export type UsuarioFormValores = {
  email: string;
  password: string;
  rol: "super_admin" | "admin_organismo";
  organismo_id: number | null;
  activo: boolean;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parsearOLanzar<T>(respuesta: Response, mensajePorDefecto: string): Promise<T> {
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => null);
    throw new Error(cuerpo?.detail ?? mensajePorDefecto);
  }
  return respuesta.json();
}

export async function obtenerUsuarios(): Promise<AdminUsuario[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/usuarios`, { credentials: "include" });
  return parsearOLanzar(respuesta, "No se pudo cargar la lista de usuarios");
}

export async function crearUsuario(datos: UsuarioFormValores): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/admin/usuarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(datos),
  });
  await parsearOLanzar(respuesta, "No se pudo crear el usuario");
}

export async function editarUsuario(id: string, datos: UsuarioFormValores): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/admin/usuarios/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      rol: datos.rol,
      organismo_id: datos.organismo_id,
      activo: datos.activo,
      password: datos.password || null,
    }),
  });
  await parsearOLanzar(respuesta, "No se pudo editar el usuario");
}

export async function crearOrganismo(nombre: string): Promise<Organismo> {
  const respuesta = await fetch(`${BASE_URL}/admin/organismos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ nombre }),
  });
  return parsearOLanzar(respuesta, "No se pudo crear el organismo");
}
