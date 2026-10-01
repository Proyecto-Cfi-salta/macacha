import uuid

from fastapi.testclient import TestClient

from agent import api, feedback, sessions
from agent.admin import chats_repository, feedback_repository
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
from agent.api import obtener_pool


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


def _organismo(conn, nombre):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def _tramite(conn, tramite_id, organismo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial) VALUES (%s, %s, '', %s)",
            (tramite_id, organismo_id, tramite_id),
        )


def _cita(tramite_id):
    return [
        {
            "id": f"call_{tramite_id}",
            "type": "function",
            "function": {"name": "obtener_requisitos", "arguments": f'{{"tramite_id": "{tramite_id}"}}'},
        }
    ]


def _sesion_votada(conn, util, motivo=None, comentario=None, tramite_id=None):
    """Crea una sesión con una respuesta final votada; devuelve (session_id, mensaje_id)."""
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    if tramite_id:
        sessions.guardar_mensaje(conn, session_id, rol="assistant", tool_calls=_cita(tramite_id))
    mensaje_id = sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido="respuesta")
    feedback.guardar_voto(conn, session_id, mensaje_id, util, motivo, comentario)
    conn.commit()
    return session_id, mensaje_id


# ---------- detalle y listado ----------


def test_detalle_incluye_id_y_feedback_en_mensajes_del_asistente(db_conn, clean_db):
    session_id, mensaje_id = _sesion_votada(db_conn, False, "otro", "mal")
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    asistente = next(m for m in mensajes if m.get("contenido") == "respuesta")
    usuario = next(m for m in mensajes if m["rol"] == "user")
    assert asistente["id"] == mensaje_id
    assert asistente["feedback"] == {"util": False, "motivo": "otro", "comentario": "mal"}
    assert "id" in usuario
    assert "feedback" not in usuario


def test_detalle_feedback_es_none_si_el_asistente_no_fue_votado(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta")
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    assert mensajes[0]["feedback"] is None


def test_listado_incluye_votos_por_sesion(db_conn, clean_db):
    session_id, _ = _sesion_votada(db_conn, False)
    sin_votos = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, sin_votos)
    db_conn.commit()

    sesiones = {s["id"]: s for s in chats_repository.listar_sesiones(db_conn, page=1, page_size=20)}

    assert (sesiones[session_id]["votos_positivos"], sesiones[session_id]["votos_negativos"]) == (0, 1)
    assert (sesiones[sin_votos]["votos_positivos"], sesiones[sin_votos]["votos_negativos"]) == (0, 0)


def test_listado_de_organismo_incluye_votos_por_sesion(db_conn, clean_db):
    organismo = _organismo(db_conn, "Registro Civil")
    _tramite(db_conn, "RC-0001", organismo)
    session_id, _ = _sesion_votada(db_conn, True, tramite_id="RC-0001")

    sesiones, total = chats_repository.listar_sesiones_de_organismo(db_conn, organismo, page=1, page_size=20)

    assert total == 1
    assert (sesiones[0]["votos_positivos"], sesiones[0]["votos_negativos"]) == (1, 0)


# ---------- métricas ----------


def test_metricas_sin_votos_devuelven_ceros_y_porcentaje_nulo(db_conn, clean_db):
    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert metricas["total"] == 0
    assert metricas["positivos"] == 0
    assert metricas["negativos"] == 0
    assert metricas["porcentaje_util"] is None
    assert metricas["motivos"] == []
    assert metricas["sin_motivo"] == 0
    assert metricas["por_dia"] == []
    assert metricas["comentarios_recientes"] == []
    assert metricas["por_organismo"] == []


def test_metricas_totales_y_porcentaje(db_conn, clean_db):
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, False, "faltaba_info")

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert (metricas["total"], metricas["positivos"], metricas["negativos"]) == (4, 3, 1)
    assert metricas["porcentaje_util"] == 75.0


def test_metricas_motivos_ordenados_y_sin_motivo(db_conn, clean_db):
    _sesion_votada(db_conn, False, "poco_clara")
    _sesion_votada(db_conn, False, "faltaba_info")
    _sesion_votada(db_conn, False, "faltaba_info")
    _sesion_votada(db_conn, False)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert metricas["motivos"] == [
        {"motivo": "faltaba_info", "cantidad": 2},
        {"motivo": "poco_clara", "cantidad": 1},
    ]
    assert metricas["sin_motivo"] == 1


