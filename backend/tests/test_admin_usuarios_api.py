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


def _crear_admin_y_loguear(client, conn, rol="super_admin", organismo_id=None, email="admin@macacha.gob.ar"):
    password = "secreta123"
    admin_repository.crear_admin(conn, email, admin_security.hash_password(password), rol, organismo_id)
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": password})


def _crear_organismo(conn, nombre):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def test_listar_usuarios_requiere_super_admin(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = _crear_organismo(db_conn, "Registro Civil")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_id)
        respuesta = client.get("/admin/usuarios")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 403


def test_listar_usuarios_super_admin_devuelve_lista(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/usuarios")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["email"] == "admin@macacha.gob.ar"


def test_crear_usuario_admin_organismo_requiere_organismo_id(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post(
            "/admin/usuarios",
            json={
                "email": "nuevo@macacha.gob.ar",
                "password": "secreta123",
                "rol": "admin_organismo",
                "organismo_id": None,
            },
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 400


def test_crear_usuario_super_admin_no_permite_organismo_id(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = _crear_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post(
            "/admin/usuarios",
            json={
                "email": "nuevo@macacha.gob.ar",
                "password": "secreta123",
                "rol": "super_admin",
                "organismo_id": organismo_id,
            },
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 400


def test_crear_usuario_email_duplicado_devuelve_409(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post(
            "/admin/usuarios",
            json={
                "email": "admin@macacha.gob.ar",
                "password": "secreta123",
                "rol": "super_admin",
                "organismo_id": None,
            },
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 409


def test_crear_usuario_exitoso(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = _crear_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post(
            "/admin/usuarios",
            json={
                "email": "nuevo@macacha.gob.ar",
                "password": "secreta123",
                "rol": "admin_organismo",
                "organismo_id": organismo_id,
            },
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    creado = admin_repository.obtener_admin_por_email(db_conn, "nuevo@macacha.gob.ar")
    assert creado["rol"] == "admin_organismo"
    assert creado["organismo_id"] == organismo_id


def test_editar_usuario_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(
            "/admin/usuarios/00000000-0000-0000-0000-000000000000",
            json={"rol": "super_admin", "organismo_id": None, "activo": True, "password": None},
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_editar_usuario_desactiva(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    admin_repository.crear_admin(
        db_conn, "otro@macacha.gob.ar", admin_security.hash_password("secreta123"), "super_admin", None
    )
    db_conn.commit()
    otro_id = admin_repository.obtener_admin_por_email(db_conn, "otro@macacha.gob.ar")["id"]

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(
            f"/admin/usuarios/{otro_id}",
            json={"rol": "super_admin", "organismo_id": None, "activo": False, "password": None},
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    editado = admin_repository.obtener_admin_por_id(db_conn, otro_id)
    assert editado["activo"] is False


def test_crear_organismo_requiere_super_admin(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = _crear_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=organismo_id)
        respuesta = client.post("/admin/organismos", json={"nombre": "Rentas"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 403


def test_crear_organismo_exitoso(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post("/admin/organismos", json={"nombre": "Rentas"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Rentas"


def test_crear_organismo_nombre_duplicado_devuelve_409(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    _crear_organismo(db_conn, "Rentas")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post("/admin/organismos", json={"nombre": "Rentas"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 409
