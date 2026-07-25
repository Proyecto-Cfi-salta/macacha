# Admin — esqueleto (login) + sección de Chats — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el esqueleto de autenticación del panel de admin (login con JWT en cookie httpOnly) y la sección de Chats (lista paginada de sesiones + detalle con vista técnica expandible), según el spec aprobado en `docs/superpowers/specs/2026-07-24-admin-panel-chats-design.md`.

**Architecture:** Backend FastAPI existente (`backend/agent/api.py`) se extiende con endpoints `/admin/*` protegidos por una dependencia JWT; la lógica de hashing/JWT y las queries de admins/chats viven en módulos nuevos bajo `backend/agent/admin/`. Frontend Next.js existente se extiende con rutas nuevas bajo `frontend/app/admin/`, protegidas por `middleware.ts` que delega la validación de sesión al backend.

**Tech Stack:** FastAPI, psycopg3, pytest (backend) — Next.js 15 / React 19, Vitest (frontend) — `passlib[bcrypt]` para hashing, `PyJWT` para tokens.

## Global Constraints

- Todos los identificadores nuevos (funciones, variables, componentes) van en español, consistente con el resto del repo (ver `agent/orchestrator.py`, `frontend/hooks/*`).
- Sin comentarios en el código salvo que expliquen un WHY no obvio — no hay ninguno previsto en este plan.
- Backend: `psycopg[binary]>=3.2,<4` ya en uso; nuevas deps con el mismo estilo de pin (`>=X,<Y`).
- Tests de backend usan las fixtures existentes `db_conn` y `clean_db` de `backend/tests/conftest.py` contra la DB real de test — no mockear la DB.
- Tests de frontend: solo se testea lógica pura con Vitest (no hay `jsdom`/`@testing-library` instalado); páginas y componentes con DOM se verifican manualmente en el browser, siguiendo el patrón ya usado en el repo (`hooks/useTramiteActual.test.ts` testea una función pura exportada, no el componente).
- Cookie de sesión: `admin_session`, `httpOnly=True`, `secure=True`, `samesite="lax"`, `max_age=86400` (24h). Backend y frontend son orígenes distintos (`localhost:8000` / `localhost:3000`) — todo fetch a `/admin/*` desde el frontend usa `credentials:"include"`, y CORS en el backend necesita `allow_credentials=True`.
- El JWT no lleva más que `{"sub": admin_id, "exp": ...}` — el email se resuelve siempre con una lookup a `admins` por id, nunca se mete en el token.

---

## Backend

### Task 1: Tabla `admins` + dependencias nuevas

**Files:**
- Modify: `backend/db/schema.sql`
- Modify: `backend/tests/test_schema_smoke.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/requirements.txt`
- Modify: `.env.example`
- Modify: `.env`

**Interfaces:**
- Produces: tabla `admins(id UUID PK, email TEXT UNIQUE, password_hash TEXT, created_at TIMESTAMPTZ)`, usada por todas las tasks siguientes de backend.

- [ ] **Step 1: Agregar la tabla al schema**

En `backend/db/schema.sql`, al final del archivo:

