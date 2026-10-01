import { describe, expect, it } from "vitest";
import { puedeGuardarTramite } from "./tramite-form";

const organismos = ["Registro Civil", "Secretaría de Trabajo"];

describe("puedeGuardarTramite", () => {
  it("permite guardar con un organismo existente y nombre oficial", () => {
    expect(
      puedeGuardarTramite({ organismo: "Registro Civil", nombreOficial: "Actas", organismosExistentes: organismos })
    ).toBe(true);
  });

  it("no permite guardar con un organismo que no está en la lista", () => {
    expect(
      puedeGuardarTramite({ organismo: "Organismo Nuevo", nombreOficial: "Actas", organismosExistentes: organismos })
    ).toBe(false);
  });

  it("no permite guardar sin haber elegido organismo", () => {
    expect(
      puedeGuardarTramite({ organismo: "", nombreOficial: "Actas", organismosExistentes: organismos })
    ).toBe(false);
  });

  it("no permite guardar sin nombre oficial", () => {
    expect(
      puedeGuardarTramite({ organismo: "Registro Civil", nombreOficial: "   ", organismosExistentes: organismos })
    ).toBe(false);
  });

  it("distingue mayúsculas: el nombre debe coincidir exactamente", () => {
    expect(
      puedeGuardarTramite({ organismo: "registro civil", nombreOficial: "Actas", organismosExistentes: organismos })
    ).toBe(false);
  });
});
