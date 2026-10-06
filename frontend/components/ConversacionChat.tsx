"use client";

import { useState } from "react";
import type { MensajeAdmin } from "../lib/admin-api";
import { etiquetaProveedor, extraerDetalleToolCalls } from "../lib/admin-chats";
import { textoMotivo, type FeedbackVoto } from "../lib/feedback";
import { BurbujaMensaje } from "./BurbujaMensaje";

export function ConversacionChat({ mensajes }: { mensajes: MensajeAdmin[] }) {
  const visibles = mensajes.filter((m) => m.rol === "user" || m.rol === "assistant");

  return (
    <div className="mx-auto max-w-2xl space-y-3">
      {visibles.map((mensaje, indice) => (
        <BurbujaMensaje key={indice} esUsuario={mensaje.rol === "user"}>
          <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
          {mensaje.rol === "assistant" && mensaje.proveedor && (
            <span className="mt-1 inline-block rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-600">
              {etiquetaProveedor(mensaje.proveedor)}
            </span>
          )}
          {mensaje.rol === "assistant" && mensaje.feedback && (
            <FeedbackAdmin feedback={mensaje.feedback} />
          )}
          {mensaje.rol === "assistant" && mensaje.tool_calls && mensaje.tool_calls.length > 0 && (
            <DetalleTecnico mensaje={mensaje} todosLosMensajes={mensajes} />
          )}
        </BurbujaMensaje>
      ))}
    </div>
  );
}

function DetalleTecnico({
  mensaje,
  todosLosMensajes,
}: {
  mensaje: MensajeAdmin;
  todosLosMensajes: MensajeAdmin[];
}) {
  const [abierto, setAbierto] = useState(false);
  const detalle = extraerDetalleToolCalls(mensaje, todosLosMensajes);

  return (
    <div className="mt-2 border-t border-gray-300 pt-2 text-sm">
      <button onClick={() => setAbierto(!abierto)} className="boton-secundario">
        {abierto ? "Ocultar detalle técnico" : "Ver detalle técnico"}
      </button>
      {abierto && (
        <ul className="mt-2 space-y-2">
          {detalle.map((item) => (
            <li key={item.id} className="rounded bg-white p-2">
              <p className="font-mono text-xs font-semibold">{item.nombre}</p>
              <pre className="whitespace-pre-wrap break-all text-xs">{item.argumentos}</pre>
              <pre className="whitespace-pre-wrap break-all text-xs texto-secundario">
                {item.resultado ?? "(sin resultado)"}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FeedbackAdmin({ feedback }: { feedback: FeedbackVoto }) {
  const motivo = textoMotivo(feedback.motivo);
  return (
    <div className="mt-2 rounded border border-gray-300 bg-white p-2 text-xs">
      <p className="font-semibold">
        {feedback.util ? "👍 Le sirvió" : "👎 No le sirvió"}
        {motivo ? ` · ${motivo}` : ""}
      </p>
      {feedback.comentario && <p className="mt-1 whitespace-pre-wrap">{feedback.comentario}</p>}
    </div>
  );
}
