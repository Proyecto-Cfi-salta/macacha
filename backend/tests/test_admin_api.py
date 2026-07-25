import uuid

from fastapi.testclient import TestClient

from agent import api
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


def _crear_admin(conn, email="admin@macacha.gob.ar", password="secreta123"):
    admin_repository.crear_admin(conn, email, admin_security.hash_password(password))
    conn.commit()
    return email, password


def test_login_credenciales_validas_setea_cookie(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post("/admin/login", json={"email": email, "password": password})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"email": email}
    assert "admin_session" in respuesta.cookies


def test_login_password_incorrecta_devuelve_401(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, _ = _crear_admin(db_conn)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post("/admin/login", json={"email": email, "password": "incorrecta"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_login_email_inexistente_devuelve_401(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post(
            "/admin/login", json={"email": "no-existe@macacha.gob.ar", "password": "cualquiera"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_me_sin_cookie_devuelve_401(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.get("/admin/me")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_me_con_cookie_valida_devuelve_email(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get("/admin/me")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"email": email}


def test_logout_borra_la_cookie(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        client.post("/admin/logout")
        respuesta = client.get("/admin/me")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401
