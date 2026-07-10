"use client";

import { ChatInput } from "../components/ChatInput";
import { ChatMessage } from "../components/ChatMessage";
import { useChatStream } from "../hooks/useChatStream";
import { useSession } from "../hooks/useSession";

export default function Home() {
  const { sessionId } = useSession();

  if (!sessionId) {
    return null;
  }

  return <Chat sessionId={sessionId} />;
}

function Chat({ sessionId }: { sessionId: string }) {
  const { mensajes, enviando, enviarMensaje } = useChatStream(sessionId);

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col">
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
              mensaje.error
                ? () => {
                    const anterior = mensajes[mensajes.length - 2];
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
  );
}
