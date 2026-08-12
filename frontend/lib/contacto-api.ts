export type SolicitudContactoInput = {
  session_id: string;
  tramite_id: string | null;
  nombre: string;
  email: string;
  telefono: string;
  consulta: string;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function enviarSolicitudContacto(datos: SolicitudContactoInput): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/contacto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo enviar la consulta");
  }
}