```sql
CREATE TABLE IF NOT EXISTS admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Actualizar el test de smoke del schema**

En `backend/tests/test_schema_smoke.py`, agregar `"admins"` al set esperado:

```python
def test_extension_and_tables_exist(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cur.fetchone() is not None

        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = {row[0] for row in cur.fetchall()}
        assert {
            "organismos",
            "tramites",
            "tramite_versiones",
            "tramite_chunks",
            "sesiones",
            "mensajes",
            "admins",
        } <= tables
```

- [ ] **Step 3: Limpiar la tabla `admins` entre tests**

En `backend/tests/conftest.py`, agregar la línea al método `_clean`:

```python
@pytest.fixture
def clean_db():
    conn = psycopg.connect(_test_database_url(), autocommit=True)

    def _clean() -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mensajes")
            cur.execute("DELETE FROM sesiones")
            cur.execute("DELETE FROM tramite_chunks")
            cur.execute("DELETE FROM tramite_versiones")
            cur.execute("DELETE FROM tramites")
            cur.execute("DELETE FROM organismos")
            cur.execute("DELETE FROM admins")

    _clean()
    yield
    _clean()
    conn.close()
```

- [ ] **Step 4: Agregar dependencias nuevas**

En `backend/requirements.txt`, agregar dos líneas:

```
passlib[bcrypt]>=1.7,<2
pyjwt>=2.9,<3
```

- [ ] **Step 5: Agregar `ADMIN_JWT_SECRET` al ejemplo y al `.env` local**

En `.env.example`, agregar:

```
ADMIN_JWT_SECRET=changeme-generar-un-secreto-real
```

Generar un secreto real para desarrollo local:

Run: `python3 -c "import secrets; print(secrets.token_hex(32))"`

Copiar el valor impreso y agregarlo como nueva línea en `.env` (que ya existe en la raíz del repo, no versionado):

```
ADMIN_JWT_SECRET=<el-valor-generado>
```

- [ ] **Step 6: Instalar las dependencias nuevas**

Run: `cd backend && source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 7: Recrear el volumen de Postgres para aplicar el schema nuevo**

El volumen nombrado de Docker conserva el esquema viejo hasta que se recrea (ver nota en `README.md`).

Run: `docker compose down -v && docker compose up -d postgres`

Expected: el contenedor `macacha-postgres-1` arranca limpio y corre `schema.sql` de nuevo (incluye la tabla `admins`).

- [ ] **Step 8: Correr el test de smoke para confirmar la tabla nueva**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_schema_smoke.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/db/schema.sql backend/tests/test_schema_smoke.py backend/tests/conftest.py backend/requirements.txt .env.example
git commit -m "feat: agregar tabla admins y dependencias de autenticación"
```

(`.env` no se commitea — no está trackeado.)

---

### Task 2: `agent/admin/security.py` — hashing y JWT

**Files:**
- Create: `backend/agent/admin/__init__.py`
- Create: `backend/agent/admin/security.py`
- Test: `backend/tests/test_admin_security.py`

**Interfaces:**
- Consumes: nada (funciones puras, sin DB).
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`, `crear_token(admin_id: str) -> str`, `decodificar_token(token: str) -> str | None`. Usadas por Task 3 (create_admin), Task 5 (endpoints de login) y Task 6 (dependencia `requiere_admin`).

- [ ] **Step 1: Crear el paquete `agent/admin`**

```bash
mkdir -p backend/agent/admin
touch backend/agent/admin/__init__.py
```

- [ ] **Step 2: Escribir los tests que fallan**

Crear `backend/tests/test_admin_security.py`:

```python
from datetime import datetime, timedelta, timezone

import jwt

from agent.admin import security


def test_hash_password_permite_verificar_la_password_correcta():
    hash_ = security.hash_password("secreta123")
    assert security.verify_password("secreta123", hash_) is True


def test_verify_password_rechaza_password_incorrecta():
    hash_ = security.hash_password("secreta123")
    assert security.verify_password("otra-cosa", hash_) is False


def test_crear_token_y_decodificar_token_devuelve_admin_id(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token = security.crear_token("admin-1")
    assert security.decodificar_token(token) == "admin-1"


def test_decodificar_token_invalido_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    assert security.decodificar_token("token-basura") is None


def test_decodificar_token_expirado_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_vencido = jwt.encode(
        {"sub": "admin-1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        "secreto-de-test",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_vencido) is None


def test_decodificar_token_firmado_con_otro_secreto_devuelve_none(monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    token_ajeno = jwt.encode(
        {"sub": "admin-1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "otro-secreto",
        algorithm="HS256",
    )
    assert security.decodificar_token(token_ajeno) is None
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_security.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.admin.security'`

- [ ] **Step 4: Implementar `security.py`**

Crear `backend/agent/admin/security.py`:

```python
import os
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def crear_token(admin_id: str) -> str:
    payload = {
        "sub": admin_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, os.environ["ADMIN_JWT_SECRET"], algorithm="HS256")


def decodificar_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, os.environ["ADMIN_JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_security.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/admin/__init__.py backend/agent/admin/security.py backend/tests/test_admin_security.py
git commit -m "feat: hashing de contraseñas y JWT para admins"
```

---

### Task 3: `agent/admin/repository.py` — CRUD de admins

**Files:**
- Create: `backend/agent/admin/repository.py`
- Test: `backend/tests/test_admin_repository.py`

**Interfaces:**
- Consumes: nada nuevo (usa `conn` psycopg como el resto de `ingest/repository.py`).
- Produces: `crear_admin(conn, email: str, password_hash: str) -> None`, `obtener_admin_por_email(conn, email: str) -> dict | None` (`{"id": str, "email": str, "password_hash": str}`), `obtener_admin_por_id(conn, admin_id: str) -> dict | None` (`{"id": str, "email": str}`). Usadas por Task 4 (CLI) y Task 5 (endpoints).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_repository.py`:

```python
from agent.admin import repository


def test_crear_admin_y_obtener_por_email(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["email"] == "admin@macacha.gob.ar"
    assert admin["password_hash"] == "hash-1"
    assert admin["id"]


def test_obtener_admin_por_email_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_email(db_conn, "no-existe@macacha.gob.ar") is None


def test_crear_admin_con_email_repetido_actualiza_el_hash(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-viejo")
    db_conn.commit()
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-nuevo")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["password_hash"] == "hash-nuevo"


def test_obtener_admin_por_id(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()
    creado = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    admin = repository.obtener_admin_por_id(db_conn, creado["id"])

    assert admin == {"id": creado["id"], "email": "admin@macacha.gob.ar"}


def test_obtener_admin_por_id_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_id(db_conn, "00000000-0000-0000-0000-000000000000") is None
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_repository.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.admin.repository'`

- [ ] **Step 3: Implementar `repository.py`**

Crear `backend/agent/admin/repository.py`:

```python
def crear_admin(conn, email: str, password_hash: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admins (email, password_hash) VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash
            """,
            (email, password_hash),
        )


def obtener_admin_por_email(conn, email: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, password_hash FROM admins WHERE email = %s", (email,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": str(row[0]), "email": row[1], "password_hash": row[2]}


def obtener_admin_por_id(conn, admin_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM admins WHERE id = %s", (admin_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": str(row[0]), "email": row[1]}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_repository.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/repository.py backend/tests/test_admin_repository.py
git commit -m "feat: repositorio CRUD de admins"
```

---

### Task 4: `agent/admin/create_admin.py` — CLI de alta de admin

**Files:**
- Create: `backend/agent/admin/create_admin.py`
- Test: `backend/tests/test_create_admin_cli.py`

**Interfaces:**
- Consumes: `security.hash_password` (Task 2), `repository.crear_admin` (Task 3), `db.connection.get_connection` (ya existe).
- Produces: `main(argv: list[str], password_input=getpass) -> None`, ejecutable vía `python -m agent.admin.create_admin <email>`.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_create_admin_cli.py`, siguiendo el mismo patrón que `tests/test_load_cli.py`:

```python
from agent.admin import create_admin


class _FakeConn:
    def commit(self):
        pass


def test_main_crea_admin_con_password_hasheada(monkeypatch, capsys):
    llamada = {}

    monkeypatch.setattr(create_admin, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        create_admin.security, "hash_password", lambda password: f"hash-de-{password}"
    )

    def _fake_crear_admin(conn, email, password_hash):
        llamada["email"] = email
        llamada["password_hash"] = password_hash

    monkeypatch.setattr(create_admin, "crear_admin", _fake_crear_admin)

    create_admin.main(["admin@macacha.gob.ar"], password_input=lambda prompt: "secreta123")

    assert llamada == {"email": "admin@macacha.gob.ar", "password_hash": "hash-de-secreta123"}
    assert "admin@macacha.gob.ar" in capsys.readouterr().out


def test_main_sin_email_imprime_uso_y_sale(capsys):
    try:
        create_admin.main([])
        assert False, "debería haber salido con sys.exit"
    except SystemExit as exc:
        assert exc.code == 1
    assert "Uso:" in capsys.readouterr().out
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_create_admin_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.admin.create_admin'`

- [ ] **Step 3: Implementar el CLI**

Crear `backend/agent/admin/create_admin.py`:

```python
import sys
from getpass import getpass

from dotenv import load_dotenv

from agent.admin import security
from agent.admin.repository import crear_admin
from db.connection import get_connection


def main(argv: list[str], password_input=getpass) -> None:
    load_dotenv()
    if len(argv) != 1:
        print("Uso: python -m agent.admin.create_admin <email>")
        sys.exit(1)

    email = argv[0]
    password = password_input("Contraseña: ")
    password_hash = security.hash_password(password)

    conn = get_connection()
    crear_admin(conn, email, password_hash)
    conn.commit()

    print(f"Admin creado: {email}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_create_admin_cli.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/create_admin.py backend/tests/test_create_admin_cli.py
git commit -m "feat: CLI para dar de alta un admin"
```

---

### Task 5: Endpoints de autenticación (`login`, `logout`, `me`)

**Files:**
- Create: `backend/agent/admin/dependencies.py`
- Modify: `backend/agent/api.py`
- Test: `backend/tests/test_admin_api.py`

**Interfaces:**
- Consumes: `admin_security.verify_password`, `admin_security.crear_token`, `admin_security.decodificar_token` (Task 2); `admin_repository.obtener_admin_por_email`, `admin_repository.obtener_admin_por_id` (Task 3); `obtener_pool` (ya existe en `agent/api.py`).
- Produces: dependencia FastAPI `requiere_admin(request: Request) -> str` (devuelve `admin_id`, lanza `401`); endpoints `POST /admin/login`, `POST /admin/logout`, `GET /admin/me`. La dependencia `requiere_admin` la usa también Task 7.

- [ ] **Step 1: Crear la dependencia `requiere_admin`**

Crear `backend/agent/admin/dependencies.py`:

```python
from fastapi import HTTPException, Request

from agent.admin import security


def requiere_admin(request: Request) -> str:
    token = request.cookies.get("admin_session")
    if token is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    admin_id = security.decodificar_token(token)
    if admin_id is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    return admin_id
```

- [ ] **Step 2: Escribir los tests que fallan**

Crear `backend/tests/test_admin_api.py`:

```python
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
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_api.py -v`
Expected: FAIL — `404 Not Found` en los asserts de status code (las rutas `/admin/*` todavía no existen)

- [ ] **Step 4: Agregar `allow_credentials` a CORS**

En `backend/agent/api.py`, modificar el bloque de `CORSMiddleware`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 5: Agregar los imports y los tres endpoints**

En `backend/agent/api.py`, modificar la línea de import de `fastapi`:

```python
from fastapi import Depends, FastAPI, HTTPException, Request, Response
```

Agregar después de los imports existentes:

```python
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
from agent.admin.dependencies import requiere_admin
```

Agregar al final del archivo:

```python
class LoginRequest(BaseModel):
    email: str
    password: str


@app.post("/admin/login")
def admin_login(request: LoginRequest, response: Response, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin = admin_repository.obtener_admin_por_email(conn, request.email)

    if admin is None or not admin_security.verify_password(request.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = admin_security.crear_token(admin["id"])
    response.set_cookie(
        "admin_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )
    return {"email": admin["email"]}


@app.post("/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie("admin_session")
    return {"ok": True}


@app.get("/admin/me")
def admin_me(admin_id: str = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin = admin_repository.obtener_admin_por_id(conn, admin_id)

    if admin is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return {"email": admin["email"]}
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_api.py tests/test_api.py -v`
Expected: PASS (todos, incluyendo `test_cors_preflight_allows_frontend_origin` de `test_api.py` que no debe romperse con `allow_credentials=True`)

- [ ] **Step 7: Commit**

```bash
git add backend/agent/admin/dependencies.py backend/agent/api.py backend/tests/test_admin_api.py
git commit -m "feat: endpoints de login, logout y me para el admin"
```

---

### Task 6: `agent/admin/chats_repository.py` — queries de sesiones/mensajes

**Files:**
- Create: `backend/agent/admin/chats_repository.py`
- Test: `backend/tests/test_admin_chats_repository.py`

**Interfaces:**
- Consumes: `agent.sessions.guardar_mensaje` (ya existe, solo en tests).
- Produces: `contar_sesiones(conn) -> int`, `listar_sesiones(conn, page: int, page_size: int) -> list[dict]` (cada dict: `id, creado_en, cantidad_mensajes, ultimo_mensaje, tramites_citados`), `sesion_existe(conn, session_id: str) -> bool`, `obtener_mensajes_completos(conn, session_id: str) -> list[dict]` (cada dict: `rol, contenido, creado_en`, más `tool_calls`/`tool_call_id` si corresponde). Usadas por Task 7.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_chats_repository.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

from agent import sessions
from agent.admin import chats_repository


def _crear_sesion(conn, session_id, creado_en):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sesiones (id, created_at) VALUES (%s, %s)",
            (session_id, creado_en),
        )


def test_contar_sesiones_devuelve_el_total(db_conn, clean_db):
    base = datetime.now(timezone.utc)
    _crear_sesion(db_conn, str(uuid.uuid4()), base)
    _crear_sesion(db_conn, str(uuid.uuid4()), base + timedelta(minutes=1))
    db_conn.commit()

    assert chats_repository.contar_sesiones(db_conn) == 2


def test_listar_sesiones_ordena_por_creado_en_descendente(db_conn, clean_db):
    base = datetime.now(timezone.utc)
    id_vieja = str(uuid.uuid4())
    id_nueva = str(uuid.uuid4())
    _crear_sesion(db_conn, id_vieja, base)
    _crear_sesion(db_conn, id_nueva, base + timedelta(minutes=5))
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert [s["id"] for s in sesiones] == [id_nueva, id_vieja]


def test_listar_sesiones_pagina_fuera_de_rango_devuelve_lista_vacia(db_conn, clean_db):
    _crear_sesion(db_conn, str(uuid.uuid4()), datetime.now(timezone.utc))
    db_conn.commit()

    assert chats_repository.listar_sesiones(db_conn, page=5, page_size=20) == []


def test_listar_sesiones_cuenta_solo_mensajes_visibles(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="en qué te ayudo?")
    sessions.guardar_mensaje(db_conn, session_id, rol="tool", contenido="{}", tool_call_id="call_1")
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["cantidad_mensajes"] == 2


def test_listar_sesiones_trunca_ultimo_mensaje_a_140_caracteres(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    mensaje_largo = "a" * 200
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido=mensaje_largo)
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["ultimo_mensaje"] == "a" * 140 + "…"


def test_listar_sesiones_sin_mensajes_devuelve_valores_vacios(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["ultimo_mensaje"] is None
    assert sesiones[0]["cantidad_mensajes"] == 0
    assert sesiones[0]["tramites_citados"] == []


def test_listar_sesiones_extrae_tramites_citados_deduplicados_en_orden(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RC-0002"}'},
            }
        ],
    )
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "obtener_pasos", "arguments": '{"tramite_id": "RC-0001"}'},
            },
            {
                "id": "call_3",
                "type": "function",
                "function": {"name": "obtener_pasos", "arguments": '{"tramite_id": "RC-0002"}'},
            },
        ],
    )
    db_conn.commit()

    sesiones = chats_repository.listar_sesiones(db_conn, page=1, page_size=20)

    assert sesiones[0]["tramites_citados"] == ["RC-0002", "RC-0001"]


