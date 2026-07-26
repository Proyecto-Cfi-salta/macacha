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


def test_editar_tramite_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.put(
            "/admin/tramites/RC-0001", json={"organismo": "x", "nombre_oficial": "y"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_editar_tramite_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(
            "/admin/tramites/RC-9999", json={"organismo": "Registro Civil", "nombre_oficial": "x"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_editar_tramite_payload_invalido_devuelve_422(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/tramites/RC-0001", json={"organismo": "", "nombre_oficial": "x"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422


def _payload_edicion(**overrides):
    payload = {
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
        "objetivo": "",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "Gratis",
        "modalidad": "",
        "duracion": "",
        "telefono_contacto": "",
        "email_contacto": "",
        "problemas_frecuentes": [],
        "sinonimos": [],
        "keywords": [],
        "enlaces_oficiales": [],
        "preguntas_frecuentes": [],
    }
    payload.update(overrides)
    return payload


def test_editar_tramite_exitoso_crea_version_nueva(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
        "objetivo": "",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "Gratis",
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
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, compute_content_hash(snapshot), snapshot, chunks, [[0.0] * 1536]
    )
    db_conn.commit()

    payload = _payload_edicion(costo="Con costo")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/tramites/RC-0001", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"tramite_id": "RC-0001", "numero_version": 2, "cambios": True}


def test_editar_tramite_falla_de_embeddings_no_escribe_nada(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
        "objetivo": "",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "Gratis",
        "modalidad": "",
        "duracion": "",
        "telefono_contacto": "",
        "email_contacto": "",
        "problemas_frecuentes": [],
        "sinonimos": [],
        "keywords": [],
        "enlaces_oficiales": [],
        "preguntas_frecuentes": [{"pregunta": "p", "respuesta": "r"}],
        "faq_generadas_automaticamente": False,
    }

    chunks = [{"tipo_chunk": "faq", "texto": "p r", "fuente_url": None}]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, compute_content_hash(snapshot), snapshot, chunks, [[0.0] * 1536]
    )
    db_conn.commit()

    payload = _payload_edicion(
        costo="Con costo cambiado",
        preguntas_frecuentes=[{"pregunta": "nueva", "respuesta": "resp"}],
    )

    class _FakeOpenAIClientRoto:
        def generate_embeddings(self, texts):
            raise RuntimeError("401 de OpenAI")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClientRoto()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/tramites/RC-0001", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 502
    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    assert vigente["numero_version"] == 1


def test_crear_tramite_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post("/admin/tramites", json={"organismo": "x", "nombre_oficial": "y"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_crear_tramite_payload_invalido_devuelve_422(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post(
            "/admin/tramites", json={"organismo": "Registro Civil", "nombre_oficial": ""}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422


def test_crear_tramite_exitoso_genera_id_y_version_uno(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    payload = {
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Trámite Nuevo",
        "descripcion": "Descripción",
        "objetivo": "",
        "requisitos": [],
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
    }

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post("/admin/tramites", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tramite_id"].startswith("RC-")
    assert cuerpo["numero_version"] == 1
