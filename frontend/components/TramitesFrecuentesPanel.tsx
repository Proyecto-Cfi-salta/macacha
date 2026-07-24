import type { TramiteFrecuente } from "../lib/api";

export function TramitesFrecuentesPanel({
  tramites,
}: {
  tramites: TramiteFrecuente[];
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
          <li key={tramite.tramite_id} className="flex justify-between gap-2">
            <span>
              {indice + 1}. {tramite.nombre_oficial}
            </span>
            <span className="text-gray-400">{tramite.veces_consultado}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
