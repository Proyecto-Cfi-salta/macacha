import { describe, expect, it } from "vitest";
import { etiquetaVerContrasena, tipoCampoContrasena } from "./contrasena";

describe("tipoCampoContrasena", () => {
  it("oculta la contraseña por defecto", () => {
    expect(tipoCampoContrasena(false)).toBe("password");
  });

  it("muestra el texto cuando está visible", () => {
    expect(tipoCampoContrasena(true)).toBe("text");
  });
});

describe("etiquetaVerContrasena", () => {
  it("ofrece mostrar cuando está oculta", () => {
    expect(etiquetaVerContrasena(false)).toBe("Mostrar contraseña");
  });

  it("ofrece ocultar cuando está visible", () => {
    expect(etiquetaVerContrasena(true)).toBe("Ocultar contraseña");
  });
});
