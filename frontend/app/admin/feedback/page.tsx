"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { obtenerMetricasFeedback, type MetricasFeedback } from "../../../lib/admin-api";
import { textoMotivo } from "../../../lib/feedback";
import { anchoBarra, formatearPorcentaje } from "../../../lib/feedback-metricas";

export default function FeedbackPage() {
  const [metricas, setMetricas] = useState<MetricasFeedback | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      setMetricas(await obtenerMetricasFeedback());
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }

  if (cargando) {
    return <p className="p-4 text-sm texto-secundario">Cargando…</p>;
  }

  if (error || !metricas) {
    return (
      <div className="p-4">
        <p className="text-sm texto-error">No se pudieron cargar las métricas de feedback</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  if (metricas.total === 0) {
    return <p className="p-4 text-sm texto-secundario">Todavía no hay votos registrados</p>;
  }

  const maxMotivo = Math.max(...metricas.motivos.map((m) => m.cantidad), metricas.sin_motivo, 0);
  const maxDia = Math.max(...metricas.por_dia.map((d) => d.positivos + d.negativos), 0);

  return (
    <div className="space-y-6 p-4">
      <h1 className="text-xl font-semibold">Feedback</h1>

      <div className="grid gap-3 sm:grid-cols-4">
        <Tarjeta titulo="Votos" valor={String(metricas.total)} />
        <Tarjeta titulo="👍 Útil" valor={String(metricas.positivos)} />
        <Tarjeta titulo="👎 No útil" valor={String(metricas.negativos)} />
        <Tarjeta titulo="% útil" valor={formatearPorcentaje(metricas.porcentaje_util)} />
      </div>

      <section>
        <h2 className="mb-2 font-semibold">Motivos de los votos negativos</h2>
        {metricas.motivos.length === 0 && metricas.sin_motivo === 0 ? (
          <p className="text-sm texto-secundario">Sin votos negativos.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {metricas.motivos.map((m) => (
              <Barra
                key={m.motivo}
                etiqueta={textoMotivo(m.motivo) || m.motivo}
                cantidad={m.cantidad}
                ancho={anchoBarra(m.cantidad, maxMotivo)}
              />
            ))}
            {metricas.sin_motivo > 0 && (
              <Barra
                etiqueta="Sin motivo"
                cantidad={metricas.sin_motivo}
                ancho={anchoBarra(metricas.sin_motivo, maxMotivo)}
              />
            )}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Votos por día (UTC)</h2>
        <ul className="space-y-2 text-sm">
          {metricas.por_dia.map((d) => (
            <Barra
              key={d.fecha}
              etiqueta={d.fecha}
              cantidad={d.positivos + d.negativos}
              detalle={`👍 ${d.positivos} · 👎 ${d.negativos}`}
              ancho={anchoBarra(d.positivos + d.negativos, maxDia)}
            />
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-1 font-semibold">Por organismo</h2>
        <p className="mb-2 text-xs texto-secundario">
          Aproximación: un voto cuenta en cada organismo citado en su conversación, por lo que puede
          aparecer en más de uno. Las conversaciones sin trámite citado figuran como "Sin trámite".
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="tabla-cabecera">
              <th className="p-2">Organismo</th>
              <th className="p-2">👍</th>
              <th className="p-2">👎</th>
            </tr>
          </thead>
          <tbody>
            {metricas.por_organismo.map((fila) => (
              <tr key={fila.organismo} className="tabla-fila">
                <td className="p-2">{fila.organismo}</td>
                <td className="p-2">{fila.positivos}</td>
                <td className="p-2">{fila.negativos}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Comentarios recientes de votos negativos</h2>
        {metricas.comentarios_recientes.length === 0 ? (
          <p className="text-sm texto-secundario">Todavía no hay comentarios.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {metricas.comentarios_recientes.map((c) => (
              <li key={c.mensaje_id} className="tarjeta">
                <p className="whitespace-pre-wrap">{c.comentario}</p>
                <p className="mt-1 text-xs texto-secundario">
                  {new Date(c.creado_en).toLocaleString("es-AR")}
                  {c.motivo ? ` · ${textoMotivo(c.motivo)}` : ""} ·{" "}
                  <Link href={`/admin/chats/${c.session_id}`} className="underline">
                    Ver chat
                  </Link>
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Tarjeta({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div className="tarjeta">
      <p className="text-xs texto-secundario">{titulo}</p>
      <p className="text-2xl font-semibold">{valor}</p>
    </div>
  );
}

function Barra({
  etiqueta,
  cantidad,
  ancho,
  detalle,
}: {
  etiqueta: string;
  cantidad: number;
  ancho: number;
  detalle?: string;
}) {
  return (
    <li>
      <div className="flex justify-between">
        <span>{etiqueta}</span>
        <span className="texto-secundario">{detalle ?? cantidad}</span>
      </div>
      <div className="h-2 rounded bg-gray-100">
        <div className="h-2 rounded bg-macacha-blue" style={{ width: `${ancho}%` }} />
      </div>
    </li>
  );
}
