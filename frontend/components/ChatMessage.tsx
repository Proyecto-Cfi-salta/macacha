import type { Mensaje } from "../hooks/useChatStream";
import { BurbujaMensaje } from "./BurbujaMensaje";

export function ChatMessage({
  mensaje,
  onReintentar,
}: {
  mensaje: Mensaje;
  onReintentar?: () => void;
}) {
  const esUsuario = mensaje.rol === "user";

  return (
    <BurbujaMensaje esUsuario={esUsuario} className={mensaje.error ? "border border-red-500" : ""}>
      <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
      {mensaje.fuentes && mensaje.fuentes.length > 0 && (
        <ul className="mt-2 border-t border-gray-300 pt-2 text-sm">
          {mensaje.fuentes.map((fuente) => (
            <li key={fuente.tramite_id}>
              {fuente.fuente_url ? (
                <a
                  href={fuente.fuente_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 underline"
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
      {mensaje.error && onReintentar && (
        <button
          onClick={onReintentar}
          className="mt-2 text-sm text-red-700 underline"
        >
          Reintentar
        </button>
      )}
    </BurbujaMensaje>
  );
}
