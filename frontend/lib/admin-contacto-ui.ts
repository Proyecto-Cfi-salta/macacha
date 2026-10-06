import type { SolicitudContacto } from "./admin-contacto-api";

export function quienResolvio(
  solicitud: Pick<SolicitudContacto, "estado" | "resuelto_por">
): string | null {
  if (solicitud.estado !== "resuelto") return null;
  return solicitud.resuelto_por ?? "Sin registro";
}
