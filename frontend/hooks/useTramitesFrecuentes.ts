"use client";

import { useEffect, useState } from "react";
import { obtenerTramitesFrecuentes, TramiteFrecuente } from "../lib/api";

export function useTramitesFrecuentes(organismo: string | undefined) {
  const [tramites, setTramites] = useState<TramiteFrecuente[]>([]);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!organismo) {
      setTramites([]);
      return;
    }
    setCargando(true);
    obtenerTramitesFrecuentes(organismo)
      .then(setTramites)
      .catch(() => setTramites([]))
      .finally(() => setCargando(false));
  }, [organismo]);

  return { tramites, cargando };
}
