import { describe, expect, it } from "vitest";
import { obtenerUltimoTramiteId } from "./useTramiteActual";
import type { Mensaje } from "./useChatStream";

describe("obtenerUltimoTramiteId", () => {
  it("devuelve null si ningún mensaje tiene fuentes", () => {
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "hola" },
      { rol: "assistant", contenido: "hola, en qué te ayudo?" },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBeNull();
  });

  it("devuelve el tramite_id de la última fuente del último mensaje con fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null },
        ],
      },
      { rol: "user", contenido: "y para otro trámite?" },
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0002", nombre_oficial: "Otro trámite", fuente_url: null },
        ],
      },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBe("RC-0002");
  });

  it("dentro de un mismo mensaje, toma el último tramite_id de la lista de fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null },
          { tramite_id: "RC-0003", nombre_oficial: "Otro trámite más", fuente_url: null },
        ],
      },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBe("RC-0003");
  });

  it("ignora mensajes con fuentes vacías y usa el último no vacío", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
      { rol: "assistant", contenido: "no encontré nada", fuentes: [] },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBe("RC-0001");
  });
});
