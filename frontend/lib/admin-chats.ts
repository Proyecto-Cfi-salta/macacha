import type { MensajeAdmin, ToolCall } from "./admin-api";

export type DetalleToolCall = {
  id: string;
  nombre: string;
  argumentos: string;
  resultado: string | null;
};

export function extraerDetalleToolCalls(
  mensajeAssistant: MensajeAdmin,
  todosLosMensajes: MensajeAdmin[]
): DetalleToolCall[] {
  const toolCalls = mensajeAssistant.tool_calls ?? [];
  return toolCalls.map((toolCall: ToolCall) => {
    const mensajeResultado = todosLosMensajes.find(
      (mensaje) => mensaje.rol === "tool" && mensaje.tool_call_id === toolCall.id
    );
    return {
      id: toolCall.id,
      nombre: toolCall.function.name,
      argumentos: toolCall.function.arguments,
      resultado: mensajeResultado?.contenido ?? null,
    };
  });
}

export function etiquetaProveedor(proveedor: string): string {
  if (proveedor === "gemini") return "Gemini";
  const prueba = /^evaluacion-(veredicto-)?(.+)$/.exec(proveedor);
  if (prueba) return `${prueba[1] ? "Verificación" : "Prueba"} · ${prueba[2]}`;
  return "OpenAI";
}
