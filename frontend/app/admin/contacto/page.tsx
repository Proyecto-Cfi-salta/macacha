"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CasillasContacto } from "../../../components/CasillasContacto";
import { quienResolvio } from "../../../lib/admin-contacto-ui";
import { listarSolicitudesContacto, type PaginaSolicitudesContacto } from "../../../lib/admin-contacto-api";

const POR_PAGINA = 5;

export default function ContactoPage() {
  const [datos, setDatos] = useState<PaginaSolicitudesContacto | null>(null);
  const [pagina, setPagina] = useState(1);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, [pagina]);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      setDatos(await listarSolicitudesContacto(pagina, POR_PAGINA));
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

  const solicitudes = datos?.solicitudes ?? [];
  const totalPaginas = Math.max(1, Math.ceil((datos?.total ?? 0) / POR_PAGINA));

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold">Contacto</h1>
      <CasillasContacto />
      {datos?.total === 0 ? (
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
              <th className="p-2">Resuelto por</th>
            </tr>
          </thead>
          <tbody>
            {solicitudes.map((solicitud) => (
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
                <td className="p-2">
                  {quienResolvio(solicitud) ?? "—"}
                  {solicitud.resuelto_en && (
                    <span className="block text-xs texto-secundario">
                      {new Date(solicitud.resuelto_en).toLocaleString()}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {datos && datos.total > 0 && (
        <div className="mt-4 flex items-center gap-4 text-sm">
          <button
            onClick={() => setPagina((p) => p - 1)}
            disabled={pagina <= 1}
            className="boton-secundario"
          >
            Anterior
          </button>
          <span>
            Página {pagina} de {totalPaginas}
          </span>
          <button
            onClick={() => setPagina((p) => p + 1)}
            disabled={pagina >= totalPaginas}
            className="boton-secundario"
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}
