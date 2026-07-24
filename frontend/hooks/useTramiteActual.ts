"use client";

import { useEffect, useState } from "react";
import { obtenerTramite, TramiteDetalle } from "../lib/api";
import type { Mensaje } from "./useChatStream";

export function obtenerUltimoTramiteId(mensajes: Mensaje[]): string | null {
  for (let i = mensajes.length - 1; i >= 0; i--) {
    const fuentes = mensajes[i].fuentes;
    if (fuentes && fuentes.length > 0) {
      return fuentes[fuentes.length - 1].tramite_id;
    }
  }
  return null;
}

export function useTramiteActual(mensajes: Mensaje[]) {
  const [tramite, setTramite] = useState<TramiteDetalle | null>(null);
  const [cargando, setCargando] = useState(false);
  const tramiteId = obtenerUltimoTramiteId(mensajes);

  useEffect(() => {
    if (!tramiteId) {
      setTramite(null);
      return;
    }
    setCargando(true);
    obtenerTramite(tramiteId)
      .then(setTramite)
      .catch(() => setTramite(null))
      .finally(() => setCargando(false));
  }, [tramiteId]);

  return { tramite, cargando };
}
