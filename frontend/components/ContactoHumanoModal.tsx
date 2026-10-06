"use client";

import { useState } from "react";
import { enviarSolicitudContacto } from "../lib/contacto-api";
import { tramitesCitadosEnConversacion } from "../lib/contacto-tramites";
import type { Mensaje } from "../hooks/useChatStream";

export function ContactoHumanoModal({
  sessionId,
  mensajes,
  onCerrar,
}: {
  sessionId: string;
  mensajes: Mensaje[];
  onCerrar: () => void;
}) {
  const tramites = tramitesCitadosEnConversacion(mensajes);
  const [tramiteId, setTramiteId] = useState<string | null>(
    tramites.length === 1 ? tramites[0].tramite_id : null
  );
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [telefono, setTelefono] = useState("");
  const [consulta, setConsulta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviado, setEnviado] = useState(false);

  const puedeEnviar =
    nombre.trim() !== "" &&
    email.trim() !== "" &&
    telefono.trim() !== "" &&
    consulta.trim() !== "";

  async function handleSubmit(evento: React.FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await enviarSolicitudContacto({
        session_id: sessionId,
        tramite_id: tramiteId,
        nombre,
        email,
        telefono,
        consulta,
      });
      setEnviado(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo enviar la consulta");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 dark:border dark:border-white/15 dark:bg-macacha-navy">
        {enviado ? (
          <div>
            <p className="text-sm text-gray-800 dark:text-gray-100">
              Recibimos tu consulta. Alguien del área correspondiente se va a poner en
              contacto con vos.
            </p>
            <button onClick={onCerrar} className="boton-primario mt-4">
              Cerrar
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <h2 className="text-lg font-semibold text-macacha-navy dark:text-white">
              Hablar con una persona
            </h2>

            {tramites.length > 1 && (
              <div>
                <label className="campo-label">¿Sobre qué trámite?</label>
                <select
                  value={tramiteId ?? ""}
                  onChange={(e) => setTramiteId(e.target.value || null)}
                  className="campo-input w-full"
                >
                  <option value="">Elegir…</option>
                  {tramites.map((t) => (
                    <option key={t.tramite_id} value={t.tramite_id}>
                      {t.nombre_oficial}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {tramites.length === 1 && (
              <p className="text-sm texto-secundario">Trámite: {tramites[0].nombre_oficial}</p>
            )}
            {tramites.length === 0 && (
              <p className="text-sm texto-secundario">
                No identificamos un trámite en esta conversación — tu consulta la recibe el
                equipo general.
              </p>
            )}

            <div>
              <label className="campo-label">Nombre</label>
              <input
                type="text"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="campo-input w-full"
              />
            </div>
            <div>
              <label className="campo-label">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="campo-input w-full"
              />
            </div>
            <div>
              <label className="campo-label">Teléfono / WhatsApp</label>
              <input
                type="text"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                className="campo-input w-full"
              />
            </div>
            <div>
              <label className="campo-label">Tu consulta</label>
              <textarea
                value={consulta}
                onChange={(e) => setConsulta(e.target.value)}
                className="campo-input w-full"
                rows={3}
              />
            </div>

            {error && <p className="text-sm texto-error">{error}</p>}

            <div className="flex gap-2">
              <button type="submit" disabled={!puedeEnviar || enviando} className="boton-primario">
                {enviando ? "Enviando…" : "Enviar"}
              </button>
              <button type="button" onClick={onCerrar} className="boton-neutro">
                Cancelar
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
