import { describe, expect, it } from "vitest";
import { anchoBarra, formatearPorcentaje } from "./feedback-metricas";

describe("formatearPorcentaje", () => {
  it("devuelve guion cuando no hay votos", () => {
    expect(formatearPorcentaje(null)).toBe("—");
  });

  it("usa coma decimal y un decimal", () => {
    expect(formatearPorcentaje(75)).toBe("75,0%");
    expect(formatearPorcentaje(33.3)).toBe("33,3%");
  });

  it("nunca devuelve NaN", () => {
    expect(formatearPorcentaje(0)).toBe("0,0%");
    expect(formatearPorcentaje(Number.NaN)).toBe("—");
  });
});

describe("anchoBarra", () => {
  it("calcula el porcentaje respecto del máximo", () => {
    expect(anchoBarra(5, 10)).toBe(50);
    expect(anchoBarra(10, 10)).toBe(100);
  });

  it("devuelve 0 si el máximo es 0", () => {
    expect(anchoBarra(0, 0)).toBe(0);
  });

  it("redondea al entero más cercano", () => {
    expect(anchoBarra(1, 3)).toBe(33);
  });
});
