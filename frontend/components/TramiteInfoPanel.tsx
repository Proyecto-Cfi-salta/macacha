"use client";

import type { TramiteDetalle } from "../lib/api";
import { CopyButton } from "./CopyButton";
import { useChecklist } from "../hooks/useChecklist";

export function TramiteInfoPanel({
  tramite,
  onPreguntar,
  preguntarDeshabilitado,
}: {
  tramite: TramiteDetalle | null;
  onPreguntar: (mensaje: string) => void;
  preguntarDeshabilitado: boolean;
}) {
  const { estaTildado, toggle } = useChecklist(tramite?.tramite_id ?? null);

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
          <ul className="mt-1 space-y-1 text-sm">
            {tramite.requisitos.map((requisito, indice) => (
              <li key={requisito} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={estaTildado("requisito", indice)}
                  onChange={() => toggle("requisito", indice)}
                  aria-label={`Marcar requisito: ${requisito}`}
                />
                <span
                  className={
                    estaTildado("requisito", indice)
                      ? "flex-1 line-through text-gray-400"
                      : "flex-1"
                  }
                >
                  {requisito}
                </span>
                <CopyButton texto={requisito} />
              </li>
            ))}
          </ul>
          <BotonDuda
            texto={`Tengo una duda sobre los requisitos de ${tramite.nombre_oficial}.`}
            onPreguntar={onPreguntar}
            disabled={preguntarDeshabilitado}
          />
        </div>
      )}

      {(tramite.costo || tramite.modalidad || tramite.duracion) && (
        <div className="mt-4 text-sm">
          <h3 className="font-medium">Costo, modalidad y duración</h3>
          {tramite.costo && <p>Costo: {tramite.costo}</p>}
          {tramite.modalidad && <p>Modalidad: {tramite.modalidad}</p>}
          {tramite.duracion && <p>Duración: {tramite.duracion}</p>}
          <BotonDuda
            texto={`Tengo una duda sobre el costo, la modalidad o la duración de ${tramite.nombre_oficial}.`}
            onPreguntar={onPreguntar}
            disabled={preguntarDeshabilitado}
          />
        </div>
      )}

      {tramite.pasos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Pasos</h3>
          <ol className="mt-1 space-y-1 text-sm">
            {tramite.pasos.map((paso, indice) => (
              <li key={paso} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={estaTildado("paso", indice)}
                  onChange={() => toggle("paso", indice)}
                  aria-label={`Marcar paso: ${paso}`}
                />
                <span
                  className={
                    estaTildado("paso", indice)
                      ? "flex-1 line-through text-gray-400"
                      : "flex-1"
                  }
                >
                  {paso}
                </span>
                <CopyButton texto={paso} />
              </li>
            ))}
          </ol>
          <BotonDuda
            texto={`Tengo una duda sobre los pasos de ${tramite.nombre_oficial}.`}
            onPreguntar={onPreguntar}
            disabled={preguntarDeshabilitado}
          />
        </div>
      )}

      {tramite.enlaces_oficiales.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Enlaces oficiales</h3>
          <div className="mt-1 flex flex-col gap-2">
            {tramite.enlaces_oficiales.map((enlace) => (
              <a
                key={enlace}
                href={enlace}
                target="_blank"
                rel="noreferrer"
                className="rounded border border-blue-600 px-3 py-1.5 text-center text-sm text-blue-700 hover:bg-blue-50"
              >
                {enlace}
              </a>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 text-sm">
        <h3 className="font-medium">Contacto</h3>
        {tramite.telefono_contacto && (
          <p>
            Tel: {tramite.telefono_contacto}
            <CopyButton texto={tramite.telefono_contacto} />
          </p>
        )}
        {tramite.email_contacto && (
          <p>
            Mail: {tramite.email_contacto}
            <CopyButton texto={tramite.email_contacto} />
          </p>
        )}
        {!tramite.telefono_contacto && !tramite.email_contacto && (
          <p className="text-gray-400">Sin datos de contacto.</p>
        )}
      </div>
    </div>
  );
}

function BotonDuda({
  texto,
  onPreguntar,
  disabled,
}: {
  texto: string;
  onPreguntar: (mensaje: string) => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onPreguntar(texto)}
      disabled={disabled}
      className="mt-2 text-xs text-blue-700 underline disabled:opacity-50"
    >
      ¿Tenés dudas sobre esto?
    </button>
  );
}
