"use client";

import type { CandidatoAmbiguo } from "../hooks/useChatStream";

export function TramitesAmbiguosPanel({
  candidatos,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  candidatos: CandidatoAmbiguo[];
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  return (
    <div>
      <h2 className="font-semibold">¿Cuál de estos trámites te interesa?</h2>
      <ul className="mt-2 space-y-3">
        {candidatos.map((candidato) => (
          <li key={candidato.tramite_id}>
            <button
              type="button"
              onClick={() => onPreguntar(`Quiero información sobre ${candidato.nombre_oficial}.`)}
              disabled={preguntarDeshabilitado}
              className="w-full rounded border border-gray-200 p-2 text-left text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              <span className="font-medium">{candidato.nombre_oficial}</span>
              <p className="mt-1 text-gray-500">{candidato.descripcion}</p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
