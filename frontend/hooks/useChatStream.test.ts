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

  it("parsea un evento de fin con fuentes", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[{"tramite_id":"RC-0001","nombre_oficial":"Actas Regulares","fuente_url":"https://x"}]}';

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
      },
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