def test_sesion_existe(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    db_conn.commit()

    assert chats_repository.sesion_existe(db_conn, session_id) is True
    assert chats_repository.sesion_existe(db_conn, str(uuid.uuid4())) is False


def test_obtener_mensajes_completos_incluye_tool_calls_y_mensajes_tool(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido=None,
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RC-0001"}'},
            }
        ],
    )
    sessions.guardar_mensaje(
        db_conn, session_id, rol="tool", contenido='["DNI"]', tool_call_id="call_1"
    )
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="Necesitás tu DNI.")
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    assert [m["rol"] for m in mensajes] == ["user", "assistant", "tool", "assistant"]
    assert mensajes[1]["tool_calls"][0]["function"]["name"] == "obtener_requisitos"
    assert mensajes[2]["tool_call_id"] == "call_1"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_chats_repository.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.admin.chats_repository'`

- [ ] **Step 3: Implementar `chats_repository.py`**

Crear `backend/agent/admin/chats_repository.py`:

```python
import json


def contar_sesiones(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM sesiones")
        return cur.fetchone()[0]


def listar_sesiones(conn, page: int, page_size: int) -> list[dict]:
    offset = (page - 1) * page_size
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, created_at
            FROM sesiones
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (page_size, offset),
        )
        filas = cur.fetchall()

    return [
        {
            "id": str(sesion_id),
            "creado_en": creado_en.isoformat(),
            "cantidad_mensajes": _contar_mensajes_visibles(conn, sesion_id),
            "ultimo_mensaje": _obtener_ultimo_mensaje(conn, sesion_id),
            "tramites_citados": _extraer_tramites_citados(conn, sesion_id),
        }
        for sesion_id, creado_en in filas
    ]


def sesion_existe(conn, session_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM sesiones WHERE id = %s", (session_id,))
        return cur.fetchone() is not None


def obtener_mensajes_completos(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, tool_calls, tool_call_id, created_at
            FROM mensajes
            WHERE session_id = %s
            ORDER BY orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    mensajes = []
    for rol, contenido, tool_calls, tool_call_id, creado_en in filas:
        mensaje: dict = {"rol": rol, "contenido": contenido, "creado_en": creado_en.isoformat()}
        if tool_calls is not None:
            mensaje["tool_calls"] = tool_calls
        if tool_call_id is not None:
            mensaje["tool_call_id"] = tool_call_id
        mensajes.append(mensaje)
    return mensajes


def _contar_mensajes_visibles(conn, session_id) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM mensajes
            WHERE session_id = %s AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            """,
            (session_id,),
        )
        return cur.fetchone()[0]


def _obtener_ultimo_mensaje(conn, session_id) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT contenido FROM mensajes
            WHERE session_id = %s AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            ORDER BY orden DESC
            LIMIT 1
            """,
            (session_id,),
        )
        fila = cur.fetchone()
        if fila is None:
            return None
        return _truncar(fila[0], 140)


def _truncar(texto: str, longitud: int) -> str:
    if len(texto) <= longitud:
        return texto
    return texto[:longitud] + "…"


def _extraer_tramites_citados(conn, session_id) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tool_calls FROM mensajes
            WHERE session_id = %s AND rol = 'assistant' AND tool_calls IS NOT NULL
            ORDER BY orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    citados: list[str] = []
    for (tool_calls,) in filas:
        for tool_call in tool_calls:
            argumentos = json.loads(tool_call["function"]["arguments"])
            tramite_id = argumentos.get("tramite_id")
            if tramite_id and tramite_id not in citados:
                citados.append(tramite_id)
    return citados
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_chats_repository.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/chats_repository.py backend/tests/test_admin_chats_repository.py
git commit -m "feat: queries de sesiones y mensajes para el admin"
```

