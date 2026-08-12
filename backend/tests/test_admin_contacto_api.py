import uuid

from fastapi.testclient import TestClient

from agent import api, sessions
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
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


def _crear_admin_y_loguear(client, conn, rol="super_admin", organismo_id=None, email="admin@macacha.gob.ar"):
    password = "secreta123"
    admin_repository.crear_admin(conn, email, admin_security.hash_password(password), rol, organismo_id)
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": password})


def _crear_solicitud(conn, organismo_id=None, tramite_id=None, nombre="Juan"):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO solicitudes_contacto (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta)
            VALUES (%s, %s, %s, %s, 'x@x.com', '387', 'consulta')
            RETURNING id
            """,
            (session_id, tramite_id, organismo_id, nombre),
        )
        solicitud_id = str(cur.fetchone()[0])
    conn.commit()
    return solicitud_id


def test_listar_contacto_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.get("/admin/contacto")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_admin_organismo_solo_ve_sus_solicitudes(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_ajeno = repo.upsert_organismo(db_conn, "Rentas")
    _crear_solicitud(db_conn, organismo_id=organismo_propio, nombre="Propia")
    _crear_solicitud(db_conn, organismo_id=organismo_ajeno, nombre="Ajena")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_propio)
        respuesta = client.get("/admin/contacto")
    finally:
        api.app.dependency_overrides.clear()

    assert [s["nombre"] for s in respuesta.json()] == ["Propia"]


def test_super_admin_ve_todas_las_solicitudes(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_solicitud(db_conn, organismo_id=organismo_id, nombre="Con organismo")
    _crear_solicitud(db_conn, organismo_id=None, nombre="Sin organismo")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/contacto")
    finally:
        api.app.dependency_overrides.clear()

    assert {s["nombre"] for s in respuesta.json()} == {"Con organismo", "Sin organismo"}


def test_obtener_solicitud_ajena_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_ajeno = repo.upsert_organismo(db_conn, "Rentas")
    solicitud_id = _crear_solicitud(db_conn, organismo_id=organismo_ajeno)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_propio)
        respuesta = client.get(f"/admin/contacto/{solicitud_id}")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_obtener_solicitud_propia_devuelve_200(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    solicitud_id = _crear_solicitud(db_conn, organismo_id=organismo_propio)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_propio)
        respuesta = client.get(f"/admin/contacto/{solicitud_id}")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == solicitud_id


def test_editar_estado_solicitud_ajena_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_ajeno = repo.upsert_organismo(db_conn, "Rentas")
    solicitud_id = _crear_solicitud(db_conn, organismo_id=organismo_ajeno)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_propio)
        respuesta = client.put(f"/admin/contacto/{solicitud_id}", json={"estado": "resuelto"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_editar_estado_solicitud_propia(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    solicitud_id = _crear_solicitud(db_conn, organismo_id=organismo_propio)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_propio)
        respuesta = client.put(f"/admin/contacto/{solicitud_id}", json={"estado": "resuelto"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    with db_conn.cursor() as cur:
        cur.execute("SELECT estado FROM solicitudes_contacto WHERE id = %s", (solicitud_id,))
        assert cur.fetchone()[0] == "resuelto"
