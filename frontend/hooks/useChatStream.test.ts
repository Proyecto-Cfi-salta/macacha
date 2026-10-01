import { describe, expect, it } from "vitest";
import { aplicarEventoSSE, parsearLineasSSE, type Mensaje } from "./useChatStream";

describe("parsearLineasSSE", () => {
  it("parsea múltiples eventos de tipo texto", () => {
    const bloque =
      'data: {"tipo":"texto","delta":"Hola "}\n\ndata: {"tipo":"texto","delta":"mundo"}';

    expect(parsearLineasSSE(bloque)).toEqual([
      { tipo: "texto", delta: "Hola " },
      { tipo: "texto", delta: "mundo" },
    ]);
  });

  it("parsea un evento de fin con fuentes y candidatos ambiguos vacíos", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[{"tramite_id":"RC-0001","nombre_oficial":"Actas Regulares","fuente_url":"https://x"}],"candidatos_ambiguos":[],"sugerir_contacto":false}';

    expect(parsearLineasSSE(bloque)).toEqual([
      {
        tipo: "fin",
        fuentes: [
          {
            tramite_id: "RC-0001",
            nombre_oficial: "Actas Regulares",
            fuente_url: "https://x",
          },
        ],
        candidatos_ambiguos: [],
        sugerir_contacto: false,
      },
    ]);
  });

  it("parsea un evento de fin con candidatos ambiguos", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[],"candidatos_ambiguos":[{"tramite_id":"TR-0002","nombre_oficial":"Denuncia laboral","descripcion":"Reclamos laborales."}],"sugerir_contacto":false}';

    expect(parsearLineasSSE(bloque)).toEqual([
      {
        tipo: "fin",
        fuentes: [],
        candidatos_ambiguos: [
          {
            tramite_id: "TR-0002",
            nombre_oficial: "Denuncia laboral",
            descripcion: "Reclamos laborales.",
          },
        ],
        sugerir_contacto: false,
      },
    ]);
  });

  it("parsea un evento de fin que sugiere contacto humano", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[],"candidatos_ambiguos":[],"sugerir_contacto":true}';

    expect(parsearLineasSSE(bloque)).toEqual([
      { tipo: "fin", fuentes: [], candidatos_ambiguos: [], sugerir_contacto: true },
    ]);
  });

  it("parsea un evento de error", () => {
    const bloque =
      'data: {"tipo":"error","mensaje":"Ocurrió un error al procesar tu mensaje."}';

    expect(parsearLineasSSE(bloque)).toEqual([
      { tipo: "error", mensaje: "Ocurrió un error al procesar tu mensaje." },
    ]);
  });

  it("ignora bloques vacíos", () => {
    expect(parsearLineasSSE("")).toEqual([]);
  });
});


describe("aplicarEventoSSE", () => {
  const base: Mensaje[] = [
    { rol: "user", contenido: "hola" },
    { rol: "assistant", contenido: "" },
  ];

  it("fin asigna el id y marca la respuesta como votable", () => {
    const resultado = aplicarEventoSSE(base, {
      tipo: "fin",
      fuentes: [],
      candidatos_ambiguos: [],
      sugerir_contacto: false,
      mensaje_id: "abc-123",
    });

    expect(resultado[1].id).toBe("abc-123");
    expect(resultado[1].votable).toBe(true);
  });

  it("error no asigna id ni votable", () => {
    const resultado = aplicarEventoSSE(base, { tipo: "error", mensaje: "falló" });

    expect(resultado[1].error).toBe(true);
    expect(resultado[1].id).toBeUndefined();
    expect(resultado[1].votable).toBeUndefined();
  });

  it("texto acumula el delta sin tocar el id", () => {
    const resultado = aplicarEventoSSE(base, { tipo: "texto", delta: "Hola" });

    expect(resultado[1].contenido).toBe("Hola");
    expect(resultado[1].id).toBeUndefined();
  });

  it("no muta el arreglo original", () => {
    aplicarEventoSSE(base, { tipo: "texto", delta: "Hola" });

    expect(base[1].contenido).toBe("");
  });
});