---

### Task 7: Endpoints de chats admin (`GET /admin/sesiones`, `GET /admin/sesiones/{id}`)

**Files:**
- Modify: `backend/agent/api.py`
- Modify: `backend/tests/test_admin_api.py`

**Interfaces:**
- Consumes: `admin_chats_repository.listar_sesiones`, `admin_chats_repository.contar_sesiones`, `admin_chats_repository.sesion_existe`, `admin_chats_repository.obtener_mensajes_completos` (Task 6); `requiere_admin` (Task 5).
- Produces: `GET /admin/sesiones?page=&page_size=` → `{sesiones, total, page, page_size}`; `GET /admin/sesiones/{session_id}` → lista de mensajes o `404`.

- [ ] **Step 1: Agregar los tests que fallan**

Agregar al final de `backend/tests/test_admin_api.py` (mismo archivo de Task 5; agregar el import de `sessions` arriba del archivo):

```python
from agent import sessions
```

```python
def test_listar_sesiones_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.get("/admin/sesiones")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_listar_sesiones_devuelve_sesiones_paginadas(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get("/admin/sesiones?page=1&page_size=20")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["page"] == 1
    assert cuerpo["page_size"] == 20
    assert cuerpo["sesiones"][0]["id"] == session_id


def test_obtener_sesion_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get(f"/admin/sesiones/{uuid.uuid4()}")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_obtener_sesion_devuelve_los_mensajes_completos(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get(f"/admin/sesiones/{session_id}")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["rol"] == "user"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_api.py -v -k "sesiones"`
Expected: FAIL con `404 Not Found` (las rutas todavía no existen)

