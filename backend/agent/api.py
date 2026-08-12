import json
import os
import uuid
from functools import lru_cache
from typing import Iterator, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import mail, sessions
from agent.admin import chats_repository as admin_chats_repository
from agent.admin import contacto_repository
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
from agent.admin import tramite_editor as admin_tramite_editor
from agent.admin import tramites_repository as admin_tramites_repository
from agent.admin.dependencies import AdminActual, requiere_admin, requiere_super_admin
from agent.chat_client import build_real_chat_client
from agent.orchestrator import procesar_turno
from db.pool import crear_pool
from ingest.openai_client import build_real_client
from ingest.repository import (
    incrementar_veces_consultado,
    obtener_snapshot_vigente,
    obtener_top_tramites,
    obtener_tramites_frecuentes,
)

load_dotenv()

if not os.environ.get("ADMIN_JWT_SECRET"):
    raise RuntimeError(
        "Falta la variable de entorno ADMIN_JWT_SECRET. Ver .env.example."
    )

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
            "costo": snapshot.get("costo", ""),
            "modalidad": snapshot.get("modalidad", ""),
            "duracion": snapshot.get("duracion", ""),
            "pasos": snapshot.get("pasos", []),
            "enlaces_oficiales": snapshot.get("enlaces_oficiales", []),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
        }


