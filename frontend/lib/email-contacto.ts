export const MAX_LONGITUD_EMAIL = 254;
const PATRON_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MENSAJE_INVALIDO = "Ingresá un email válido, por ejemplo mesa@organismo.gob.ar";

export type ResultadoEmail = { ok: true; email: string | null } | { ok: false; mensaje: string };

export function normalizarEmailContacto(valor: string): ResultadoEmail {
  const limpio = valor.trim();
  if (limpio === "") return { ok: true, email: null };
  if (limpio.length > MAX_LONGITUD_EMAIL || !PATRON_EMAIL.test(limpio)) {
    return { ok: false, mensaje: MENSAJE_INVALIDO };
  }
  return { ok: true, email: limpio };
}

export function textoCasillaGuardada(email: string | null): string {
  return email ? "Casilla guardada." : "Se quitó la casilla.";
}
