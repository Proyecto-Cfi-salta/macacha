"use client";

import { useEffect, useState } from "react";
import { obtenerHistorial } from "../lib/api";

export type Fuente = {
  tramite_id: string;
  nombre_oficial: string;
  fuente_url: string | null;
};

export type Mensaje = {
  rol: "user" | "assistant";
  contenido: string;
  fuentes?: Fuente[];
  error?: boolean;
};

export type EventoSSE =
  | { tipo: "texto"; delta: string }
  | { tipo: "fin"; fuentes: Fuente[] }
  | { tipo: "error"; mensaje: string };

export function parsearLineasSSE(texto: string): EventoSSE[] {
  return texto
    .split("\n\n")
    .filter((linea) => linea.startsWith("data: "))
    .map((linea) => JSON.parse(linea.slice("data: ".length)) as EventoSSE);
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useChatStream(sessionId: string) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    obtenerHistorial(sessionId).then((historial) => {
      setMensajes(
        historial.map((m) => ({ rol: m.rol, contenido: m.contenido }))
      );
    });
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
        copia[copia.length - 1] = { ...ultimo, fuentes: evento.fuentes };
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

    const respuesta = await fetch(`${BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, mensaje: texto }),
    });

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

    setEnviando(false);
  }

  return { mensajes, enviando, enviarMensaje };
}
