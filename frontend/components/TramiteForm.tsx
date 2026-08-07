"use client";

import { useState, type FormEvent } from "react";
import { ListaFAQ } from "./ListaFAQ";
import { ListaTextos } from "./ListaTextos";
import type { Organismo, TramiteDetalleAdmin } from "../lib/admin-tramites-api";

export function TramiteForm({
  valoresIniciales,
  organismosExistentes,
  organismoFijo,
  guardando,
  error,
  onGuardar,
}: {
  valoresIniciales: TramiteDetalleAdmin;
  organismosExistentes: Organismo[];
  organismoFijo?: string;
  guardando: boolean;
  error: string | null;
  onGuardar: (datos: TramiteDetalleAdmin) => void;
}) {
  const [datos, setDatos] = useState<TramiteDetalleAdmin>(
    organismoFijo ? { ...valoresIniciales, organismo: organismoFijo } : valoresIniciales
  );
  const [organismoEsNuevo, setOrganismoEsNuevo] = useState(
    !organismosExistentes.some((o) => o.nombre === valoresIniciales.organismo)
  );

  function actualizar<K extends keyof TramiteDetalleAdmin>(campo: K, valor: TramiteDetalleAdmin[K]) {
    setDatos((anterior) => ({ ...anterior, [campo]: valor }));
  }

  function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    onGuardar(datos);
  }

  const puedeGuardar = datos.organismo.trim() !== "" && datos.nombre_oficial.trim() !== "";

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-4 p-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Organismo</label>
        {organismoFijo ? (
          <input
            type="text"
            value={organismoFijo}
            disabled
            className="w-full rounded border border-gray-300 bg-gray-100 px-2 py-1 text-sm text-gray-500"
          />
        ) : organismoEsNuevo ? (
          <input
            type="text"
            value={datos.organismo}
            onChange={(e) => actualizar("organismo", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        ) : (
          <select
            value={datos.organismo}
            onChange={(e) => actualizar("organismo", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {organismosExistentes.map((organismo) => (
              <option key={organismo.id} value={organismo.nombre}>
                {organismo.nombre}
              </option>
            ))}
          </select>
        )}
        {!organismoFijo && (
          <button
            type="button"
            onClick={() => setOrganismoEsNuevo(!organismoEsNuevo)}
            className="mt-1 text-sm text-blue-700 underline"
          >
            {organismoEsNuevo ? "Elegir uno existente" : "Otro… (crear nuevo)"}
          </button>
        )}
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Categoría</label>
        <input
          type="text"
          value={datos.categoria}
          onChange={(e) => actualizar("categoria", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Nombre oficial</label>
        <input
          type="text"
          value={datos.nombre_oficial}
          onChange={(e) => actualizar("nombre_oficial", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Descripción</label>
        <textarea
          value={datos.descripcion}
          onChange={(e) => actualizar("descripcion", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Objetivo</label>
        <textarea
          value={datos.objetivo}
          onChange={(e) => actualizar("objetivo", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <ListaTextos
        etiqueta="Requisitos"
        valores={datos.requisitos}
        onChange={(v) => actualizar("requisitos", v)}
      />
      <ListaTextos etiqueta="Pasos" valores={datos.pasos} onChange={(v) => actualizar("pasos", v)} />

      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="mb-1 block text-sm font-medium">Costo</label>
          <input
            type="text"
            value={datos.costo}
            onChange={(e) => actualizar("costo", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Modalidad</label>
          <input
            type="text"
            value={datos.modalidad}
            onChange={(e) => actualizar("modalidad", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Duración</label>
          <input
            type="text"
            value={datos.duracion}
            onChange={(e) => actualizar("duracion", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-sm font-medium">Teléfono de contacto</label>
          <input
            type="text"
            value={datos.telefono_contacto}
            onChange={(e) => actualizar("telefono_contacto", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Email de contacto</label>
          <input
            type="text"
            value={datos.email_contacto}
            onChange={(e) => actualizar("email_contacto", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
      </div>

      <ListaTextos
        etiqueta="Problemas frecuentes"
        valores={datos.problemas_frecuentes}
        onChange={(v) => actualizar("problemas_frecuentes", v)}
      />
      <ListaTextos
        etiqueta="Sinónimos"
        valores={datos.sinonimos}
        onChange={(v) => actualizar("sinonimos", v)}
      />
      <ListaTextos
        etiqueta="Keywords"
        valores={datos.keywords}
        onChange={(v) => actualizar("keywords", v)}
      />
      <ListaTextos
        etiqueta="Enlaces oficiales"
        valores={datos.enlaces_oficiales}
        onChange={(v) => actualizar("enlaces_oficiales", v)}
      />
      <ListaFAQ
        valores={datos.preguntas_frecuentes}
        onChange={(v) => actualizar("preguntas_frecuentes", v)}
      />

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={!puedeGuardar || guardando}
        className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
      >
        {guardando ? "Guardando…" : "Guardar"}
      </button>
    </form>
  );
}
