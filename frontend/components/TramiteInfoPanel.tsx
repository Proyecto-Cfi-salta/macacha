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
