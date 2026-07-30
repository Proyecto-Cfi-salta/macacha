"use client";

import { useEffect, useState } from "react";
import { obtenerTramite, obtenerTopTramites, TramiteDetalle, TramiteFrecuente } from "../lib/api";
import type { CandidatoAmbiguo, Mensaje } from "./useChatStream";

export type EstadoRelevante =
  | { tipo: "tramite"; tramiteId: string }
  | { tipo: "ambiguo"; candidatos: CandidatoAmbiguo[] }
  | { tipo: "idle" };

export function determinarEstadoRelevante(mensajes: Mensaje[]): EstadoRelevante {
  for (let i = mensajes.length - 1; i >= 0; i--) {
    const fuentes = mensajes[i].fuentes;
    if (fuentes && fuentes.length > 0) {
      return { tipo: "tramite", tramiteId: fuentes[fuentes.length - 1].tramite_id };
    }
    const candidatos = mensajes[i].candidatosAmbiguos;
    if (candidatos && candidatos.length > 0) {
      return { tipo: "ambiguo", candidatos };
    }
  }
  return { tipo: "idle" };
}

export type VistaPanel =
  | { tipo: "cargando" }
  | { tipo: "top3"; tramites: TramiteFrecuente[] }
  | { tipo: "ambiguo"; candidatos: CandidatoAmbiguo[] }
  | { tipo: "tramite"; tramite: TramiteDetalle };

export function usePanelTramite(mensajes: Mensaje[]): VistaPanel {
  const estado = determinarEstadoRelevante(mensajes);
  const tramiteId = estado.tipo === "tramite" ? estado.tramiteId : null;
  const [tramite, setTramite] = useState<TramiteDetalle | null>(null);
  const [tramites, setTramites] = useState<TramiteFrecuente[] | null>(null);

  useEffect(() => {
    let cancelado = false;
    if (!tramiteId) {
      setTramite(null);
      return;
    }
    obtenerTramite(tramiteId)
      .then((resultado) => {
        if (!cancelado) setTramite(resultado);
      })
      .catch(() => {
        if (!cancelado) setTramite(null);
      });
    return () => {
      cancelado = true;
    };
  }, [tramiteId]);

  useEffect(() => {
    let cancelado = false;
    if (estado.tipo !== "idle") {
      return;
    }
    obtenerTopTramites()
      .then((resultado) => {
        if (!cancelado) setTramites(resultado);
      })
      .catch(() => {
        if (!cancelado) setTramites([]);
      });
    return () => {
      cancelado = true;
    };
  }, [estado.tipo]);

  if (estado.tipo === "tramite") {
    return tramite ? { tipo: "tramite", tramite } : { tipo: "cargando" };
  }
  if (estado.tipo === "ambiguo") {
    return { tipo: "ambiguo", candidatos: estado.candidatos };
  }
  return tramites ? { tipo: "top3", tramites } : { tipo: "cargando" };
}