- [ ] **Step 3: Agregar los endpoints**

En `backend/agent/api.py`, agregar el import junto a los demás de `agent.admin`:

```python
from agent.admin import chats_repository as admin_chats_repository
```

Agregar al final del archivo:

```python
@app.get("/admin/sesiones")
def admin_listar_sesiones(
    page: int = 1,
    page_size: int = 20,
    admin_id: str = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        sesiones = admin_chats_repository.listar_sesiones(conn, page, page_size)
        total = admin_chats_repository.contar_sesiones(conn)
    return {"sesiones": sesiones, "total": total, "page": page, "page_size": page_size}


@app.get("/admin/sesiones/{session_id}")
def admin_obtener_sesion(
    session_id: uuid.UUID,
    admin_id: str = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if not admin_chats_repository.sesion_existe(conn, str(session_id)):
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        return admin_chats_repository.obtener_mensajes_completos(conn, str(session_id))
```

- [ ] **Step 4: Correr todos los tests del backend y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Expected: PASS (toda la suite, sin regresiones)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_api.py
git commit -m "feat: endpoints de listado y detalle de sesiones para el admin"
```

---

## Frontend

### Task 8: `lib/admin-api.ts` — tipos y cliente fetch

**Files:**
- Create: `frontend/lib/admin-api.ts`

**Interfaces:**
- Produces: tipos `ToolCall`, `MensajeAdmin`, `SesionResumen`, `ListaSesiones`; funciones `login(email, password) -> Promise<{ok: true} | {ok: false}>`, `logout() -> Promise<void>`, `obtenerSesiones(page, pageSize) -> Promise<ListaSesiones>`, `obtenerSesion(id) -> Promise<MensajeAdmin[] | null>`. Consumidas por Tasks 10, 11, 12, 13.

No hay test automatizado para este archivo (es un wrapper delgado de `fetch`, mismo criterio que el `lib/api.ts` existente, que tampoco tiene test). Se verifica manualmente al usar las páginas que lo consumen.

- [ ] **Step 1: Crear `admin-api.ts`**

Crear `frontend/lib/admin-api.ts`:

```typescript
export type ToolCall = {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
};

export type MensajeAdmin = {
  rol: "user" | "assistant" | "tool";
  contenido: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  creado_en: string;
};

export type SesionResumen = {
  id: string;
  creado_en: string;
  cantidad_mensajes: number;
  ultimo_mensaje: string | null;
  tramites_citados: string[];
};

