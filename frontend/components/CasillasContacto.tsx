"use client";

import { useEffect, useState } from "react";
import { guardarCasilla, listarCasillas, type Casilla } from "../lib/admin-contacto-api";
import { normalizarEmailContacto, textoCasillaGuardada } from "../lib/email-contacto";

type Aviso = { tipo: "ok" | "error"; texto: string };

export function CasillasContacto() {
  const [casillas, setCasillas] = useState<Casilla[] | null>(null);
  const [valores, setValores] = useState<Record<number, string>>({});
  const [avisos, setAvisos] = useState<Record<number, Aviso>>({});
  const [guardando, setGuardando] = useState<number | null>(null);
  const [errorCarga, setErrorCarga] = useState(false);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setErrorCarga(false);
    try {
      const lista = await listarCasillas();
      setCasillas(lista);
      setValores(Object.fromEntries(lista.map((c) => [c.id, c.email_contacto ?? ""])));
    } catch {
      setErrorCarga(true);
    }
  }

  async function handleGuardar(casilla: Casilla) {
    const resultado = normalizarEmailContacto(valores[casilla.id] ?? "");
    if (!resultado.ok) {
      setAvisos((a) => ({ ...a, [casilla.id]: { tipo: "error", texto: resultado.mensaje } }));
      return;
    }
    setGuardando(casilla.id);
    setAvisos((a) => {
      const { [casilla.id]: _quitado, ...resto } = a;
      return resto;
    });
    try {
      const guardada = await guardarCasilla(casilla.id, resultado.email);
      setValores((v) => ({ ...v, [casilla.id]: guardada.email_contacto ?? "" }));
      setAvisos((a) => ({
        ...a,
        [casilla.id]: { tipo: "ok", texto: textoCasillaGuardada(guardada.email_contacto) },
      }));
    } catch (err) {
      setAvisos((a) => ({
        ...a,
        [casilla.id]: {
          tipo: "error",
          texto: err instanceof Error ? err.message : "No se pudo guardar la casilla",
        },
      }));
    } finally {
      setGuardando(null);
    }
  }

  if (errorCarga) {
    return (
      <div className="tarjeta mb-6 max-w-2xl">
        <p className="text-sm texto-error">No se pudieron cargar las casillas de contacto</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  if (casillas === null || casillas.length === 0) {
    return null;
  }

  return (
    <section className="tarjeta mb-6 max-w-2xl">
      <h2 className="mb-1 font-semibold">Casillas de mail de contacto</h2>
      <p className="mb-3 text-xs texto-secundario">
        El aviso de cada solicitud se envía a la casilla del organismo. Si el organismo no tiene
        casilla, se envía a los emails de sus usuarios.
      </p>
      <ul className="space-y-3">
        {casillas.map((casilla) => (
          <li key={casilla.id}>
            <label className="campo-label" htmlFor={`casilla-${casilla.id}`}>
              {casilla.nombre}
            </label>
            <div className="flex gap-2">
              <input
                id={`casilla-${casilla.id}`}
                type="text"
                inputMode="email"
                value={valores[casilla.id] ?? ""}
                onChange={(e) => setValores((v) => ({ ...v, [casilla.id]: e.target.value }))}
                placeholder="mesa@organismo.gob.ar"
                className="campo-input flex-1"
              />
              <button
                type="button"
                onClick={() => handleGuardar(casilla)}
                disabled={guardando === casilla.id}
                className="boton-secundario"
              >
                {guardando === casilla.id ? "Guardando…" : "Guardar"}
              </button>
            </div>
            {avisos[casilla.id] && (
              <p
                className={`mt-1 text-sm ${
                  avisos[casilla.id].tipo === "ok" ? "text-green-700" : "texto-error"
                }`}
              >
                {avisos[casilla.id].texto}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
