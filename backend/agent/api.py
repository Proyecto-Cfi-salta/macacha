import json
import os
import uuid
from functools import lru_cache
from typing import Iterator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import sessions
from agent.admin import chats_repository as admin_chats_repository
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
from agent.admin.dependencies import requiere_admin
from agent.chat_client import build_real_chat_client
from agent.orchestrator import procesar_turno
from db.pool import crear_pool
from ingest.openai_client import build_real_client
from ingest.repository import (
    incrementar_veces_consultado,
    obtener_snapshot_vigente,
    obtener_tramites_frecuentes,
)

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
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


@app.get("/organismos/{organismo}/tramites-frecuentes")
def tramites_frecuentes(organismo: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return obtener_tramites_frecuentes(conn, organismo)


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/admin/login")
def admin_login(request: LoginRequest, response: Response, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin = admin_repository.obtener_admin_por_email(conn, request.email)

    if admin is None or not admin_security.verify_password(request.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = admin_security.crear_token(admin["id"])
    response.set_cookie(
        "admin_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )
    return {"email": admin["email"]}


@app.post("/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie("admin_session")
    return {"ok": True}


@app.get("/admin/me")
def admin_me(admin_id: str = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin = admin_repository.obtener_admin_por_id(conn, admin_id)

    if admin is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return {"email": admin["email"]}


@app.get("/admin/sesiones")
def admin_listar_sesiones(
    page: int = 1,
    page_size: int = 20,
    admin_id: str = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        sesiones = admin_chats_repository.listar_sesiones(conn, page, page_size)
        total = admin_chats_repository.contar_sesiones(conn)
    return {"sesiones": sesiones, "total": total, "page": page, "page_size": page_size}


@app.get("/admin/sesiones/{session_id}")
def admin_obtener_sesion(
    session_id: uuid.UUID,
    admin_id: str = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if not admin_chats_repository.sesion_existe(conn, str(session_id)):
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        return admin_chats_repository.obtener_mensajes_completos(conn, str(session_id))
