"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listarTramites, type TramiteResumen } from "../../../lib/admin-tramites-api";

export default function TramitesPage() {
  const [tramites, setTramites] = useState<TramiteResumen[] | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const resultado = await listarTramites();
      setTramites(resultado);
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
        <p className="text-sm text-red-600">No se pudo cargar la lista de trámites</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Trámites</h1>
        <Link href="/admin/tramites/nuevo" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
          Nuevo trámite
        </Link>
      </div>
      {tramites && tramites.length === 0 ? (
        <p className="text-sm text-gray-500">Todavía no hay trámites cargados</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="p-2">ID</th>
              <th className="p-2">Nombre</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Categoría</th>
              <th className="p-2">Consultas</th>
              <th className="p-2">Versión</th>
            </tr>
          </thead>
          <tbody>
            {tramites!.map((tramite) => (
              <tr key={tramite.id} className="border-b border-gray-100">
                <td className="p-2">
                  <Link href={`/admin/tramites/${tramite.id}`} className="text-blue-700 hover:underline">
                    {tramite.id}
                  </Link>
                </td>
                <td className="p-2">{tramite.nombre_oficial}</td>
                <td className="p-2">{tramite.organismo}</td>
                <td className="p-2">{tramite.categoria}</td>
                <td className="p-2">{tramite.veces_consultado}</td>
                <td className="p-2">{tramite.numero_version ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
