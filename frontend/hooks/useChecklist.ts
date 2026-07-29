"use client";

import { useEffect, useState } from "react";

export type TipoItemChecklist = "requisito" | "paso";

export function claveChecklist(tramiteId: string): string {
  return `macacha_checklist_${tramiteId}`;
}

export function claveItem(tipo: TipoItemChecklist, indice: number): string {
  return `${tipo}:${indice}`;
}

export function toggleItem(
  estado: Record<string, boolean>,
  clave: string
): Record<string, boolean> {
  return { ...estado, [clave]: !estado[clave] };
}

export function useChecklist(tramiteId: string | null) {
  const [estado, setEstado] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!tramiteId) {
      setEstado({});
      return;
    }
    const guardado = localStorage.getItem(claveChecklist(tramiteId));
    setEstado(guardado ? JSON.parse(guardado) : {});
  }, [tramiteId]);

  function toggle(tipo: TipoItemChecklist, indice: number) {
    if (!tramiteId) return;
    setEstado((prev) => {
      const nuevo = toggleItem(prev, claveItem(tipo, indice));
      localStorage.setItem(claveChecklist(tramiteId), JSON.stringify(nuevo));
      return nuevo;
    });
  }

  function estaTildado(tipo: TipoItemChecklist, indice: number): boolean {
    return Boolean(estado[claveItem(tipo, indice)]);
  }

  return { estaTildado, toggle };
}
