import { describe, expect, it } from "vitest";
import {
  MAX_LONGITUD_EMAIL,
  normalizarEmailContacto,
  textoCasillaGuardada,
} from "./email-contacto";

describe("normalizarEmailContacto", () => {
  it("vacío o solo espacios devuelve null, no cadena vacía", () => {
    for (const valor of ["", "   ", "\n\t "]) {
      expect(normalizarEmailContacto(valor)).toEqual({ ok: true, email: null });
    }
  });

  it("recorta los espacios alrededor", () => {
    expect(normalizarEmailContacto("  mesa@salta.gob.ar \n")).toEqual({
      ok: true,
      email: "mesa@salta.gob.ar",
    });
  });

  it("acepta emails válidos", () => {
    for (const valor of ["mesa@salta.gob.ar", "a@b.co", "nombre.apellido+tag@dominio.com.ar"]) {
      expect(normalizarEmailContacto(valor)).toEqual({ ok: true, email: valor });
    }
  });

  it("rechaza emails con forma inválida", () => {
    for (const valor of ["sin-arroba", "a@b", "a b@c.com", "a@@b.com", "@x.com", "a@", "a@x .com"]) {
      const resultado = normalizarEmailContacto(valor);
      expect(resultado.ok).toBe(false);
    }
  });

  it("acepta exactamente el largo máximo y rechaza uno más", () => {
    const sufijo = "@x.co";
    const justo = "a".repeat(MAX_LONGITUD_EMAIL - sufijo.length) + sufijo;
    expect(normalizarEmailContacto(justo)).toEqual({ ok: true, email: justo });
    expect(normalizarEmailContacto("a" + justo).ok).toBe(false);
  });

  it("el mensaje de error está en español", () => {
    expect(normalizarEmailContacto("nope")).toEqual({
      ok: false,
      mensaje: "Ingresá un email válido, por ejemplo mesa@organismo.gob.ar",
    });
  });
});

describe("textoCasillaGuardada", () => {
  it("avisa que se guardó cuando hay email", () => {
    expect(textoCasillaGuardada("mesa@x.com")).toBe("Casilla guardada.");
  });

  it("avisa que se quitó cuando no hay email", () => {
    expect(textoCasillaGuardada(null)).toBe("Se quitó la casilla.");
  });
});
