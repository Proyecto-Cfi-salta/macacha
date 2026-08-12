"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  editarEstadoContacto,
  obtenerSolicitudContacto,
  type SolicitudContactoDetalle,
} from "../../../../lib/admin-contacto-api";
import { ConversacionChat } from "../../../../components/ConversacionChat";

export default function ContactoDetallePage() {
  const params = useParams<{ id: string }>();
  const [solicitud, setSolicitud] = useState<SolicitudContactoDetalle | null | undefined>(undefined);
  const [error, setError] = useState(false);
  const [actualizandoEstado, setActualizandoEstado] = useState(false);

  useEffect(() => {
    cargar();
  }, [params.id]);

  async function cargar() {
    setError(false);
    setSolicitud(undefined);
    try {
      const resultado = await obtenerSolicitudContacto(params.id);
      setSolicitud(resultado);
    } catch {
      setError(true);
    }
  }

  async function handleCambiarEstado() {
    if (!solicitud) return;
    const nuevoEstado = solicitud.estado === "pendiente" ? "resuelto" : "pendiente";
    setActualizandoEstado(true);
    try {
      await editarEstadoContacto(solicitud.id, nuevoEstado);
      setSolicitud({ ...solicitud, estado: nuevoEstado });
    } catch {
      setError(true);
    } finally {
      setActualizandoEstado(false);
    }
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la solicitud</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (solicitud === undefined) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (solicitud === null) {
    return (
      <div className="p-4">
        <p className="text-sm text-gray-600">Solicitud no encontrada</p>
        <Link href="/admin/contacto" className="text-sm text-blue-700 underline">
          Volver a la lista
        </Link>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 max-w-2xl rounded border border-gray-200 p-4">
        <p><span className="font-semibold">Nombre:</span> {solicitud.nombre}</p>
        <p><span className="font-semibold">Email:</span> {solicitud.email}</p>
        <p><span className="font-semibold">Teléfono:</span> {solicitud.telefono}</p>
        <p><span className="font-semibold">Trámite:</span> {solicitud.tramite_nombre ?? "—"}</p>
        <p className="mt-2"><span className="font-semibold">Consulta:</span></p>
        <p className="whitespace-pre-wrap text-sm">{solicitud.consulta}</p>
        <button
          onClick={handleCambiarEstado}
          disabled={actualizandoEstado}
          className="mt-3 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {solicitud.estado === "pendiente" ? "Marcar como resuelto" : "Marcar como pendiente"}
        </button>
      </div>

      <h2 className="mb-2 text-sm font-semibold text-gray-600">Conversación completa</h2>
      <ConversacionChat mensajes={solicitud.mensajes} />
    </div>
  );
}
