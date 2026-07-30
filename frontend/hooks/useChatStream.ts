"use client";

import { useEffect, useState } from "react";
import { BASE_URL, obtenerHistorial } from "../lib/api";

export type Fuente = {
  tramite_id: string;
  nombre_oficial: string;
  fuente_url: string | null;
};

export type CandidatoAmbiguo = {
  tramite_id: string;
  nombre_oficial: string;
  descripcion: string;
};

export type Mensaje = {
  rol: "user" | "assistant";
  contenido: string;
  fuentes?: Fuente[];
  candidatosAmbiguos?: CandidatoAmbiguo[];
  error?: boolean;
};

export type EventoSSE =
  | { tipo: "texto"; delta: string }
  | { tipo: "fin"; fuentes: Fuente[]; candidatos_ambiguos: CandidatoAmbiguo[] }
  | { tipo: "error"; mensaje: string };

export function parsearLineasSSE(texto: string): EventoSSE[] {
  return texto
    .split("\n\n")
    .filter((linea) => linea.startsWith("data: "))
    .map((linea) => JSON.parse(linea.slice("data: ".length)) as EventoSSE);
}

export function useChatStream(sessionId: string) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    obtenerHistorial(sessionId)
      .then((historial) => {
        setMensajes(
          historial.map((m) => ({ rol: m.rol, contenido: m.contenido }))
        );
      })
      .catch(() => setMensajes([]));
  }, [sessionId]);

  function aplicarEvento(evento: EventoSSE) {
    setMensajes((prev) => {
      const copia = [...prev];
      const ultimo = copia[copia.length - 1];
      if (evento.tipo === "texto") {
        copia[copia.length - 1] = {
          ...ultimo,
          contenido: ultimo.contenido + evento.delta,
        };
      } else if (evento.tipo === "fin") {
        copia[copia.length - 1] = {
          ...ultimo,
          fuentes: evento.fuentes,
          candidatosAmbiguos: evento.candidatos_ambiguos,
        };
      } else if (evento.tipo === "error") {
        copia[copia.length - 1] = {
          ...ultimo,
          contenido: evento.mensaje,
          error: true,
        };
      }
      return copia;
    });
  }

  async function enviarMensaje(texto: string) {
    setMensajes((prev) => [
      ...prev,
      { rol: "user", contenido: texto },
      { rol: "assistant", contenido: "" },
    ]);
    setEnviando(true);

    try {
      const respuesta = await fetch(`${BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, mensaje: texto }),
      });

      if (!respuesta.ok) {
        console.error("Respuesta no exitosa del backend:", respuesta.status);
        aplicarEvento({
          tipo: "error",
          mensaje: "No se pudo conectar con el servidor. Intentá de nuevo.",
        });
        return;
      }

      const lector = respuesta.body?.getReader();
      const decodificador = new TextDecoder();
      let acumulado = "";

      if (lector) {
        while (true) {
          const { done, value } = await lector.read();
          if (done) break;
          acumulado += decodificador.decode(value, { stream: true });

          const partes = acumulado.split("\n\n");
          acumulado = partes.pop() ?? "";

          if (partes.length > 0) {
            for (const evento of parsearLineasSSE(partes.join("\n\n"))) {
              aplicarEvento(evento);
            }
          }
        }
      }
    } catch (error) {
      console.error("Error al enviar el mensaje:", error);
      aplicarEvento({
        tipo: "error",
        mensaje: "No se pudo conectar con el servidor. Intentá de nuevo.",
      });
    } finally {
      setEnviando(false);
    }
  }

  return { mensajes, enviando, enviarMensaje };
}
