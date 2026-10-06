import uuid

import pytest
from fastapi.testclient import TestClient

from agent import api, sessions
from agent.admin import contacto_repository
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


def _crear_solicitud(conn, organismo_id=None, tramite_id=None, nombre="Juan", estado="pendiente", creado_en=None):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO solicitudes_contacto
                (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta, estado, creado_en)
            VALUES (%s, %s, %s, %s, 'x@x.com', '387', 'consulta', %s, COALESCE(%s, now()))
            RETURNING id
            """,
            (session_id, tramite_id, organismo_id, nombre, estado, creado_en),
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

    assert [s["nombre"] for s in respuesta.json()["solicitudes"]] == ["Propia"]
    assert respuesta.json()["total"] == 1


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

    assert {s["nombre"] for s in respuesta.json()["solicitudes"]} == {"Con organismo", "Sin organismo"}


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


def _con_pool(db_conn):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    return TestClient(api.app, base_url="https://testserver")


def _casilla_de(db_conn, organismo_id):
    with db_conn.cursor() as cur:
        cur.execute("SELECT email_contacto FROM organismos WHERE id = %s", (organismo_id,))
        return cur.fetchone()[0]


def test_get_casillas_requiere_autenticacion(db_conn, clean_db):
    client = _con_pool(db_conn)
    try:
        respuesta = client.get("/admin/contacto/casillas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_get_casillas_super_admin_ve_todos_ordenados_y_la_ruta_no_se_confunde_con_un_id(
    db_conn, clean_db, monkeypatch
):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    rentas = repo.upsert_organismo(db_conn, "Rentas")
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/contacto/casillas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == [
        {"id": registro, "nombre": "Registro Civil", "email_contacto": None},
        {"id": rentas, "nombre": "Rentas", "email_contacto": None},
    ]


def test_get_casillas_admin_de_organismo_ve_solo_la_suya(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    propio = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_organismo(db_conn, "Rentas")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=propio)
        respuesta = client.get("/admin/contacto/casillas")
    finally:
        api.app.dependency_overrides.clear()

    assert [c["nombre"] for c in respuesta.json()] == ["Registro Civil"]


def test_put_casilla_requiere_autenticacion(db_conn, clean_db):
    client = _con_pool(db_conn)
    try:
        respuesta = client.put("/admin/contacto/casillas/1", json={"email_contacto": "a@b.co"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_put_casilla_super_admin_guarda_y_recorta(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(
            f"/admin/contacto/casillas/{registro}", json={"email_contacto": "  mesa@registro.gob.ar "}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": registro, "nombre": "Registro Civil", "email_contacto": "mesa@registro.gob.ar"}
    assert _casilla_de(db_conn, registro) == "mesa@registro.gob.ar"


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_put_casilla_vacia_o_null_borra_la_casilla_y_guarda_null(db_conn, clean_db, monkeypatch, valor):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    contacto_repository.guardar_casilla(db_conn, registro, "vieja@x.com")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(f"/admin/contacto/casillas/{registro}", json={"email_contacto": valor})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()["email_contacto"] is None
    assert _casilla_de(db_conn, registro) is None


@pytest.mark.parametrize("valor", ["sin-arroba", "a@b", "a b@c.com", "a@@b.com", "@x.com", "a" * 260 + "@x.com"])
def test_put_casilla_invalida_devuelve_422_y_no_escribe(db_conn, clean_db, monkeypatch, valor):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    contacto_repository.guardar_casilla(db_conn, registro, "vieja@x.com")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(f"/admin/contacto/casillas/{registro}", json={"email_contacto": valor})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422
    assert _casilla_de(db_conn, registro) == "vieja@x.com"


def test_put_casilla_organismo_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/contacto/casillas/99999", json={"email_contacto": "a@b.co"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_put_casilla_admin_de_organismo_edita_la_suya(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    propio = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=propio)
        respuesta = client.put(f"/admin/contacto/casillas/{propio}", json={"email_contacto": "mesa@x.com"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert _casilla_de(db_conn, propio) == "mesa@x.com"


@pytest.mark.parametrize("valor", ["mesa@x.com", "esto-no-es-un-email"])
def test_put_casilla_admin_de_organismo_sobre_otro_organismo_devuelve_404_sin_escribir(
    db_conn, clean_db, monkeypatch, valor
):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    propio = repo.upsert_organismo(db_conn, "Registro Civil")
    ajeno = repo.upsert_organismo(db_conn, "Rentas")
    contacto_repository.guardar_casilla(db_conn, ajeno, "original@x.com")
    db_conn.commit()

    client = _con_pool(db_conn)
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=propio)
        respuesta = client.put(f"/admin/contacto/casillas/{ajeno}", json={"email_contacto": valor})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404
    assert _casilla_de(db_conn, ajeno) == "original@x.com"


def _listar(client, **params):
    return client.get("/admin/contacto", params=params)


def _con_super_admin(db_conn, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    _crear_admin_y_loguear(client, db_conn)
    return client


def test_listado_pone_los_pendientes_primero_y_los_mas_nuevos_arriba(db_conn, clean_db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    _crear_solicitud(db_conn, nombre="resuelta-vieja", estado="resuelto", creado_en=base)
    _crear_solicitud(db_conn, nombre="pendiente-vieja", creado_en=base + timedelta(days=1))
    _crear_solicitud(db_conn, nombre="resuelta-nueva", estado="resuelto", creado_en=base + timedelta(days=4))
    _crear_solicitud(db_conn, nombre="pendiente-nueva", creado_en=base + timedelta(days=3))
    client = _con_super_admin(db_conn, monkeypatch)
    try:
        respuesta = _listar(client)
    finally:
        api.app.dependency_overrides.clear()

    assert [s["nombre"] for s in respuesta.json()["solicitudes"]] == [
        "pendiente-nueva", "pendiente-vieja", "resuelta-nueva", "resuelta-vieja",
    ]


def test_listado_se_pagina_sin_repetir_ni_perder_solicitudes(db_conn, clean_db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    base = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    for i in range(5):
        _crear_solicitud(db_conn, nombre=f"s{i}", creado_en=base + timedelta(hours=i))
    client = _con_super_admin(db_conn, monkeypatch)
    try:
        paginas = [_listar(client, page=n, page_size=2).json() for n in (1, 2, 3)]
        fuera = _listar(client, page=4, page_size=2).json()
    finally:
        api.app.dependency_overrides.clear()

    assert [len(p["solicitudes"]) for p in paginas] == [2, 2, 1]
    assert [s["nombre"] for p in paginas for s in p["solicitudes"]] == ["s4", "s3", "s2", "s1", "s0"]
    assert all(p["total"] == 5 and p["page_size"] == 2 for p in paginas)
    assert [p["page"] for p in paginas] == [1, 2, 3]
    assert fuera["solicitudes"] == [] and fuera["total"] == 5


def test_el_total_del_admin_de_organismo_cuenta_solo_las_suyas(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    propio = repo.upsert_organismo(db_conn, "Registro Civil")
    ajeno = repo.upsert_organismo(db_conn, "Rentas")
    for i in range(3):
        _crear_solicitud(db_conn, organismo_id=propio, nombre=f"p{i}")
    _crear_solicitud(db_conn, organismo_id=ajeno, nombre="ajena")
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn, rol="admin_organismo", organismo_id=propio)
        respuesta = _listar(client, page_size=2)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.json()["total"] == 3
    assert len(respuesta.json()["solicitudes"]) == 2


@pytest.mark.parametrize("params", [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}])
def test_listado_rechaza_paginacion_invalida(db_conn, clean_db, monkeypatch, params):
    client = _con_super_admin(db_conn, monkeypatch)
    try:
        respuesta = _listar(client, **params)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422
