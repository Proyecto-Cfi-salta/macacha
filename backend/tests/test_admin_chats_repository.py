import uuid
from datetime import datetime, timedelta, timezone

from agent import sessions
from agent.admin import chats_repository


def _crear_sesion(conn, session_id, creado_en):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sesiones (id, created_at) VALUES (%s, %s)",
            (session_id, creado_en),
        )


def test_contar_sesiones_devuelve_el_total(db_conn, clean_db):
    base = datetime.now(timezone.utc)
    _crear_sesion(db_conn, str(uuid.uuid4()), base)
    _crear_sesion(db_conn, str(uuid.uuid4()), base + timedelta(minutes=1))
    db_conn.commit()

    assert chats_repository.contar_sesiones(db_conn) == 2


def test_listar_sesiones_ordena_por_creado_en_descendente(db_conn, clean_db):
    base = datetime.now(timezone.utc)
    id_vieja = str(uuid.uuid4())
    id_nueva = str(uuid.uuid4())
    _crear_sesion(db_conn, id_vieja, base)
    _crear_sesion(db_conn, id_nueva, base + timedelta(minutes=5))
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert [s["id"] for s in sesiones] == [id_nueva, id_vieja]


def test_listar_sesiones_pagina_fuera_de_rango_devuelve_lista_vacia(db_conn, clean_db):
    _crear_sesion(db_conn, str(uuid.uuid4()), datetime.now(timezone.utc))
    db_conn.commit()

    assert chats_repository.listar_sesiones(db_conn, page=5, page_size=20) == []


def test_listar_sesiones_cuenta_solo_mensajes_visibles(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="en qué te ayudo?")
    sessions.guardar_mensaje(db_conn, session_id, rol="tool", contenido="{}", tool_call_id="call_1")
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["cantidad_mensajes"] == 2


def test_listar_sesiones_trunca_ultimo_mensaje_a_140_caracteres(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    mensaje_largo = "a" * 200
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido=mensaje_largo)
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["ultimo_mensaje"] == "a" * 140 + "…"


def test_listar_sesiones_sin_mensajes_devuelve_valores_vacios(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["ultimo_mensaje"] is None
    assert sesiones[0]["cantidad_mensajes"] == 0
    assert sesiones[0]["tramites_citados"] == []


def test_listar_sesiones_extrae_tramites_citados_deduplicados_en_orden(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RC-0002"}'},
            }
        ],
    )
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "obtener_pasos", "arguments": '{"tramite_id": "RC-0001"}'},
            },
            {
                "id": "call_3",
                "type": "function",
                "function": {"name": "obtener_pasos", "arguments": '{"tramite_id": "RC-0002"}'},
            },
        ],
    )
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["tramites_citados"] == ["RC-0002", "RC-0001"]


def test_listar_sesiones_ignora_tool_call_con_argumentos_invalidos(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": "esto no es json valido"},
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "obtener_pasos", "arguments": '{"tramite_id": "RC-0001"}'},
            },
        ],
    )
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["tramites_citados"] == ["RC-0001"]


def test_sesion_existe(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    db_conn.commit()

    assert chats_repository.sesion_existe(db_conn, session_id) is True
    assert chats_repository.sesion_existe(db_conn, str(uuid.uuid4())) is False


def test_obtener_mensajes_completos_incluye_tool_calls_y_mensajes_tool(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RC-0001"}'},
            }
        ],
    )
    sessions.guardar_mensaje(
        db_conn, session_id, rol="tool", contenido='["DNI"]', tool_call_id="call_1"
    )
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="Necesitás tu DNI.")
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    assert [m["rol"] for m in mensajes] == ["user", "assistant", "tool", "assistant"]
    assert mensajes[1]["tool_calls"][0]["function"]["name"] == "obtener_requisitos"
    assert mensajes[2]["tool_call_id"] == "call_1"
