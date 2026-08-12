"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la lista de contacto</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold">Contacto</h1>
      {solicitudes && solicitudes.length === 0 ? (
        <p className="text-sm text-gray-500">Todavía no hay solicitudes de contacto</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="p-2">Fecha</th>
              <th className="p-2">Nombre</th>
              <th className="p-2">Trámite</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {solicitudes!.map((solicitud) => (
              <tr key={solicitud.id} className="border-b border-gray-100">
                <td className="p-2">{new Date(solicitud.creado_en).toLocaleString()}</td>
                <td className="p-2">
                  <Link
                    href={`/admin/contacto/${solicitud.id}`}
                    className="text-blue-700 hover:underline"
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
