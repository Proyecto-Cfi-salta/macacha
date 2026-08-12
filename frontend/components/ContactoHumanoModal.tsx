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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6">
        {enviado ? (
          <div>
            <p className="text-sm text-gray-800">
              Recibimos tu consulta. Alguien del área correspondiente se va a poner en
              contacto con vos.
            </p>
            <button
              onClick={onCerrar}
              className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white"
            >
              Cerrar
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <h2 className="text-lg font-semibold">Hablar con una persona</h2>

            {tramites.length > 1 && (
              <div>
                <label className="mb-1 block text-sm font-medium">¿Sobre qué trámite?</label>
                <select
                  value={tramiteId ?? ""}
                  onChange={(e) => setTramiteId(e.target.value || null)}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
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
              <p className="text-sm text-gray-600">Trámite: {tramites[0].nombre_oficial}</p>
            )}
            {tramites.length === 0 && (
              <p className="text-sm text-gray-500">
                No identificamos un trámite en esta conversación — tu consulta la recibe el
                equipo general.
              </p>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium">Nombre</label>
              <input
                type="text"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Teléfono / WhatsApp</label>
              <input
                type="text"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Tu consulta</label>
              <textarea
                value={consulta}
                onChange={(e) => setConsulta(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                rows={3}
              />
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!puedeEnviar || enviando}
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                {enviando ? "Enviando…" : "Enviar"}
              </button>
              <button
                type="button"
                onClick={onCerrar}
                className="rounded px-4 py-2 text-sm text-gray-500"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
