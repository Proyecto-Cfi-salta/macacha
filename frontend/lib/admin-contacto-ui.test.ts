import { describe, expect, it } from "vitest";
import { quienResolvio } from "./admin-contacto-ui";

describe("quienResolvio", () => {
  it("muestra el email de quien resolvió", () => {
    expect(quienResolvio({ estado: "resuelto", resuelto_por: "ana@gob.ar" })).toBe("ana@gob.ar");
  });

  it("no muestra nada si la solicitud está pendiente", () => {
    expect(quienResolvio({ estado: "pendiente", resuelto_por: null })).toBeNull();
  });

  it("avisa que no hay registro si se resolvió antes de guardar quién", () => {
    expect(quienResolvio({ estado: "resuelto", resuelto_por: null })).toBe("Sin registro");
  });
});
