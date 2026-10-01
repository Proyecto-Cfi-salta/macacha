import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  MAX_COMENTARIO,
  MOTIVOS,
  estadoInicialFeedback,
  textoMotivo,
} from "./feedback";

describe("MOTIVOS", () => {
  it("coincide en valores y orden con la lista cerrada del backend", () => {
    const fuente = readFileSync(
      new URL("../../backend/agent/feedback.py", import.meta.url),
      "utf8"
    );
    const bloque = fuente.match(/MOTIVOS\s*=\s*\(([\s\S]*?)\)/)?.[1] ?? "";
    const valoresBackend = [...bloque.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);

    expect(valoresBackend.length).toBeGreaterThan(0);
    expect(MOTIVOS.map((m) => m.valor)).toEqual(valoresBackend);
  });

  it("tiene los textos de la interfaz", () => {
    expect(MOTIVOS.map((m) => m.texto)).toEqual([
      "No respondió mi pregunta",
      "La información era incorrecta",
      "Faltaba información",
      "Me mostró otro trámite",
      "La información estaba desactualizada",
      "La respuesta no fue clara",
      "Otro",
    ]);
  });

  it("el límite de comentario es 500", () => {
    expect(MAX_COMENTARIO).toBe(500);
  });
});

describe("estadoInicialFeedback", () => {
  it("sin voto pregunta", () => {
    expect(estadoInicialFeedback(null)).toBe("pregunta");
    expect(estadoInicialFeedback(undefined)).toBe("pregunta");
  });

  it("voto positivo agradece", () => {
    expect(estadoInicialFeedback({ util: true, motivo: null, comentario: null })).toBe("gracias_si");
  });

  it("voto negativo con motivo agradece el comentario", () => {
    expect(estadoInicialFeedback({ util: false, motivo: "otro", comentario: null })).toBe("gracias_no");
  });

  it("voto negativo con comentario agradece el comentario", () => {
    expect(estadoInicialFeedback({ util: false, motivo: null, comentario: "mal" })).toBe("gracias_no");
  });

  it("voto negativo sin motivo ni comentario reabre el detalle", () => {
    expect(estadoInicialFeedback({ util: false, motivo: null, comentario: null })).toBe("detalle");
  });
});

describe("textoMotivo", () => {
  it("devuelve el texto del motivo", () => {
    expect(textoMotivo("faltaba_info")).toBe("Faltaba información");
  });

  it("devuelve cadena vacía para null o desconocido", () => {
    expect(textoMotivo(null)).toBe("");
    expect(textoMotivo("inventado")).toBe("");
  });
});
