import pytest
from fastapi import HTTPException

from agent.admin import dependencies, security


class _FakeRequest:
    def __init__(self, cookies: dict):
        self.cookies = cookies


def test_requiere_admin_sin_cookie_devuelve_401():
    with pytest.raises(HTTPException) as exc_info:
        dependencies.requiere_admin(_FakeRequest({}))
    assert exc_info.value.status_code == 401


def test_requiere_admin_con_token_invalido_devuelve_401(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    with pytest.raises(HTTPException) as exc_info:
        dependencies.requiere_admin(_FakeRequest({"admin_session": "token-basura"}))
    assert exc_info.value.status_code == 401


def test_requiere_admin_con_token_valido_devuelve_admin_actual(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token = security.crear_token({"id": "admin-1", "rol": "admin_organismo", "organismo_id": 7})

    admin = dependencies.requiere_admin(_FakeRequest({"admin_session": token}))

    assert admin == dependencies.AdminActual(id="admin-1", rol="admin_organismo", organismo_id=7)


def test_requiere_super_admin_rechaza_admin_organismo():
    admin = dependencies.AdminActual(id="admin-1", rol="admin_organismo", organismo_id=7)
    with pytest.raises(HTTPException) as exc_info:
        dependencies.requiere_super_admin(admin)
    assert exc_info.value.status_code == 403


def test_requiere_super_admin_permite_super_admin():
    admin = dependencies.AdminActual(id="admin-1", rol="super_admin", organismo_id=None)
    assert dependencies.requiere_super_admin(admin) == admin
