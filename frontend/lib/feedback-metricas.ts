export function formatearPorcentaje(valor: number | null): string {
  if (valor === null || Number.isNaN(valor)) return "—";
  return `${valor.toFixed(1).replace(".", ",")}%`;
}

export function anchoBarra(cantidad: number, maximo: number): number {
  if (maximo <= 0) return 0;
  return Math.round((cantidad / maximo) * 100);
}
