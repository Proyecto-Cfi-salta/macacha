"use client";

import { useEffect, useState } from "react";
import { obtenerTramitesFrecuentes, TramiteFrecuente } from "../lib/api";

export function useTramitesFrecuentes(organismo: string | undefined) {
  const [tramites, setTramites] = useState<TramiteFrecuente[]>([]);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    let cancelado = false;

    if (!organismo) {
      setTramites([]);
      return;
    }
    setCargando(true);
    obtenerTramitesFrecuentes(organismo)
      .then((resultado) => {
        if (!cancelado) {
          setTramites(resultado);
        }
      })
      .catch(() => {
        if (!cancelado) {
          setTramites([]);
        }
      })
      .finally(() => {
        if (!cancelado) {
          setCargando(false);
        }
      });

    return () => {
      cancelado = true;
    };
  }, [organismo]);

  return { tramites, cargando };
}
