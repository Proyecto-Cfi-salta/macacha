"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { TramiteForm } from "../../../../components/TramiteForm";
import {
  editarTramite,
  listarOrganismos,
  obtenerTramiteAdmin,
  type TramiteDetalleAdmin,
} from "../../../../lib/admin-tramites-api";

export default function EditarTramitePage() {
  const params = useParams<{ id: string }>();
  const [organismos, setOrganismos] = useState<string[]>([]);
  const [tramite, setTramite] = useState<TramiteDetalleAdmin | null | undefined>(undefined);
  const [cargandoError, setCargandoError] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [errorGuardado, setErrorGuardado] = useState<string | null>(null);
  const [confirmacion, setConfirmacion] = useState<string | null>(null);

  useEffect(() => {
    cargar();
  }, [params.id]);

  async function cargar() {
    setCargandoError(false);
    setTramite(undefined);
    try {
      const [detalle, listaOrganismos] = await Promise.all([
        obtenerTramiteAdmin(params.id),
        listarOrganismos(),
      ]);
      setTramite(detalle);
      setOrganismos(listaOrganismos);
    } catch {
      setCargandoError(true);
    }
  }

  async function handleGuardar(datos: TramiteDetalleAdmin) {
    setGuardando(true);
    setErrorGuardado(null);
    setConfirmacion(null);
    try {
      const resultado = await editarTramite(params.id, datos);
      setConfirmacion(
        resultado.cambios
          ? `Guardado como versión ${resultado.numero_version}.`
          : "No había cambios para guardar."
      );
    } catch (err) {
      setErrorGuardado(err instanceof Error ? err.message : "No se pudo guardar el trámite");
    } finally {
      setGuardando(false);
    }
  }

  if (cargandoError) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar el trámite</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (tramite === undefined) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (tramite === null) {
    return <p className="p-4 text-sm text-gray-600">Trámite no encontrado</p>;
  }

  return (
    <div>
      {confirmacion && <p className="p-4 pb-0 text-sm text-green-700">{confirmacion}</p>}
      <TramiteForm
        valoresIniciales={tramite}
        organismosExistentes={organismos}
        guardando={guardando}
        error={errorGuardado}
        onGuardar={handleGuardar}
      />
    </div>
  );
}
