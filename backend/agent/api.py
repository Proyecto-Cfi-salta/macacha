import json
import os
import uuid
from functools import lru_cache
from typing import Iterator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import sessions
from agent.chat_client import build_real_chat_client
from agent.orchestrator import procesar_turno
from db.pool import crear_pool
from ingest.openai_client import build_real_client
from ingest.repository import incrementar_veces_consultado, obtener_snapshot_vigente

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def obtener_pool():
    return crear_pool(os.environ["DATABASE_URL"])


@lru_cache
def obtener_chat_client():
    return build_real_chat_client()


@lru_cache
def obtener_openai_client():
    return build_real_client()


class ChatRequest(BaseModel):
    session_id: uuid.UUID
    mensaje: str


@app.post("/chat")
def chat(
    request: ChatRequest,
    pool=Depends(obtener_pool),
    chat_client=Depends(obtener_chat_client),
    openai_client=Depends(obtener_openai_client),
):
    def generar() -> Iterator[str]:
        with pool.connection() as conn:
            try:
                fuentes_del_turno: list[dict] = []
                for evento in procesar_turno(
                    conn,
                    chat_client,
                    openai_client.generate_embeddings,
                    openai_client.rerank,
                    str(request.session_id),
                    request.mensaje,
                ):
                    if evento["tipo"] == "fin":
                        fuentes_del_turno = evento["fuentes"]
                    yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                for fuente in fuentes_del_turno:
                    incrementar_veces_consultado(conn, fuente["tramite_id"])
                conn.commit()
            except Exception:
                conn.rollback()
                evento_error = {"tipo": "error", "mensaje": "Ocurrió un error al procesar tu mensaje."}
                yield f"data: {json.dumps(evento_error, ensure_ascii=False)}\n\n"

    return StreamingResponse(generar(), media_type="text/event-stream")


@app.get("/sesiones/{session_id}/mensajes")
def obtener_mensajes(session_id: uuid.UUID, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return sessions.obtener_mensajes_visibles(conn, str(session_id))


@app.get("/tramites/{tramite_id}")
def obtener_tramite(tramite_id: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")
        return {
            "tramite_id": tramite_id,
            "nombre_oficial": snapshot["nombre_oficial"],
            "organismo": snapshot["organismo"],
            "categoria": snapshot["categoria"],
            "requisitos": snapshot.get("requisitos", []),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
        }
