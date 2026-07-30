import { describe, expect, it } from "vitest";
import { determinarEstadoRelevante } from "./usePanelTramite";
import type { Mensaje } from "./useChatStream";

describe("determinarEstadoRelevante", () => {
  it("devuelve idle si ningún mensaje tiene fuentes ni candidatos ambiguos", () => {
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "hola" },
      { rol: "assistant", contenido: "hola, en qué te ayudo?" },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "idle" });
  });

  it("devuelve el tramite_id de la última fuente del último mensaje con fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
      { rol: "user", contenido: "y para otro trámite?" },
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0002", nombre_oficial: "Otro trámite", fuente_url: null }],
      },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "RC-0002" });
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
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "RC-0003" });
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
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "RC-0001" });
  });

  it("devuelve los candidatos ambiguos del último mensaje que los tiene", () => {
    const candidatos = [
      {
        tramite_id: "TR-0002",
        nombre_oficial: "Denuncia laboral",
        descripcion: "Reclamos laborales.",
      },
      {
        tramite_id: "DC-0001",
        nombre_oficial: "Denuncia ante Defensa del Consumidor",
        descripcion: "Reclamos de consumo.",
      },
    ];
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "hola como hago una denuncia?" },
      { rol: "assistant", contenido: "...", candidatosAmbiguos: candidatos },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "ambiguo", candidatos });
  });

  it("una vez resuelto a un trámite puntual, ignora la ambigüedad de un mensaje anterior", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        candidatosAmbiguos: [
          {
            tramite_id: "TR-0002",
            nombre_oficial: "Denuncia laboral",
            descripcion: "Reclamos laborales.",
          },
        ],
      },
      { rol: "user", contenido: "la laboral" },
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "TR-0002", nombre_oficial: "Denuncia laboral", fuente_url: null }],
      },
    ];
    expect(determinarEstadoRelevante(mensajes)).toEqual({ tipo: "tramite", tramiteId: "TR-0002" });
  });
});
