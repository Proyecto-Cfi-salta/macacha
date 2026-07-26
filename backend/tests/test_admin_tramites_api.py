from fastapi.testclient import TestClient

from agent import api
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
from agent.api import obtener_pool
from ingest import repository as repo
from ingest.hashing import compute_content_hash


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


class _FakeOpenAIClient:
    def generate_embeddings(self, texts):
        return [[0.0] * 1536 for _ in texts]


def _crear_admin_y_loguear(client, conn):
    email, password = "admin@macacha.gob.ar", "secreta123"
    admin_repository.crear_admin(conn, email, admin_security.hash_password(password))
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": password})


def test_listar_tramites_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.get("/admin/tramites")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_listar_tramites_devuelve_lista(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "telefono_contacto": "",
        "email_contacto": "",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, [[0.0] * 1536])
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/tramites")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["id"] == "RC-0001"


def test_listar_organismos_devuelve_nombres(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/organismos")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == ["Registro Civil"]


def test_obtener_tramite_admin_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/tramites/RC-9999")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_obtener_tramite_admin_devuelve_snapshot_completo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "desc",
        "objetivo": "obj",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "",
        "modalidad": "",
        "duracion": "",
        "telefono_contacto": "",
        "email_contacto": "",
        "problemas_frecuentes": [],
        "sinonimos": [],
        "keywords": [],
        "enlaces_oficiales": [],
        "preguntas_frecuentes": [],
        "faq_generadas_automaticamente": False,
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, [[0.0] * 1536])
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre_oficial"] == "Actas Regulares"
    assert cuerpo["requisitos"] == ["DNI"]
    assert "id" not in cuerpo
