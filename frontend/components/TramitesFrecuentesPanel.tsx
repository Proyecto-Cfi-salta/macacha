import type { TramiteFrecuente } from "../lib/api";

export function TramitesFrecuentesPanel({
  tramites,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  tramites: TramiteFrecuente[];
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  if (tramites.length === 0) {
    return (
      <p className="text-sm text-gray-400">
        Los trámites más consultados van a aparecer acá.
      </p>
    );
  }

  return (
    <div>
      <h2 className="font-semibold">Más consultados</h2>
      <ol className="mt-2 space-y-2 text-sm">
        {tramites.map((tramite, indice) => (
          <li key={tramite.tramite_id}>
            <button
              type="button"
              onClick={() => onPreguntar(`Quiero información sobre ${tramite.nombre_oficial}.`)}
              disabled={preguntarDeshabilitado}
              className="flex w-full justify-between gap-2 rounded p-1 text-left hover:bg-gray-50 disabled:opacity-50"
            >
              <span>
                {indice + 1}. {tramite.nombre_oficial}
              </span>
              <span className="text-gray-400">{tramite.veces_consultado}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