def test_metricas_comentarios_recientes_solo_negativos_con_comentario(db_conn, clean_db):
    _sesion_votada(db_conn, False, "otro", "Primer comentario")
    _sesion_votada(db_conn, False, "otro")
    _sesion_votada(db_conn, True)
    _, ultimo = _sesion_votada(db_conn, False, "poco_clara", "Segundo comentario")

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    comentarios = metricas["comentarios_recientes"]
    assert [c["comentario"] for c in comentarios] == ["Segundo comentario", "Primer comentario"]
    assert comentarios[0]["mensaje_id"] == ultimo
    assert comentarios[0]["motivo"] == "poco_clara"


def test_metricas_por_dia_agrupa_votos(db_conn, clean_db):
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, False)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert len(metricas["por_dia"]) == 1
    assert metricas["por_dia"][0]["positivos"] == 1
    assert metricas["por_dia"][0]["negativos"] == 1


def test_metricas_por_organismo_cuenta_en_cada_organismo_citado_y_sin_tramite(db_conn, clean_db):
    rc = _organismo(db_conn, "Registro Civil")
    tr = _organismo(db_conn, "Secretaría de Trabajo")
    _tramite(db_conn, "RC-0001", rc)
    _tramite(db_conn, "TR-0001", tr)
    _sesion_votada(db_conn, True, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, tramite_id="TR-0001")
    _sesion_votada(db_conn, True)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    por_organismo = {f["organismo"]: (f["positivos"], f["negativos"]) for f in metricas["por_organismo"]}
    assert por_organismo == {
        "Registro Civil": (1, 1),
        "Secretaría de Trabajo": (0, 1),
        "Sin trámite": (1, 0),
    }
    assert metricas["por_organismo"][0]["organismo"] == "Registro Civil"


def test_metricas_de_admin_organismo_solo_cuentan_sus_sesiones(db_conn, clean_db):
    rc = _organismo(db_conn, "Registro Civil")
    tr = _organismo(db_conn, "Secretaría de Trabajo")
    _tramite(db_conn, "RC-0001", rc)
    _tramite(db_conn, "TR-0001", tr)
    _sesion_votada(db_conn, True, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, "otro", "Comentario de trabajo", tramite_id="TR-0001")
    _sesion_votada(db_conn, False)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=rc)

    assert (metricas["total"], metricas["positivos"], metricas["negativos"]) == (1, 1, 0)
    assert metricas["comentarios_recientes"] == []
    assert metricas["por_organismo"] == [{"organismo": "Registro Civil", "positivos": 1, "negativos": 0}]


# ---------- endpoint ----------


def _login(client, conn, rol="super_admin", organismo_id=None, email="admin@macacha.gob.ar"):
    admin_repository.crear_admin(conn, email, admin_security.hash_password("secreta123"), rol, organismo_id)
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": "secreta123"})


def test_endpoint_metricas_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    try:
        respuesta = TestClient(api.app, base_url="https://testserver").get("/admin/feedback/metricas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_endpoint_metricas_devuelve_el_resumen_para_super_admin(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, False, "otro", "mal")
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _login(client, db_conn)
        respuesta = client.get("/admin/feedback/metricas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["total"], cuerpo["positivos"], cuerpo["negativos"]) == (2, 1, 1)
    assert cuerpo["porcentaje_util"] == 50.0


def test_endpoint_metricas_filtra_por_organismo_del_admin(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    rc = _organismo(db_conn, "Registro Civil")
    tr = _organismo(db_conn, "Secretaría de Trabajo")
    _tramite(db_conn, "RC-0001", rc)
    _tramite(db_conn, "TR-0001", tr)
    _sesion_votada(db_conn, True, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, tramite_id="TR-0001")
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _login(client, db_conn, rol="admin_organismo", organismo_id=rc, email="rc@macacha.gob.ar")
        respuesta = client.get("/admin/feedback/metricas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 1
