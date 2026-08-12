import { describe, expect, it } from "vitest";
import { tramitesCitadosEnConversacion } from "./contacto-tramites";
import type { Mensaje } from "../hooks/useChatStream";

describe("tramitesCitadosEnConversacion", () => {
  it("devuelve lista vacía si ningún mensaje citó trámites", () => {
    const mensajes: Mensaje[] = [{ rol: "assistant", contenido: "Hola" }];
    expect(tramitesCitadosEnConversacion(mensajes)).toEqual([]);
  });

  it("devuelve un único trámite citado", () => {
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "qué necesito para un acta" },
      {
        rol: "assistant",
        contenido: "Necesitás tu DNI.",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
    ];
    expect(tramitesCitadosEnConversacion(mensajes)).toEqual([
      { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares" },
    ]);
  });

  it("deduplica trámites citados en más de un mensaje, en orden de primera aparición", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "primero",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Acta A", fuente_url: null }],
      },
      {
        rol: "assistant",
        contenido: "segundo",
        fuentes: [
          { tramite_id: "RC-0002", nombre_oficial: "Acta B", fuente_url: null },
          { tramite_id: "RC-0001", nombre_oficial: "Acta A", fuente_url: null },
        ],
      },
    ];
    expect(tramitesCitadosEnConversacion(mensajes)).toEqual([
      { tramite_id: "RC-0001", nombre_oficial: "Acta A" },
      { tramite_id: "RC-0002", nombre_oficial: "Acta B" },
    ]);
  });
});
