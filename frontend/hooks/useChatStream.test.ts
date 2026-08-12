import { describe, expect, it } from "vitest";
import { parsearLineasSSE } from "./useChatStream";

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
