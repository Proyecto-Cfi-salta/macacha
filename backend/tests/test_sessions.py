import uuid

from agent import sessions


def test_crear_sesion_si_no_existe_es_idempotente(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM sesiones WHERE id = %s", (session_id,))
        assert cur.fetchone()[0] == 1


def test_guardar_mensaje_y_obtener_historial_en_orden(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

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
                "function": {"name": "buscar_tramite", "arguments": "{}"},
            }
        ],
    )
    sessions.guardar_mensaje(db_conn, session_id, rol="tool", contenido="[]", tool_call_id="call_1")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta final")
    db_conn.commit()

    historial = sessions.obtener_historial(db_conn, session_id)

    assert [m["role"] for m in historial] == ["user", "assistant", "tool", "assistant"]
    assert historial[0]["content"] == "hola"
    assert historial[1]["tool_calls"][0]["function"]["name"] == "buscar_tramite"
    assert historial[2]["tool_call_id"] == "call_1"
    assert historial[3]["content"] == "respuesta final"


def test_obtener_mensajes_visibles_excluye_tool_calling_interno(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

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
                "function": {"name": "buscar_tramite", "arguments": "{}"},
            }
        ],
    )
    sessions.guardar_mensaje(db_conn, session_id, rol="tool", contenido="[]", tool_call_id="call_1")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta final")
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert [m["rol"] for m in visibles] == ["user", "assistant"]
    assert [m["contenido"] for m in visibles] == ["hola", "respuesta final"]


def test_guardar_mensaje_persiste_proveedor(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="hola", proveedor="gemini")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT proveedor FROM mensajes WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] == "gemini"


def test_guardar_mensaje_sin_proveedor_persiste_null(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT proveedor FROM mensajes WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] is None


def test_guardar_mensaje_devuelve_el_id_del_mensaje_insertado(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

    mensaje_id = sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="hola")
    db_conn.commit()

    assert isinstance(mensaje_id, str)
    with db_conn.cursor() as cur:
        cur.execute("SELECT contenido FROM mensajes WHERE id = %s", (mensaje_id,))
        assert cur.fetchone()[0] == "hola"


def test_mensajes_visibles_incluyen_id_votable_y_feedback_nulo(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    id_usuario = sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    id_asistente = sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta")
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert visibles[0]["id"] == id_usuario
    assert visibles[0]["votable"] is False
    assert visibles[0]["feedback"] is None
    assert visibles[1]["id"] == id_asistente
    assert visibles[1]["votable"] is True
    assert visibles[1]["feedback"] is None


def test_mensajes_visibles_incluyen_el_voto_guardado(db_conn, clean_db):
    from agent import feedback

    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    id_asistente = sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta")
    feedback.guardar_voto(db_conn, session_id, id_asistente, util=False, motivo="poco_clara", comentario="no entendí")
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert visibles[0]["feedback"] == {"util": False, "motivo": "poco_clara", "comentario": "no entendí"}


def test_mensaje_intermedio_con_contenido_y_tool_calls_no_es_votable(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido="Dejame buscar eso…",
        tool_calls=[{"id": "c1", "type": "function", "function": {"name": "buscar_tramite", "arguments": "{}"}}],
    )
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert visibles[0]["votable"] is False