@app.get("/organismos/{organismo}/tramites-frecuentes")
def tramites_frecuentes(organismo: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return obtener_tramites_frecuentes(conn, organismo)


@app.get("/tramites-frecuentes")
def top_tramites(pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return obtener_top_tramites(conn)


class ContactoPayload(BaseModel):
    session_id: uuid.UUID
    tramite_id: str | None = None
    nombre: str = Field(min_length=1)
    email: str = Field(min_length=1)
    telefono: str = Field(min_length=1)
    consulta: str = Field(min_length=1)


def _armar_cuerpo_mail(request: ContactoPayload, mensajes: list[dict]) -> str:
    lineas = [
        f"Nombre: {request.nombre}",
        f"Email: {request.email}",
        f"Teléfono: {request.telefono}",
        "",
        "Consulta:",
        request.consulta,
        "",
        "--- Conversación completa ---",
    ]
    for mensaje in mensajes:
        etiqueta = "Persona" if mensaje["rol"] == "user" else "Macacha"
        lineas.append(f"{etiqueta}: {mensaje['contenido']}")
    return "\n".join(lineas)


@app.post("/contacto")
def crear_solicitud_contacto(request: ContactoPayload, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = (
            admin_tramites_repository.obtener_organismo_id_de_tramite(conn, request.tramite_id)
            if request.tramite_id
            else None
        )
        contacto_repository.crear_solicitud(
            conn,
            str(request.session_id),
            request.tramite_id,
            organismo_id,
            request.nombre,
            request.email,
            request.telefono,
            request.consulta,
        )
        conn.commit()

        destinatarios = contacto_repository.resolver_destinatarios(conn, organismo_id)
        mensajes = sessions.obtener_mensajes_visibles(conn, str(request.session_id))

    try:
        mail.enviar_mail(
            destinatarios,
            asunto=f"Nueva consulta de {request.nombre}",
            cuerpo_texto=_armar_cuerpo_mail(request, mensajes),
        )
    except Exception:
        pass  # best-effort: la solicitud ya está guardada y visible en /admin/contacto

    return {"ok": True}


class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/admin/login")
def admin_login(request: LoginRequest, response: Response, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin = admin_repository.obtener_admin_por_email(conn, request.email)

        if (
            admin is None
            or not admin["activo"]
            or not admin_security.verify_password(request.password, admin["password_hash"])
        ):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        organismo = (
            admin_tramites_repository.obtener_nombre_organismo(conn, admin["organismo_id"])
            if admin["organismo_id"] is not None
            else None
        )

        token = admin_security.crear_token(admin)

    response.set_cookie(
        "admin_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )
    return {"email": admin["email"], "rol": admin["rol"], "organismo": organismo}


@app.post("/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie("admin_session")
    return {"ok": True}


@app.get("/admin/me")
def admin_me(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin_db = admin_repository.obtener_admin_por_id(conn, admin.id)
        if admin_db is None or not admin_db["activo"]:
            raise HTTPException(status_code=401, detail="No autenticado")
        organismo = (
            admin_tramites_repository.obtener_nombre_organismo(conn, admin_db["organismo_id"])
            if admin_db["organismo_id"] is not None
            else None
        )
    return {"email": admin_db["email"], "rol": admin_db["rol"], "organismo": organismo}


@app.get("/admin/sesiones")
def admin_listar_sesiones(
    page: int = 1,
    page_size: int = 20,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if admin.rol == "admin_organismo":
            sesiones, total = admin_chats_repository.listar_sesiones_de_organismo(
                conn, admin.organismo_id, page, page_size
            )
        else:
            sesiones = admin_chats_repository.listar_sesiones(conn, page, page_size)
            total = admin_chats_repository.contar_sesiones(conn)
    return {"sesiones": sesiones, "total": total, "page": page, "page_size": page_size}


@app.get("/admin/sesiones/{session_id}")
def admin_obtener_sesion(
    session_id: uuid.UUID,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if admin.rol == "admin_organismo":
            permitido = admin_chats_repository.sesion_pertenece_a_organismo(
                conn, str(session_id), admin.organismo_id
            )
        else:
            permitido = admin_chats_repository.sesion_existe(conn, str(session_id))

        if not permitido:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        return admin_chats_repository.obtener_mensajes_completos(conn, str(session_id))


@app.get("/admin/tramites")
def admin_listar_tramites(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = admin.organismo_id if admin.rol == "admin_organismo" else None
        return admin_tramites_repository.listar_tramites(conn, organismo_id)


@app.get("/admin/organismos")
def admin_listar_organismos(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return admin_tramites_repository.listar_organismos(conn)


def _verificar_tramite_de_mi_organismo(conn, admin: AdminActual, tramite_id: str) -> None:
    if admin.rol != "admin_organismo":
        return
    organismo_del_tramite = admin_tramites_repository.obtener_organismo_id_de_tramite(conn, tramite_id)
    if organismo_del_tramite != admin.organismo_id:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")


def _verificar_payload_de_mi_organismo(conn, admin: AdminActual, organismo_payload: str) -> None:
    if admin.rol != "admin_organismo":
        return
    nombre_organismo_admin = admin_tramites_repository.obtener_nombre_organismo(conn, admin.organismo_id)
    if organismo_payload != nombre_organismo_admin:
        raise HTTPException(
            status_code=400, detail="No podés asignar un trámite a otro organismo"
        )


@app.get("/admin/tramites/{tramite_id}")
def admin_obtener_tramite(
    tramite_id: str, admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
        _verificar_tramite_de_mi_organismo(conn, admin, tramite_id)
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")
        return {
            "organismo": snapshot["organismo"],
            "categoria": snapshot["categoria"],
            "nombre_oficial": snapshot["nombre_oficial"],
            "descripcion": snapshot.get("descripcion", ""),
            "objetivo": snapshot.get("objetivo", ""),
            "requisitos": snapshot.get("requisitos", []),
            "pasos": snapshot.get("pasos", []),
            "costo": snapshot.get("costo", ""),
            "modalidad": snapshot.get("modalidad", ""),
            "duracion": snapshot.get("duracion", ""),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
            "problemas_frecuentes": snapshot.get("problemas_frecuentes", []),
            "sinonimos": snapshot.get("sinonimos", []),
            "keywords": snapshot.get("keywords", []),
            "enlaces_oficiales": snapshot.get("enlaces_oficiales", []),
            "preguntas_frecuentes": snapshot.get("preguntas_frecuentes", []),
        }


class FaqPayload(BaseModel):
    pregunta: str
    respuesta: str


class TramitePayload(BaseModel):
    organismo: str = Field(min_length=1)
    categoria: str = ""
    nombre_oficial: str = Field(min_length=1)
    descripcion: str = ""
    objetivo: str = ""
    requisitos: list[str] = []
    pasos: list[str] = []
    costo: str = ""
    modalidad: str = ""
    duracion: str = ""
    telefono_contacto: str = ""
    email_contacto: str = ""
    problemas_frecuentes: list[str] = []
    sinonimos: list[str] = []
    keywords: list[str] = []
    enlaces_oficiales: list[str] = []
    preguntas_frecuentes: list[FaqPayload] = []


@app.put("/admin/tramites/{tramite_id}")
def admin_editar_tramite(
    tramite_id: str,
    request: TramitePayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
    openai_client=Depends(obtener_openai_client),
):
    with pool.connection() as conn:
        _verificar_tramite_de_mi_organismo(conn, admin, tramite_id)
        _verificar_payload_de_mi_organismo(conn, admin, request.organismo)

        if obtener_snapshot_vigente(conn, tramite_id) is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")

        try:
            resultado = admin_tramite_editor.editar_tramite(
                conn, tramite_id, request.model_dump(), openai_client.generate_embeddings
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(
                status_code=502,
                detail="No se pudieron generar los embeddings. Verificá la configuración de OpenAI.",
            )
    return resultado


@app.post("/admin/tramites")
def admin_crear_tramite(
    request: TramitePayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
    openai_client=Depends(obtener_openai_client),
):
    with pool.connection() as conn:
        _verificar_payload_de_mi_organismo(conn, admin, request.organismo)
        try:
            resultado = admin_tramite_editor.crear_tramite(
                conn, request.model_dump(), openai_client.generate_embeddings
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(
                status_code=502,
                detail="No se pudieron generar los embeddings. Verificá la configuración de OpenAI.",
            )
    return resultado


class UsuarioPayload(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=8)
    rol: Literal["super_admin", "admin_organismo"]
    organismo_id: int | None = None


class UsuarioEdicionPayload(BaseModel):
    rol: Literal["super_admin", "admin_organismo"]
    organismo_id: int | None = None
    activo: bool
    password: str | None = Field(default=None, min_length=8)


class OrganismoPayload(BaseModel):
    nombre: str = Field(min_length=1)


def _validar_consistencia_rol_organismo(rol: str, organismo_id: int | None) -> None:
    if rol == "admin_organismo" and organismo_id is None:
        raise HTTPException(
            status_code=400, detail="Un admin de organismo necesita un organismo asignado"
        )
    if rol == "super_admin" and organismo_id is not None:
        raise HTTPException(
            status_code=400, detail="Un super admin no puede tener un organismo asignado"
        )


@app.get("/admin/usuarios")
def admin_listar_usuarios(
    admin: AdminActual = Depends(requiere_super_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
        return admin_repository.listar_admins(conn)


@app.post("/admin/usuarios")
def admin_crear_usuario(
    request: UsuarioPayload,
    admin: AdminActual = Depends(requiere_super_admin),
    pool=Depends(obtener_pool),
):
    _validar_consistencia_rol_organismo(request.rol, request.organismo_id)
    password_hash = admin_security.hash_password(request.password)
    with pool.connection() as conn:
        if admin_repository.obtener_admin_por_email(conn, request.email) is not None:
            raise HTTPException(status_code=409, detail="Ya existe un admin con ese email")
        admin_repository.crear_admin(
            conn, request.email, password_hash, request.rol, request.organismo_id
        )
        conn.commit()
    return {"ok": True}


@app.put("/admin/usuarios/{admin_id}")
def admin_editar_usuario(
    admin_id: uuid.UUID,
    request: UsuarioEdicionPayload,
    admin: AdminActual = Depends(requiere_super_admin),
    pool=Depends(obtener_pool),
):
    _validar_consistencia_rol_organismo(request.rol, request.organismo_id)
    password_hash = admin_security.hash_password(request.password) if request.password else None
    with pool.connection() as conn:
        if admin_repository.obtener_admin_por_id(conn, str(admin_id)) is None:
            raise HTTPException(status_code=404, detail="Admin no encontrado")
        admin_repository.editar_admin(
            conn, str(admin_id), request.rol, request.organismo_id, request.activo, password_hash
        )
        conn.commit()
    return {"ok": True}


@app.post("/admin/organismos")
def admin_crear_organismo(
    request: OrganismoPayload,
    admin: AdminActual = Depends(requiere_super_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if admin_tramites_repository.obtener_organismo_id_por_nombre(conn, request.nombre) is not None:
            raise HTTPException(status_code=409, detail="Ya existe un organismo con ese nombre")
        organismo_id = admin_tramites_repository.crear_organismo(conn, request.nombre)
        conn.commit()
    return {"id": organismo_id, "nombre": request.nombre}


class ContactoEstadoPayload(BaseModel):
    estado: Literal["pendiente", "resuelto"]


@app.get("/admin/contacto")
def admin_listar_contacto(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = admin.organismo_id if admin.rol == "admin_organismo" else None
        return contacto_repository.listar_solicitudes(conn, organismo_id)


def _verificar_solicitud_de_mi_organismo(conn, admin: AdminActual, solicitud: dict | None) -> None:
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if admin.rol == "admin_organismo" and solicitud["organismo_id"] != admin.organismo_id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")


@app.get("/admin/contacto/{solicitud_id}")
def admin_obtener_contacto(
    solicitud_id: uuid.UUID, admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
        solicitud = contacto_repository.obtener_solicitud(conn, str(solicitud_id))
        _verificar_solicitud_de_mi_organismo(conn, admin, solicitud)
        mensajes = admin_chats_repository.obtener_mensajes_completos(conn, solicitud["session_id"])
    return {**solicitud, "mensajes": mensajes}


@app.put("/admin/contacto/{solicitud_id}")
def admin_editar_estado_contacto(
    solicitud_id: uuid.UUID,
    request: ContactoEstadoPayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        solicitud = contacto_repository.obtener_solicitud(conn, str(solicitud_id))
        _verificar_solicitud_de_mi_organismo(conn, admin, solicitud)
        contacto_repository.actualizar_estado(conn, str(solicitud_id), request.estado)
        conn.commit()
    return {"ok": True}
