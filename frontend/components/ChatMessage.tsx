import type { Mensaje } from "../hooks/useChatStream";
import { BurbujaMensaje } from "./BurbujaMensaje";
import { FeedbackRespuesta } from "./FeedbackRespuesta";

export function ChatMessage({
  mensaje,
  sessionId,
  mostrarFeedback,
  onReintentar,
  onPedirContacto,
}: {
  mensaje: Mensaje;
  sessionId: string;
  mostrarFeedback: boolean;
  onReintentar?: () => void;
  onPedirContacto?: () => void;
}) {
  const esUsuario = mensaje.rol === "user";

  return (
    <BurbujaMensaje
      esUsuario={esUsuario}
      className={mensaje.error ? "border border-red-500 dark:border-red-400" : ""}
    >
      <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
      {mensaje.fuentes && mensaje.fuentes.length > 0 && (
        <ul className="mt-2 border-t border-gray-300 pt-2 text-sm dark:border-white/20">
          {mensaje.fuentes.map((fuente) => (
            <li key={fuente.tramite_id}>
              {fuente.fuente_url ? (
                <a
                  href={fuente.fuente_url}
                  target="_blank"
                  rel="noreferrer"
                  className="boton-secundario"
                >
                  {fuente.nombre_oficial}
                </a>
              ) : (
                fuente.nombre_oficial
              )}
            </li>
          ))}
        </ul>
      )}
      {mensaje.sugerirContacto && onPedirContacto && (
        <button onClick={onPedirContacto} className="boton-secundario mt-2 block">
          ¿Querés que te ayude una persona? Completá este formulario
        </button>
      )}
      {mostrarFeedback &&
        !esUsuario &&
        !mensaje.error &&
        mensaje.votable &&
        mensaje.id &&
        mensaje.contenido && (
          <FeedbackRespuesta
            sessionId={sessionId}
            mensajeId={mensaje.id}
            feedbackInicial={mensaje.feedback}
          />
        )}
      {mensaje.error && onReintentar && (
        <button onClick={onReintentar} className="texto-error mt-2 text-sm underline">
          Reintentar
        </button>
      )}
    </BurbujaMensaje>
  );
}
