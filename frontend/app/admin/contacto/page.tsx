"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CasillasContacto } from "../../../components/CasillasContacto";
import { listarSolicitudesContacto, type SolicitudContacto } from "../../../lib/admin-contacto-api";

export default function ContactoPage() {
  const [solicitudes, setSolicitudes] = useState<SolicitudContacto[] | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const resultado = await listarSolicitudesContacto();
      setSolicitudes(resultado);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }

  if (cargando) {
    return <p className="p-4 text-sm texto-secundario">Cargando…</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm texto-error">No se pudo cargar la lista de contacto</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold">Contacto</h1>
      <CasillasContacto />
      {solicitudes && solicitudes.length === 0 ? (
        <p className="text-sm texto-secundario">Todavía no hay solicitudes de contacto</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="tabla-cabecera">
              <th className="p-2">Fecha</th>
              <th className="p-2">Nombre</th>
              <th className="p-2">Trámite</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {solicitudes!.map((solicitud) => (
              <tr key={solicitud.id} className="tabla-fila">
                <td className="p-2">{new Date(solicitud.creado_en).toLocaleString()}</td>
                <td className="p-2">
                  <Link
                    href={`/admin/contacto/${solicitud.id}`}
                    className="boton-secundario"
                  >
                    {solicitud.nombre}
                  </Link>
                </td>
                <td className="p-2">{solicitud.tramite_nombre ?? "—"}</td>
                <td className="p-2">{solicitud.organismo ?? "—"}</td>
                <td className="p-2">
                  {solicitud.estado === "resuelto" ? "Resuelto" : "Pendiente"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
