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


def test_obtener_mensajes_completos_incluye_proveedor_cuando_no_es_null(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(
        db_conn, session_id, rol="assistant", contenido="respuesta", proveedor="gemini"
    )
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    assert "proveedor" not in mensajes[0]
    assert mensajes[1]["proveedor"] == "gemini"


def _crear_organismo(conn, nombre):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def _crear_tramite(conn, tramite_id, organismo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial) VALUES (%s, %s, '', %s)",
            (tramite_id, organismo_id, tramite_id),
        )


def _mensaje_cita_tramite(call_id, tramite_id):
    return [
        {
            "id": call_id,
            "type": "function",
            "function": {"name": "obtener_requisitos", "arguments": f'{{"tramite_id": "{tramite_id}"}}'},
        }
    ]


def test_listar_sesiones_de_organismo_incluye_solo_sesiones_con_tramite_propio(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    organismo_b = _crear_organismo(db_conn, "Rentas")
    _crear_tramite(db_conn, "RC-0001", organismo_a)
    _crear_tramite(db_conn, "RE-0001", organismo_b)

    sesion_a = str(uuid.uuid4())
    sesion_b = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_a, datetime.now(timezone.utc))
    _crear_sesion(db_conn, sesion_b, datetime.now(timezone.utc) + timedelta(minutes=1))
    sessions.guardar_mensaje(
        db_conn, sesion_a, rol="assistant", tool_calls=_mensaje_cita_tramite("call_1", "RC-0001")
    )
    sessions.guardar_mensaje(
        db_conn, sesion_b, rol="assistant", tool_calls=_mensaje_cita_tramite("call_2", "RE-0001")
    )
    db_conn.commit()

    sesiones, total = chats_repository.listar_sesiones_de_organismo(
        db_conn, organismo_a, page=1, page_size=20
    )

    assert total == 1
    assert [s["id"] for s in sesiones] == [sesion_a]


def test_listar_sesiones_de_organismo_excluye_sesiones_sin_tramites_citados(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    sesion_sin_citas = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_sin_citas, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, sesion_sin_citas, rol="user", contenido="hola")
    db_conn.commit()

    sesiones, total = chats_repository.listar_sesiones_de_organismo(
        db_conn, organismo_a, page=1, page_size=20
    )

    assert total == 0
    assert sesiones == []


def test_listar_sesiones_de_organismo_pagina_el_resultado_filtrado(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    _crear_tramite(db_conn, "RC-0001", organismo_a)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    base = datetime.now(timezone.utc)
    for i, sesion_id in enumerate(ids):
        _crear_sesion(db_conn, sesion_id, base + timedelta(minutes=i))
        sessions.guardar_mensaje(
            db_conn, sesion_id, rol="assistant", tool_calls=_mensaje_cita_tramite(f"call_{i}", "RC-0001")
        )
    db_conn.commit()

    sesiones, total = chats_repository.listar_sesiones_de_organismo(
        db_conn, organismo_a, page=1, page_size=2
    )

    assert total == 3
    assert len(sesiones) == 2
    assert sesiones[0]["id"] == ids[2]


def test_sesion_pertenece_a_organismo_true_si_cito_un_tramite_propio(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    _crear_tramite(db_conn, "RC-0001", organismo_a)
    sesion_id = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn, sesion_id, rol="assistant", tool_calls=_mensaje_cita_tramite("call_1", "RC-0001")
    )
    db_conn.commit()

    assert chats_repository.sesion_pertenece_a_organismo(db_conn, sesion_id, organismo_a) is True


def test_sesion_pertenece_a_organismo_false_si_no_cito_nada_de_ese_organismo(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    organismo_b = _crear_organismo(db_conn, "Rentas")
    _crear_tramite(db_conn, "RE-0001", organismo_b)
    sesion_id = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn, sesion_id, rol="assistant", tool_calls=_mensaje_cita_tramite("call_1", "RE-0001")
    )
    db_conn.commit()

    assert chats_repository.sesion_pertenece_a_organismo(db_conn, sesion_id, organismo_a) is False


def test_sesion_pertenece_a_organismo_false_si_no_cito_nada(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    sesion_id = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, sesion_id, rol="user", contenido="hola")
    db_conn.commit()

    assert chats_repository.sesion_pertenece_a_organismo(db_conn, sesion_id, organismo_a) is False
