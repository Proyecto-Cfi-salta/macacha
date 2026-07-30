"use client";

import { useState } from "react";
import { ChatInput } from "../components/ChatInput";
import { ChatMessage } from "../components/ChatMessage";
import { TramiteInfoPanel } from "../components/TramiteInfoPanel";
import { TramitesAmbiguosPanel } from "../components/TramitesAmbiguosPanel";
import { TramitesFrecuentesPanel } from "../components/TramitesFrecuentesPanel";
import { useChatStream } from "../hooks/useChatStream";
import { usePanelTramite } from "../hooks/usePanelTramite";
import { useSession } from "../hooks/useSession";

export default function Home() {
  const { sessionId } = useSession();

  if (!sessionId) {
    return null;
  }

  return <Chat sessionId={sessionId} />;
}

type Tab = "chat" | "info";

function Chat({ sessionId }: { sessionId: string }) {
  const { mensajes, enviando, enviarMensaje } = useChatStream(sessionId);
  const vista = usePanelTramite(mensajes);
  const [tab, setTab] = useState<Tab>("chat");

  function preguntarSobre(mensaje: string) {
    enviarMensaje(mensaje);
    setTab("chat");
  }

  return (
    <div className="mx-auto flex h-screen max-w-6xl flex-col md:flex-row">
      <nav className="flex border-b border-gray-200 md:hidden">
        <TabButton activo={tab === "chat"} onClick={() => setTab("chat")}>
          Chat
        </TabButton>
        <TabButton activo={tab === "info"} onClick={() => setTab("info")}>
          Info del trámite
        </TabButton>
      </nav>

      <main
        className={`min-w-0 flex-1 flex-col ${tab === "chat" ? "flex" : "hidden"} md:flex`}
      >
        <header className="border-b border-gray-200 p-4">
          <h1 className="text-lg font-semibold">Macacha</h1>
          <p className="text-sm text-gray-500">
            Asistente de trámites — Provincia de Salta
          </p>
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {mensajes.map((mensaje, indice) => (
            <ChatMessage
              key={indice}
              mensaje={mensaje}
              onReintentar={
                mensaje.error && !enviando
                  ? () => {
                      const anterior = mensajes[indice - 1];
                      if (anterior) enviarMensaje(anterior.contenido);
                    }
                  : undefined
              }
            />
          ))}
          {enviando && <p className="text-sm text-gray-400">escribiendo…</p>}
        </div>
        <ChatInput disabled={enviando} onEnviar={enviarMensaje} />
      </main>

      <aside
        className={`w-full flex-1 overflow-y-auto border-gray-200 p-4 md:block md:flex-none md:w-72 md:border-l ${
          tab === "info" ? "block" : "hidden"
        }`}
      >
        {vista.tipo === "tramite" && (
          <TramiteInfoPanel
            tramite={vista.tramite}
            onPreguntar={preguntarSobre}
            preguntarDeshabilitado={enviando}
          />
        )}
        {vista.tipo === "ambiguo" && (
          <TramitesAmbiguosPanel
            candidatos={vista.candidatos}
            onPreguntar={preguntarSobre}
            preguntarDeshabilitado={enviando}
          />
        )}
        {vista.tipo === "top3" && (
          <TramitesFrecuentesPanel
            tramites={vista.tramites}
            onPreguntar={preguntarSobre}
            preguntarDeshabilitado={enviando}
          />
        )}
        {vista.tipo === "cargando" && (
          <p className="text-sm text-gray-400">La info del trámite va a aparecer acá.</p>
        )}
      </aside>
    </div>
  );
}

function TabButton({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      className={`flex-1 p-3 text-sm font-medium ${
        activo ? "border-b-2 border-blue-600 text-blue-600" : "text-gray-500"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
