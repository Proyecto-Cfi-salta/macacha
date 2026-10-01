export function puedeGuardarTramite({
  organismo,
  nombreOficial,
  organismosExistentes,
}: {
  organismo: string;
  nombreOficial: string;
  organismosExistentes: string[];
}): boolean {
  return organismosExistentes.includes(organismo) && nombreOficial.trim() !== "";
}
