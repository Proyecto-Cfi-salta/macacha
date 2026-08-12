import type { Mensaje } from "../hooks/useChatStream";

export type TramiteCitado = { tramite_id: string; nombre_oficial: string };

export function tramitesCitadosEnConversacion(mensajes: Mensaje[]): TramiteCitado[] {
  const vistos = new Map<string, string>();
  for (const mensaje of mensajes) {
    for (const fuente of mensaje.fuentes ?? []) {
      if (!vistos.has(fuente.tramite_id)) {
        vistos.set(fuente.tramite_id, fuente.nombre_oficial);
      }
    }
  }
  return [...vistos.entries()].map(([tramite_id, nombre_oficial]) => ({
    tramite_id,
    nombre_oficial,
  }));
}
