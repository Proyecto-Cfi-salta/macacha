import { describe, expect, it } from "vitest";
import { claveChecklist, claveItem, toggleItem } from "./useChecklist";

describe("claveChecklist", () => {
  it("arma la clave de localStorage a partir del tramite_id", () => {
    expect(claveChecklist("RC-0004")).toBe("macacha_checklist_RC-0004");
  });
});

describe("claveItem", () => {
  it("arma la clave de un requisito por índice", () => {
    expect(claveItem("requisito", 0)).toBe("requisito:0");
  });

  it("arma la clave de un paso por índice", () => {
    expect(claveItem("paso", 2)).toBe("paso:2");
  });
});

describe("toggleItem", () => {
  it("prende una clave que no estaba en el estado", () => {
    expect(toggleItem({}, "requisito:0")).toEqual({ "requisito:0": true });
  });

  it("apaga una clave que estaba prendida", () => {
    expect(toggleItem({ "requisito:0": true }, "requisito:0")).toEqual({
      "requisito:0": false,
    });
  });

  it("no afecta otras claves del estado", () => {
    const estado = { "requisito:0": true, "paso:1": true };
    expect(toggleItem(estado, "requisito:0")).toEqual({
      "requisito:0": false,
      "paso:1": true,
    });
  });
});
