"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  editarEstadoContacto,
  obtenerSolicitudContacto,
  type SolicitudContactoDetalle,
} from "../../../../lib/admin-contacto-api";
import { quienResolvio } from "../../../../lib/admin-contacto-ui";
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
      setSolicitud(await obtenerSolicitudContacto(solicitud.id));
    } catch {
      setError(true);
    } finally {
      setActualizandoEstado(false);
    }
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm texto-error">No se pudo cargar la solicitud</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  if (solicitud === undefined) {
    return <p className="p-4 text-sm texto-secundario">Cargando…</p>;
  }

  if (solicitud === null) {
    return (
      <div className="p-4">
        <p className="text-sm texto-secundario">Solicitud no encontrada</p>
        <Link href="/admin/contacto" className="boton-secundario">
          Volver a la lista
        </Link>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="tarjeta mb-4 max-w-2xl">
        <p><span className="font-semibold">Nombre:</span> {solicitud.nombre}</p>
        <p><span className="font-semibold">Email:</span> {solicitud.email}</p>
        <p><span className="font-semibold">Teléfono:</span> {solicitud.telefono}</p>
        <p><span className="font-semibold">Trámite:</span> {solicitud.tramite_nombre ?? "—"}</p>
        <p>
          <span className="font-semibold">Estado:</span>{" "}
          {solicitud.estado === "resuelto" ? "Resuelto" : "Pendiente"}
        </p>
        {quienResolvio(solicitud) && (
          <p>
            <span className="font-semibold">Resuelto por:</span> {quienResolvio(solicitud)}
            {solicitud.resuelto_en && ` el ${new Date(solicitud.resuelto_en).toLocaleString()}`}
          </p>
        )}
        <p className="mt-2"><span className="font-semibold">Consulta:</span></p>
        <p className="whitespace-pre-wrap text-sm">{solicitud.consulta}</p>
        <button
          onClick={handleCambiarEstado}
          disabled={actualizandoEstado}
          className="boton-primario mt-3"
        >
          {solicitud.estado === "pendiente" ? "Marcar como resuelto" : "Marcar como pendiente"}
        </button>
      </div>

      <h2 className="mb-2 text-sm font-semibold texto-secundario">Conversación completa</h2>
      <ConversacionChat mensajes={solicitud.mensajes} />
    </div>
  );
}