export type ListaSesiones = {
  sesiones: SesionResumen[];
  total: number;
  page: number;
  page_size: number;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function login(
  email: string,
  password: string
): Promise<{ ok: true } | { ok: false }> {
  const respuesta = await fetch(`${BASE_URL}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  return respuesta.ok ? { ok: true } : { ok: false };
}

export async function logout(): Promise<void> {
  await fetch(`${BASE_URL}/admin/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function obtenerSesiones(
  page: number,
  pageSize: number
): Promise<ListaSesiones> {
  const respuesta = await fetch(
    `${BASE_URL}/admin/sesiones?page=${page}&page_size=${pageSize}`,
    { credentials: "include" }
  );
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la lista de chats");
  }
  return respuesta.json();
}

export async function obtenerSesion(id: string): Promise<MensajeAdmin[] | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/sesiones/${id}`, {
    credentials: "include",
  });
  if (respuesta.status === 404) {
    return null;
  }
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la sesión");
  }
  return respuesta.json();
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos relacionados a `admin-api.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/admin-api.ts
git commit -m "feat: cliente HTTP del panel de admin"
```

---

### Task 9: `lib/admin-chats.ts` — emparejar tool calls con sus resultados

**Files:**
- Create: `frontend/lib/admin-chats.ts`
- Test: `frontend/lib/admin-chats.test.ts`

**Interfaces:**
- Consumes: tipos `MensajeAdmin`, `ToolCall` de `lib/admin-api.ts` (Task 8).
- Produces: `extraerDetalleToolCalls(mensajeAssistant: MensajeAdmin, todosLosMensajes: MensajeAdmin[]) -> DetalleToolCall[]` (`{id, nombre, argumentos, resultado}`). Usada por Task 13.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `frontend/lib/admin-chats.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { extraerDetalleToolCalls } from "./admin-chats";
import type { MensajeAdmin } from "./admin-api";

describe("extraerDetalleToolCalls", () => {
  it("devuelve lista vacía si el mensaje no tiene tool_calls", () => {
    const mensaje: MensajeAdmin = { rol: "assistant", contenido: "hola", creado_en: "" };
    expect(extraerDetalleToolCalls(mensaje, [mensaje])).toEqual([]);
  });

  it("empareja un tool call con el resultado del mensaje tool correspondiente", () => {
    const mensajeAssistant: MensajeAdmin = {
      rol: "assistant",
      contenido: null,
      creado_en: "",
      tool_calls: [
        {
          id: "call_1",
          type: "function",
          function: { name: "obtener_requisitos", arguments: '{"tramite_id":"RC-0001"}' },
        },
      ],
    };
    const mensajeTool: MensajeAdmin = {
      rol: "tool",
      contenido: '["DNI"]',
      tool_call_id: "call_1",
      creado_en: "",
    };

    const detalle = extraerDetalleToolCalls(mensajeAssistant, [mensajeAssistant, mensajeTool]);

    expect(detalle).toEqual([
      {
        id: "call_1",
        nombre: "obtener_requisitos",
        argumentos: '{"tramite_id":"RC-0001"}',
        resultado: '["DNI"]',
      },
    ]);
  });

  it("devuelve resultado null si no encuentra el mensaje tool correspondiente", () => {
    const mensajeAssistant: MensajeAdmin = {
      rol: "assistant",
      contenido: null,
      creado_en: "",
      tool_calls: [
        { id: "call_1", type: "function", function: { name: "obtener_requisitos", arguments: "{}" } },
      ],
    };

    const detalle = extraerDetalleToolCalls(mensajeAssistant, [mensajeAssistant]);

    expect(detalle[0].resultado).toBeNull();
  });

  it("empareja varios tool calls del mismo mensaje con sus respectivos resultados", () => {
    const mensajeAssistant: MensajeAdmin = {
      rol: "assistant",
      contenido: null,
      creado_en: "",
      tool_calls: [
        { id: "call_1", type: "function", function: { name: "a", arguments: "{}" } },
        { id: "call_2", type: "function", function: { name: "b", arguments: "{}" } },
      ],
    };
    const toolMsg1: MensajeAdmin = { rol: "tool", contenido: "r1", tool_call_id: "call_1", creado_en: "" };
    const toolMsg2: MensajeAdmin = { rol: "tool", contenido: "r2", tool_call_id: "call_2", creado_en: "" };

    const detalle = extraerDetalleToolCalls(mensajeAssistant, [mensajeAssistant, toolMsg1, toolMsg2]);

    expect(detalle.map((d) => d.resultado)).toEqual(["r1", "r2"]);
  });
});
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd frontend && npx vitest run lib/admin-chats.test.ts`
Expected: FAIL — no se puede resolver el módulo `./admin-chats`

- [ ] **Step 3: Implementar `admin-chats.ts`**

Crear `frontend/lib/admin-chats.ts`:

```typescript
import type { MensajeAdmin, ToolCall } from "./admin-api";

export type DetalleToolCall = {
  id: string;
  nombre: string;
  argumentos: string;
  resultado: string | null;
};

export function extraerDetalleToolCalls(
  mensajeAssistant: MensajeAdmin,
  todosLosMensajes: MensajeAdmin[]
): DetalleToolCall[] {
  const toolCalls = mensajeAssistant.tool_calls ?? [];
  return toolCalls.map((toolCall: ToolCall) => {
    const mensajeResultado = todosLosMensajes.find(
      (mensaje) => mensaje.rol === "tool" && mensaje.tool_call_id === toolCall.id
    );
    return {
      id: toolCall.id,
      nombre: toolCall.function.name,
      argumentos: toolCall.function.arguments,
      resultado: mensajeResultado?.contenido ?? null,
    };
  });
}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd frontend && npx vitest run lib/admin-chats.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/admin-chats.ts frontend/lib/admin-chats.test.ts
git commit -m "feat: emparejar tool calls con sus resultados para el detalle técnico"
```

---

### Task 10: Login y protección de rutas (`middleware.ts` + `app/admin/login/page.tsx`)

**Files:**
- Create: `frontend/middleware.ts`
- Create: `frontend/app/admin/login/page.tsx`

**Interfaces:**
- Consumes: `login` de `lib/admin-api.ts` (Task 8).
- Produces: protección de todas las rutas `/admin/*` salvo `/admin/login`.

No hay test automatizado (requiere DOM/fetch real contra el backend). Verificación manual al final de esta task.

- [ ] **Step 1: Crear el middleware**

Crear `frontend/middleware.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function middleware(request: NextRequest) {
  if (request.nextUrl.pathname === "/admin/login") {
    return NextResponse.next();
  }

  const respuesta = await fetch(`${BASE_URL}/admin/me`, {
    headers: { cookie: request.headers.get("cookie") ?? "" },
  });

  if (!respuesta.ok) {
    return NextResponse.redirect(new URL("/admin/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*"],
};
```

- [ ] **Step 2: Crear la página de login**

Crear `frontend/app/admin/login/page.tsx`:

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { login } from "../../../lib/admin-api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [enviando, setEnviando] = useState(false);

  async function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setError(false);
    const resultado = await login(email, password);
    setEnviando(false);
    if (!resultado.ok) {
      setError(true);
      return;
    }
    router.push("/admin/chats");
  }

  return (
    <div className="flex h-screen items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 p-4">
        <h1 className="text-lg font-semibold">Ingresar</h1>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded border border-gray-300 px-3 py-2"
          required
        />
        <input
          type="password"
          placeholder="Contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded border border-gray-300 px-3 py-2"
          required
        />
        {error && <p className="text-sm text-red-600">Credenciales inválidas</p>}
        <button
          type="submit"
          disabled={enviando}
          className="w-full rounded bg-blue-600 px-3 py-2 text-white disabled:opacity-50"
        >
          {enviando ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 4: Commit**

```bash
git add frontend/middleware.ts frontend/app/admin/login/page.tsx
git commit -m "feat: login y protección de rutas del admin"
```

---

### Task 11: Dashboard shell (`app/admin/layout.tsx`, `app/admin/page.tsx`)

**Files:**
- Create: `frontend/app/admin/layout.tsx`
- Create: `frontend/app/admin/page.tsx`

**Interfaces:**
- Consumes: `logout` de `lib/admin-api.ts` (Task 8).
- Produces: layout de navegación para todas las páginas de `/admin/*`; redirect de `/admin` a `/admin/chats`.

- [ ] **Step 1: Crear el layout con navegación y logout**

Crear `frontend/app/admin/layout.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "../../lib/admin-api";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/admin/login");
  }

  return (
    <div className="flex h-screen">
      <nav className="flex w-48 flex-col justify-between border-r border-gray-200 p-4">
        <div>
          <p className="mb-4 font-semibold">Macacha Admin</p>
          <ul className="space-y-2 text-sm">
            <li>
              <Link href="/admin/chats" className="text-blue-700 hover:underline">
                Chats
              </Link>
            </li>
          </ul>
        </div>
        <button onClick={handleLogout} className="text-left text-sm text-gray-500 hover:underline">
          Cerrar sesión
        </button>
      </nav>
      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Crear el redirect de `/admin` a `/admin/chats`**

Crear `frontend/app/admin/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default function AdminIndexPage() {
  redirect("/admin/chats");
}
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/layout.tsx frontend/app/admin/page.tsx
git commit -m "feat: layout de navegación y redirect del dashboard de admin"
```

---

### Task 12: Chats — lista paginada

**Files:**
- Create: `frontend/app/admin/chats/page.tsx`

**Interfaces:**
- Consumes: `obtenerSesiones`, tipo `ListaSesiones` de `lib/admin-api.ts` (Task 8).

- [ ] **Step 1: Crear la página de lista**

Crear `frontend/app/admin/chats/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { obtenerSesiones, type ListaSesiones } from "../../../lib/admin-api";

export default function ChatsPage() {
  const [pagina, setPagina] = useState(1);
  const [datos, setDatos] = useState<ListaSesiones | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, [pagina]);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const resultado = await obtenerSesiones(pagina, 20);
      setDatos(resultado);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }

  if (cargando) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la lista de chats</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (!datos || datos.total === 0) {
    return <p className="p-4 text-sm text-gray-500">Todavía no hay chats registrados</p>;
  }

  const totalPaginas = Math.ceil(datos.total / datos.page_size);

  return (
    <div className="p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left">
            <th className="p-2">Fecha</th>
            <th className="p-2">Mensajes</th>
            <th className="p-2">Último mensaje</th>
            <th className="p-2">Trámites citados</th>
          </tr>
        </thead>
        <tbody>
          {datos.sesiones.map((sesion) => (
            <tr key={sesion.id} className="border-b border-gray-100">
              <td className="p-2">
                <Link href={`/admin/chats/${sesion.id}`} className="text-blue-700 hover:underline">
                  {new Date(sesion.creado_en).toLocaleString("es-AR")}
                </Link>
              </td>
              <td className="p-2">{sesion.cantidad_mensajes}</td>
              <td className="p-2">{sesion.ultimo_mensaje ?? "—"}</td>
              <td className="p-2">
                {sesion.tramites_citados.map((id) => (
                  <span key={id} className="mr-1 rounded bg-gray-100 px-2 py-0.5 text-xs">
                    {id}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 flex items-center gap-4 text-sm">
        <button
          onClick={() => setPagina((p) => p - 1)}
          disabled={pagina <= 1}
          className="text-blue-700 underline disabled:text-gray-400 disabled:no-underline"
        >
          Anterior
        </button>
        <span>
          Página {pagina} de {totalPaginas}
        </span>
        <button
          onClick={() => setPagina((p) => p + 1)}
          disabled={pagina >= totalPaginas}
          className="text-blue-700 underline disabled:text-gray-400 disabled:no-underline"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/chats/page.tsx
git commit -m "feat: lista paginada de chats en el admin"
```

---

### Task 13: Chats — detalle de sesión con detalle técnico expandible

**Files:**
- Create: `frontend/app/admin/chats/[id]/page.tsx`

**Interfaces:**
- Consumes: `obtenerSesion`, tipo `MensajeAdmin` de `lib/admin-api.ts` (Task 8); `extraerDetalleToolCalls` de `lib/admin-chats.ts` (Task 9).

- [ ] **Step 1: Crear la página de detalle**

Crear `frontend/app/admin/chats/[id]/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { obtenerSesion, type MensajeAdmin } from "../../../../lib/admin-api";
import { extraerDetalleToolCalls } from "../../../../lib/admin-chats";

export default function SesionDetallePage() {
  const params = useParams<{ id: string }>();
  const [mensajes, setMensajes] = useState<MensajeAdmin[] | null | undefined>(undefined);
  const [error, setError] = useState(false);

  useEffect(() => {
    cargar();
  }, [params.id]);

  async function cargar() {
    setError(false);
    setMensajes(undefined);
    try {
      const resultado = await obtenerSesion(params.id);
      setMensajes(resultado);
    } catch {
      setError(true);
    }
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la sesión</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (mensajes === undefined) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (mensajes === null) {
    return (
      <div className="p-4">
        <p className="text-sm text-gray-600">Sesión no encontrada</p>
        <Link href="/admin/chats" className="text-sm text-blue-700 underline">
          Volver a la lista
        </Link>
      </div>
    );
  }

  const visibles = mensajes.filter((m) => m.rol === "user" || m.rol === "assistant");

  return (
    <div className="mx-auto max-w-2xl space-y-3 p-4">
      {visibles.map((mensaje, indice) => (
        <div key={indice} className={`flex ${mensaje.rol === "user" ? "justify-end" : "justify-start"}`}>
          <div
            className={`max-w-[80%] rounded-lg px-4 py-2 ${
              mensaje.rol === "user" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-900"
            }`}
          >
            <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
            {mensaje.rol === "assistant" && mensaje.tool_calls && mensaje.tool_calls.length > 0 && (
              <DetalleTecnico mensaje={mensaje} todosLosMensajes={mensajes} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function DetalleTecnico({
  mensaje,
  todosLosMensajes,
}: {
  mensaje: MensajeAdmin;
  todosLosMensajes: MensajeAdmin[];
}) {
  const [abierto, setAbierto] = useState(false);
  const detalle = extraerDetalleToolCalls(mensaje, todosLosMensajes);

  return (
    <div className="mt-2 border-t border-gray-300 pt-2 text-sm">
      <button onClick={() => setAbierto(!abierto)} className="text-blue-700 underline">
        {abierto ? "Ocultar detalle técnico" : "Ver detalle técnico"}
      </button>
      {abierto && (
        <ul className="mt-2 space-y-2">
          {detalle.map((item) => (
            <li key={item.id} className="rounded bg-white p-2">
              <p className="font-mono text-xs font-semibold">{item.nombre}</p>
              <pre className="whitespace-pre-wrap break-all text-xs">{item.argumentos}</pre>
              <pre className="whitespace-pre-wrap break-all text-xs text-gray-600">
                {item.resultado ?? "(sin resultado)"}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/admin/chats/[id]/page.tsx"
git commit -m "feat: detalle de sesión con detalle técnico expandible"
```

---

### Task 14: Verificación manual end-to-end

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Confirmar que `NEXT_PUBLIC_API_URL` apunta al backend real**

`frontend/.env.local` puede tener un valor de puerto obsoleto. Confirmar que coincide con el puerto donde corre `uvicorn` (por defecto `8000` en este repo):

```bash
cat frontend/.env.local
```

Si no coincide, corregirlo a `NEXT_PUBLIC_API_URL=http://localhost:8000`.

- [ ] **Step 2: Crear el primer admin**

Run: `cd backend && source .venv/bin/activate && python -m agent.admin.create_admin admin@macacha.gob.ar`

Ingresar una contraseña cuando lo pida.

- [ ] **Step 3: Levantar backend y frontend**

Confirmar que Postgres, `uvicorn agent.api:app --reload --port 8000` y `npm run dev` (frontend) están corriendo.

- [ ] **Step 4: Verificar la protección de rutas**

Navegar a `http://localhost:3000/admin/chats` sin haber iniciado sesión.
Expected: redirige a `/admin/login`.

- [ ] **Step 5: Verificar login con credenciales inválidas**

Ingresar un email/password incorrectos.
Expected: se muestra "Credenciales inválidas", sin redirigir.

- [ ] **Step 6: Verificar login con credenciales válidas**

Ingresar el email/password creados en el Step 2.
Expected: redirige a `/admin/chats`.

- [ ] **Step 7: Generar una sesión de chat con trámites citados**

En `http://localhost:3000` (chat público), preguntar por un trámite existente (ej. "¿qué necesito para un acta de nacimiento?") para generar una sesión con tool calls.

- [ ] **Step 8: Verificar la lista de chats**

Volver a `http://localhost:3000/admin/chats` y refrescar.
Expected: aparece la sesión nueva, con fecha, cantidad de mensajes, preview del último mensaje y el trámite citado.

- [ ] **Step 9: Verificar el detalle de sesión y el detalle técnico**

Entrar a la sesión generada en el Step 7.
Expected: se ve la conversación limpia; al expandir "Ver detalle técnico" en el turno del asistente que usó una tool, se ve el nombre de la tool, los argumentos y el resultado.

- [ ] **Step 10: Verificar sesión inexistente**

Navegar a `http://localhost:3000/admin/chats/00000000-0000-0000-0000-000000000000`.
Expected: "Sesión no encontrada" con link de vuelta a la lista.

- [ ] **Step 11: Verificar logout**

Click en "Cerrar sesión".
Expected: redirige a `/admin/login`; navegar de nuevo a `/admin/chats` vuelve a redirigir a `/admin/login`.

- [ ] **Step 12: Correr toda la suite de tests una última vez**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Run: `cd frontend && npx vitest run`
Expected: PASS en ambas suites.
