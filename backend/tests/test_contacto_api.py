import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent import api, sessions
from agent.api import obtener_pool
from ingest import repository as repo


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


def _payload(session_id, **overrides):
    payload = {
        "session_id": session_id,
        "tramite_id": None,
        "nombre": "Juan Pérez",
        "email": "juan@x.com",
        "telefono": "3871234567",
        "consulta": "Necesito ayuda con mi trámite",
    }
    payload.update(overrides)
    return payload


def test_post_contacto_crea_solicitud_sin_tramite(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail") as enviar_mail_mock:
            respuesta = client.post("/contacto", json=_payload(session_id))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    enviar_mail_mock.assert_called_once()


def test_post_contacto_resuelve_organismo_desde_tramite(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail"):
            respuesta = client.post("/contacto", json=_payload(session_id, tramite_id="RC-0001"))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    with db_conn.cursor() as cur:
        cur.execute("SELECT organismo_id FROM solicitudes_contacto WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] == organismo_id


def test_post_contacto_persiste_aunque_el_mail_falle(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail", side_effect=RuntimeError("SMTP caído")):
            respuesta = client.post("/contacto", json=_payload(session_id))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM solicitudes_contacto WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] == 1


def test_post_contacto_crea_sesion_si_no_existe(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    # A propósito NO se llama a sessions.crear_sesion_si_no_existe ni se
    # inserta en `sesiones`: reproduce el caso del botón "¿Necesitás hablar
    # con una persona?" clickeado antes de enviar ningún mensaje de chat.

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail") as enviar_mail_mock:
            respuesta = client.post("/contacto", json=_payload(session_id))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    enviar_mail_mock.assert_called_once()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM sesiones WHERE id = %s", (session_id,))
        assert cur.fetchone()[0] == 1


def test_post_contacto_campo_faltante_devuelve_422(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        payload = _payload(session_id)
        del payload["nombre"]
        respuesta = client.post("/contacto", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422
