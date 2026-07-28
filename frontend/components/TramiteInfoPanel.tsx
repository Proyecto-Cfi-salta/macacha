import type { TramiteDetalle } from "../lib/api";

export function TramiteInfoPanel({ tramite }: { tramite: TramiteDetalle | null }) {
  if (!tramite) {
    return (
      <p className="text-sm text-gray-400">
        La info del trámite va a aparecer acá.
      </p>
    );
  }

  return (
    <div>
      <h2 className="font-semibold">{tramite.nombre_oficial}</h2>
      <p className="text-sm text-gray-500">{tramite.organismo}</p>

      {tramite.requisitos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Requisitos</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {tramite.requisitos.map((requisito) => (
              <li key={requisito}>{requisito}</li>
            ))}
          </ul>
        </div>
      )}

      {(tramite.costo || tramite.modalidad || tramite.duracion) && (
        <div className="mt-4 text-sm">
          <h3 className="font-medium">Costo, modalidad y duración</h3>
          {tramite.costo && <p>Costo: {tramite.costo}</p>}
          {tramite.modalidad && <p>Modalidad: {tramite.modalidad}</p>}
          {tramite.duracion && <p>Duración: {tramite.duracion}</p>}
        </div>
      )}

      {tramite.pasos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Pasos</h3>
          <ol className="mt-1 list-decimal pl-5 text-sm">
            {tramite.pasos.map((paso) => (
              <li key={paso}>{paso}</li>
            ))}
          </ol>
        </div>
      )}

      {tramite.enlaces_oficiales.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Enlaces oficiales</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {tramite.enlaces_oficiales.map((enlace) => (
              <li key={enlace}>
                <a
                  href={enlace}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 underline"
                >
                  {enlace}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 text-sm">
        <h3 className="font-medium">Contacto</h3>
        {tramite.telefono_contacto && <p>Tel: {tramite.telefono_contacto}</p>}
        {tramite.email_contacto && <p>Mail: {tramite.email_contacto}</p>}
        {!tramite.telefono_contacto && !tramite.email_contacto && (
          <p className="text-gray-400">Sin datos de contacto.</p>
        )}
      </div>
    </div>
  );
}
