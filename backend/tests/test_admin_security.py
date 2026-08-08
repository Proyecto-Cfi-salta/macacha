from datetime import datetime, timedelta, timezone

import jwt

from agent.admin import security


def test_hash_password_permite_verificar_la_password_correcta():
    hash_ = security.hash_password("secreta123")
    assert security.verify_password("secreta123", hash_) is True


def test_verify_password_rechaza_password_incorrecta():
    hash_ = security.hash_password("secreta123")
    assert security.verify_password("otra-cosa", hash_) is False


def test_crear_token_y_decodificar_token_devuelve_claims(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    admin = {"id": "admin-1", "rol": "admin_organismo", "organismo_id": 7}

    token = security.crear_token(admin)

    assert security.decodificar_token(token) == {
        "sub": "admin-1",
        "rol": "admin_organismo",
        "organismo_id": 7,
    }


def test_crear_token_con_organismo_id_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    admin = {"id": "admin-1", "rol": "super_admin", "organismo_id": None}

    token = security.crear_token(admin)

    assert security.decodificar_token(token) == {
        "sub": "admin-1",
        "rol": "super_admin",
        "organismo_id": None,
    }


def test_decodificar_token_invalido_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    assert security.decodificar_token("token-basura") is None


def test_decodificar_token_expirado_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_vencido = jwt.encode(
        {
            "sub": "admin-1",
            "rol": "admin_organismo",
            "organismo_id": 1,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        "secreto-de-test",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_vencido) is None


def test_decodificar_token_firmado_con_otro_secreto_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_ajeno = jwt.encode(
        {
            "sub": "admin-1",
            "rol": "admin_organismo",
            "organismo_id": 1,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "otro-secreto",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_ajeno) is None


def test_decodificar_token_sin_rol_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_sin_rol = jwt.encode(
        {
            "sub": "admin-1",
            "organismo_id": 1,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "secreto-de-test",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_sin_rol) is None


def test_decodificar_token_con_rol_invalido_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_rol_invalido = jwt.encode(
        {
            "sub": "admin-1",
            "rol": "editor",
            "organismo_id": 1,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "secreto-de-test",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_rol_invalido) is None


def test_decodificar_token_admin_organismo_sin_organismo_id_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_sin_organismo = jwt.encode(
        {
            "sub": "admin-1",
            "rol": "admin_organismo",
            "organismo_id": None,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "secreto-de-test",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_sin_organismo) is None
