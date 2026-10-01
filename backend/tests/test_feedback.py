import uuid

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation

from agent import api, feedback, sessions
from agent.api import obtener_pool


def _respuesta(conn, session_id=None, **kwargs):
    session_id = session_id or str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    mensaje_id = sessions.guardar_mensaje(
        conn, session_id, rol="assistant", contenido="respuesta", **kwargs
    )
    conn.commit()
    return session_id, mensaje_id


def _filas(conn, mensaje_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT util, motivo, comentario FROM feedback_respuestas WHERE mensaje_id = %s",
            (mensaje_id,),
        )
        return cur.fetchall()


def test_motivos_son_la_lista_cerrada_del_spec():
    assert feedback.MOTIVOS == (
        "no_respondio",
        "info_incorrecta",
        "faltaba_info",
        "otro_tramite",
        "desactualizada",
        "poco_clara",
        "otro",
    )


def test_mensaje_votable_true_para_respuesta_final_del_asistente(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    assert feedback.mensaje_votable(db_conn, session_id, mensaje_id) is True


def test_mensaje_votable_false_para_mensaje_de_usuario(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    mensaje_id = sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    assert feedback.mensaje_votable(db_conn, session_id, mensaje_id) is False


def test_mensaje_votable_false_para_mensaje_intermedio_con_tool_calls(db_conn, clean_db):
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "buscar_tramite", "arguments": "{}"}}]
    session_id, mensaje_id = _respuesta(db_conn, tool_calls=tool_calls)

    assert feedback.mensaje_votable(db_conn, session_id, mensaje_id) is False


def test_mensaje_votable_false_si_pertenece_a_otra_sesion(db_conn, clean_db):
    _, mensaje_id = _respuesta(db_conn)
    otra_sesion = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, otra_sesion)
    db_conn.commit()

    assert feedback.mensaje_votable(db_conn, otra_sesion, mensaje_id) is False


def test_guardar_voto_positivo_crea_la_fila(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=True)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(True, None, None)]


def test_guardar_voto_negativo_con_motivo_y_comentario(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    feedback.guardar_voto(
        db_conn, session_id, mensaje_id, util=False, motivo="faltaba_info", comentario="Faltó el costo"
    )
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, "faltaba_info", "Faltó el costo")]


def test_doble_voto_seguido_deja_una_sola_fila(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, None, None)]


def test_voto_negativo_sin_detalle_no_borra_motivo_ni_comentario_guardados(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="poco_clara", comentario="No entendí")

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, "poco_clara", "No entendí")]


def test_cambiar_a_positivo_limpia_motivo_y_comentario(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="otro", comentario="x")

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=True)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(True, None, None)]


def test_cambiar_de_positivo_a_negativo_actualiza_la_misma_fila(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=True)

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="otro_tramite")
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, "otro_tramite", None)]


def test_la_base_rechaza_un_motivo_fuera_de_la_lista(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    with pytest.raises(CheckViolation):
        feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="inventado")


def test_obtener_voto_devuelve_none_si_no_hay_voto(db_conn, clean_db):
    _, mensaje_id = _respuesta(db_conn)

    assert feedback.obtener_voto(db_conn, mensaje_id) is None


def test_obtener_voto_devuelve_el_voto_guardado(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="otro", comentario="c")
    db_conn.commit()

    assert feedback.obtener_voto(db_conn, mensaje_id) == {
        "util": False,
        "motivo": "otro",
        "comentario": "c",
    }


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        pass


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        return _FakeConnCtx(self._conn)


def _post_feedback(conn, cuerpo):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(conn)
    try:
        return TestClient(api.app).post("/feedback", json=cuerpo)
    finally:
        api.app.dependency_overrides.clear()


def test_post_feedback_positivo_guarda_el_voto(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": mensaje_id, "util": True}
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    assert _filas(db_conn, mensaje_id) == [(True, None, None)]


def test_post_feedback_negativo_con_motivo_y_comentario(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {
            "session_id": session_id,
            "mensaje_id": mensaje_id,
            "util": False,
            "motivo": "desactualizada",
            "comentario": "El costo cambió",
        },
    )

    assert respuesta.status_code == 200
    assert _filas(db_conn, mensaje_id) == [(False, "desactualizada", "El costo cambió")]


def test_post_feedback_comentario_solo_con_espacios_se_guarda_como_null(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": False, "comentario": "  \n  "},
    )

    assert respuesta.status_code == 200
    assert _filas(db_conn, mensaje_id) == [(False, None, None)]


def test_post_feedback_mensaje_de_otra_sesion_devuelve_404_y_no_escribe(db_conn, clean_db):
    _, mensaje_id = _respuesta(db_conn)
    otra_sesion = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, otra_sesion)
    db_conn.commit()

    respuesta = _post_feedback(
        db_conn, {"session_id": otra_sesion, "mensaje_id": mensaje_id, "util": True}
    )

    assert respuesta.status_code == 404
    assert _filas(db_conn, mensaje_id) == []


def test_post_feedback_mensaje_inexistente_devuelve_404(db_conn, clean_db):
    session_id, _ = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": str(uuid.uuid4()), "util": True}
    )

    assert respuesta.status_code == 404


def test_post_feedback_motivo_con_voto_positivo_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": True, "motivo": "otro"},
    )

    assert respuesta.status_code == 422
    assert _filas(db_conn, mensaje_id) == []


def test_post_feedback_comentario_con_voto_positivo_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": True, "comentario": "gracias"},
    )

    assert respuesta.status_code == 422


def test_post_feedback_motivo_fuera_de_la_lista_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": False, "motivo": "inventado"},
    )

    assert respuesta.status_code == 422


def test_post_feedback_comentario_de_mas_de_500_caracteres_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": False, "comentario": "a" * 501},
    )

    assert respuesta.status_code == 422
    assert _filas(db_conn, mensaje_id) == []


def test_post_feedback_mensaje_id_que_no_es_uuid_devuelve_422(db_conn, clean_db):
    session_id, _ = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": "no-es-un-uuid", "util": True}
    )

    assert respuesta.status_code == 422


def test_post_feedback_no_requiere_cookie_de_admin(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": mensaje_id, "util": True}
    )

    assert respuesta.status_code == 200
