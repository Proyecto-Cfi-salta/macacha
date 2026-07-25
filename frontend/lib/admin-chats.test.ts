import { describe, expect, it } from "vitest";
import { extraerDetalleToolCalls } from "./admin-chats";
import type { MensajeAdmin } from "./admin-api";

describe("extraerDetalleToolCalls", () => {
  it("devuelve lista vacía si el mensaje no tiene tool_calls", () => {
    const mensaje: MensajeAdmin = { rol: "assistant", contenido: "hola", creado_en: "" };
    expect(extraerDetalleToolCalls(mensaje, [mensaje])).toEqual([]);
  });

  it("empareja un tool call con el resultado del mensaje tool correspondiente", () => {
    const mensajeAssistant: MensajeAdmin = {
      rol: "assistant",
      contenido: null,
      creado_en: "",
      tool_calls: [
        {
          id: "call_1",
          type: "function",
          function: { name: "obtener_requisitos", arguments: '{"tramite_id":"RC-0001"}' },
        },
      ],
    };
    const mensajeTool: MensajeAdmin = {
      rol: "tool",
      contenido: '["DNI"]',
      tool_call_id: "call_1",
      creado_en: "",
    };

    const detalle = extraerDetalleToolCalls(mensajeAssistant, [mensajeAssistant, mensajeTool]);

    expect(detalle).toEqual([
      {
        id: "call_1",
        nombre: "obtener_requisitos",
        argumentos: '{"tramite_id":"RC-0001"}',
        resultado: '["DNI"]',
      },
    ]);
  });

  it("devuelve resultado null si no encuentra el mensaje tool correspondiente", () => {
    const mensajeAssistant: MensajeAdmin = {
      rol: "assistant",
      contenido: null,
      creado_en: "",
      tool_calls: [
        { id: "call_1", type: "function", function: { name: "obtener_requisitos", arguments: "{}" } },
      ],
    };

    const detalle = extraerDetalleToolCalls(mensajeAssistant, [mensajeAssistant]);

    expect(detalle[0].resultado).toBeNull();
  });

  it("empareja varios tool calls del mismo mensaje con sus respectivos resultados", () => {
    const mensajeAssistant: MensajeAdmin = {
      rol: "assistant",
      contenido: null,
      creado_en: "",
      tool_calls: [
        { id: "call_1", type: "function", function: { name: "a", arguments: "{}" } },
        { id: "call_2", type: "function", function: { name: "b", arguments: "{}" } },
      ],
    };
    const toolMsg1: MensajeAdmin = { rol: "tool", contenido: "r1", tool_call_id: "call_1", creado_en: "" };
    const toolMsg2: MensajeAdmin = { rol: "tool", contenido: "r2", tool_call_id: "call_2", creado_en: "" };

    const detalle = extraerDetalleToolCalls(mensajeAssistant, [mensajeAssistant, toolMsg1, toolMsg2]);

    expect(detalle.map((d) => d.resultado)).toEqual(["r1", "r2"]);
  });
});
