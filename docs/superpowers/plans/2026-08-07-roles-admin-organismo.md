# Roles de admin por organismo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introducir dos roles de admin (`super_admin`, `admin_organismo`) para que un admin de organismo solo vea y edite los chats y trámites de su propio organismo, con gestión de usuarios/organismos desde una pantalla nueva accesible solo a super-admins.

**Architecture:** Se agregan `rol`, `organismo_id`, `activo` a la tabla `admins`. El JWT lleva `rol`/`organismo_id` para que `requiere_admin` no necesite ir a la base en cada request. Cada endpoint que lista o accede a chats/trámites por id aplica el filtro/chequeo de organismo según el rol del admin autenticado. El filtrado de chats por organismo se resuelve en Python (no en SQL) reutilizando el código existente que extrae trámites citados de `tool_calls`. En el frontend, un `AdminAuthContext` poblado desde `/admin/me` expone `{ email, rol, organismo }` a toda la sección `/admin`.

**Tech Stack:** FastAPI + psycopg3 + Postgres/pgvector (backend), Next.js 15 + React 19 + TypeScript (frontend), pytest, vitest.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-07-roles-admin-organismo-design.md` — toda tarea implementa una sección de ese documento.
- Estilo de nombres del proyecto: identificadores en español (`crear_admin`, `listar_sesiones`, `obtener_tramite`), consistente con el código existente.
- Backend: cada función nueva en `agent/admin/*` que toque la base recibe `conn` como primer parámetro (patrón ya usado en todo `agent/admin/`).
- Frontend: `"use client"` en cualquier componente/página con estado o efectos, siguiendo el patrón existente. `credentials: "include"` en todo `fetch` a la API (cookies de sesión).
- Este repo no testea componentes React ni fetch wrappers de frontend (`lib/*-api.ts`) — solo funciones puras de transformación (ver `lib/admin-chats.test.ts`). Las tareas de frontend no agregan tests nuevos, salvo que se indique lo contrario explícitamente.
- Todo cambio de schema va en `backend/db/schema.sql`, agregado al final, con el mismo estilo idempotente (`ADD COLUMN IF NOT EXISTS`) que ya usa el archivo.

---

## Task 1: Schema — columnas de rol/organismo/activo en `admins`

**Files:**
- Modify: `backend/db/schema.sql`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_schema_smoke.py`

**Interfaces:**
- Produces: columnas `admins.rol` (`admin_rol` enum: `'super_admin'` | `'admin_organismo'`), `admins.organismo_id` (`INTEGER REFERENCES organismos(id)`, nullable), `admins.activo` (`BOOLEAN NOT NULL DEFAULT true`). Usadas por todas las tareas siguientes.

- [ ] **Step 1: Agregar el cambio de schema**

Al final de `backend/db/schema.sql`, agregar:

```sql
DO $$ BEGIN
    CREATE TYPE admin_rol AS ENUM ('super_admin', 'admin_organismo');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE admins ADD COLUMN IF NOT EXISTS rol admin_rol NOT NULL DEFAULT 'admin_organismo';
ALTER TABLE admins ADD COLUMN IF NOT EXISTS organismo_id INTEGER REFERENCES organismos(id);
ALTER TABLE admins ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT true;
```

- [ ] **Step 2: Recrear la base de tests con el schema nuevo**

`admins.organismo_id` ahora referencia `organismos`, así que el orden de limpieza en el fixture `clean_db` (que hoy borra `organismos` antes que `admins`) va a violar la FK en cuanto un test cree un admin con `organismo_id`. Reordenar:

En `backend/tests/conftest.py`, dentro de `_clean()`, mover `cur.execute("DELETE FROM admins")` para que ocurra **antes** de `cur.execute("DELETE FROM organismos")`:

```python
def _clean() -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mensajes")
        cur.execute("DELETE FROM sesiones")
        cur.execute("DELETE FROM tramite_chunks")
        cur.execute("DELETE FROM tramite_versiones")
        cur.execute("DELETE FROM admins")
        cur.execute("DELETE FROM tramites")
        cur.execute("DELETE FROM organismos")
```

- [ ] **Step 3: Aplicar el schema a la base de tests local**

```bash
docker compose up -d postgres
psql "postgresql://macacha:macacha@localhost:5432/macacha" -f backend/db/schema.sql
```

Expected: sin errores. Correrlo dos veces seguidas tampoco debe dar error (idempotencia).

- [ ] **Step 4: Extender el smoke test de schema**

En `backend/tests/test_schema_smoke.py`, agregar una verificación de las columnas nuevas:

```python
def test_admins_tiene_columnas_de_rol_y_organismo(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'admins'
            """
        )
        columnas = {row[0] for row in cur.fetchall()}
        assert {"rol", "organismo_id", "activo"} <= columnas
```

- [ ] **Step 5: Correr los tests de schema**

Run: `cd backend && .venv/bin/pytest tests/test_schema_smoke.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/db/schema.sql backend/tests/conftest.py backend/tests/test_schema_smoke.py
git commit -m "feat: agrega rol, organismo_id y activo a admins"
```

---

## Task 2: `agent/admin/repository.py` — CRUD de admin extendido

**Files:**
- Modify: `backend/agent/admin/repository.py`
- Modify: `backend/tests/test_admin_repository.py`

**Interfaces:**
- Consumes: tabla `admins` (Task 1).
- Produces:
  - `crear_admin(conn, email: str, password_hash: str, rol: str = "admin_organismo", organismo_id: int | None = None) -> None`
  - `obtener_admin_por_email(conn, email: str) -> dict | None` — dict con `id, email, password_hash, rol, organismo_id, activo`
  - `obtener_admin_por_id(conn, admin_id: str) -> dict | None` — dict con `id, email, rol, organismo_id, activo`
  - `listar_admins(conn) -> list[dict]` — cada dict: `id, email, rol, organismo, activo` (`organismo` es el **nombre**, no el id; `None` si `super_admin`)
  - `editar_admin(conn, admin_id: str, rol: str, organismo_id: int | None, activo: bool, password_hash: str | None = None) -> None`

Usadas por Task 4 (dependencies), Task 7 (login/me) y Task 10 (endpoints de usuarios).

- [ ] **Step 1: Escribir los tests que fallan**

Reemplazar el contenido de `backend/tests/test_admin_repository.py`:

```python
from agent.admin import repository


def test_crear_admin_y_obtener_por_email(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["email"] == "admin@macacha.gob.ar"
    assert admin["password_hash"] == "hash-1"
    assert admin["id"]
    assert admin["rol"] == "admin_organismo"
    assert admin["organismo_id"] is None
    assert admin["activo"] is True


def test_crear_admin_con_rol_y_organismo(db_conn, clean_db):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES ('Registro Civil') RETURNING id")
        organismo_id = cur.fetchone()[0]
    db_conn.commit()

    repository.crear_admin(
        db_conn, "admin@macacha.gob.ar", "hash-1", rol="super_admin", organismo_id=None
    )
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")
    assert admin["rol"] == "super_admin"
    assert admin["organismo_id"] is None


def test_obtener_admin_por_email_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_email(db_conn, "no-existe@macacha.gob.ar") is None


def test_crear_admin_con_email_repetido_actualiza_los_datos(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-viejo")
    db_conn.commit()
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-nuevo", rol="super_admin")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["password_hash"] == "hash-nuevo"
    assert admin["rol"] == "super_admin"


def test_obtener_admin_por_id(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()
    creado = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    admin = repository.obtener_admin_por_id(db_conn, creado["id"])

    assert admin == {
        "id": creado["id"],
        "email": "admin@macacha.gob.ar",
        "rol": "admin_organismo",
        "organismo_id": None,
        "activo": True,
    }


def test_obtener_admin_por_id_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_id(db_conn, "00000000-0000-0000-0000-000000000000") is None


def test_listar_admins_incluye_nombre_de_organismo(db_conn, clean_db):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES ('Registro Civil') RETURNING id")
        organismo_id = cur.fetchone()[0]
    repository.crear_admin(db_conn, "super@macacha.gob.ar", "hash-1", rol="super_admin")
    repository.crear_admin(
        db_conn, "org@macacha.gob.ar", "hash-2", rol="admin_organismo", organismo_id=organismo_id
    )
    db_conn.commit()

    admins = repository.listar_admins(db_conn)

    por_email = {a["email"]: a for a in admins}
    assert por_email["super@macacha.gob.ar"]["organismo"] is None
    assert por_email["org@macacha.gob.ar"]["organismo"] == "Registro Civil"


def test_editar_admin_actualiza_rol_organismo_y_activo(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()
    admin_id = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")["id"]

    repository.editar_admin(db_conn, admin_id, rol="super_admin", organismo_id=None, activo=False)
    db_conn.commit()

    admin = repository.obtener_admin_por_id(db_conn, admin_id)
    assert admin["rol"] == "super_admin"
    assert admin["activo"] is False


def test_editar_admin_con_password_hash_lo_actualiza(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-viejo")
    db_conn.commit()
    admin_id = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")["id"]

    repository.editar_admin(
        db_conn, admin_id, rol="admin_organismo", organismo_id=None, activo=True,
        password_hash="hash-nuevo",
    )
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")
    assert admin["password_hash"] == "hash-nuevo"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_repository.py -v`
Expected: FAIL (los dicts devueltos no tienen `rol`/`organismo_id`/`activo`, `listar_admins`/`editar_admin` no existen).

- [ ] **Step 3: Implementar `repository.py`**

Reemplazar `backend/agent/admin/repository.py` completo:

```python
def crear_admin(
    conn,
    email: str,
    password_hash: str,
    rol: str = "admin_organismo",
    organismo_id: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admins (email, password_hash, rol, organismo_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                rol = EXCLUDED.rol,
                organismo_id = EXCLUDED.organismo_id
            """,
            (email, password_hash, rol, organismo_id),
        )


def obtener_admin_por_email(conn, email: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, password_hash, rol, organismo_id, activo FROM admins WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "password_hash": row[2],
            "rol": row[3],
            "organismo_id": row[4],
            "activo": row[5],
        }


def obtener_admin_por_id(conn, admin_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, email, rol, organismo_id, activo FROM admins WHERE id = %s", (admin_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "rol": row[2],
            "organismo_id": row[3],
            "activo": row[4],
        }


def listar_admins(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.email, a.rol, o.nombre, a.activo
            FROM admins a
            LEFT JOIN organismos o ON o.id = a.organismo_id
            ORDER BY a.email
            """
        )
        return [
            {"id": str(id_), "email": email, "rol": rol, "organismo": organismo, "activo": activo}
            for id_, email, rol, organismo, activo in cur.fetchall()
        ]


def editar_admin(
    conn,
    admin_id: str,
    rol: str,
    organismo_id: int | None,
    activo: bool,
    password_hash: str | None = None,
) -> None:
    with conn.cursor() as cur:
        if password_hash is not None:
            cur.execute(
                """
                UPDATE admins SET rol = %s, organismo_id = %s, activo = %s, password_hash = %s
                WHERE id = %s
                """,
                (rol, organismo_id, activo, password_hash, admin_id),
            )
        else:
            cur.execute(
                "UPDATE admins SET rol = %s, organismo_id = %s, activo = %s WHERE id = %s",
                (rol, organismo_id, activo, admin_id),
            )
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_repository.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/repository.py backend/tests/test_admin_repository.py
git commit -m "feat: extiende admin repository con rol, organismo_id y activo"
```

---

## Task 3: `agent/admin/security.py` — JWT con rol y organismo

**Files:**
- Modify: `backend/agent/admin/security.py`
- Modify: `backend/tests/test_admin_security.py`

**Interfaces:**
- Consumes: nada nuevo.
- Produces:
  - `crear_token(admin: dict) -> str` — `admin` requiere `id`, `rol`, `organismo_id`.
  - `decodificar_token(token: str) -> dict | None` — devuelve `{"sub": str, "rol": str, "organismo_id": int | None}` o `None` si inválido/expirado.

Usadas por Task 4 (`requiere_admin`) y Task 7 (`admin_login`).

- [ ] **Step 1: Escribir los tests que fallan**

Reemplazar `backend/tests/test_admin_security.py`:

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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_security.py -v`
Expected: FAIL (`crear_token` toma un `str`, `decodificar_token` devuelve solo el `sub`).

- [ ] **Step 3: Implementar `security.py`**

Reemplazar `backend/agent/admin/security.py` completo:

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


def crear_token(admin: dict) -> str:
    payload = {
        "sub": admin["id"],
        "rol": admin["rol"],
        "organismo_id": admin["organismo_id"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, os.environ["ADMIN_JWT_SECRET"], algorithm="HS256")


def decodificar_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, os.environ["ADMIN_JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return {
        "sub": payload.get("sub"),
        "rol": payload.get("rol"),
        "organismo_id": payload.get("organismo_id"),
    }
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_security.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/security.py backend/tests/test_admin_security.py
git commit -m "feat: incluye rol y organismo_id en el JWT de admin"
```

---

## Task 4: `agent/admin/dependencies.py` — `AdminActual` y `requiere_super_admin`

**Files:**
- Modify: `backend/agent/admin/dependencies.py`
- Create: `backend/tests/test_admin_dependencies.py`

**Interfaces:**
- Consumes: `security.decodificar_token` (Task 3).
- Produces:
  - `AdminActual` (dataclass): `id: str`, `rol: str`, `organismo_id: int | None`.
  - `requiere_admin(request: Request) -> AdminActual`
  - `requiere_super_admin(admin: AdminActual = Depends(requiere_admin)) -> AdminActual` — `403` si `admin.rol != "super_admin"`.

Usadas por Task 7, 8, 9, 10 (todos los endpoints de `api.py`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_dependencies.py`:

```python
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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_dependencies.py -v`
Expected: FAIL (`AdminActual`/`requiere_super_admin` no existen; `requiere_admin` devuelve un `str`).

- [ ] **Step 3: Implementar `dependencies.py`**

Reemplazar `backend/agent/admin/dependencies.py` completo:

```python
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from agent.admin import security


@dataclass
class AdminActual:
    id: str
    rol: str
    organismo_id: int | None


def requiere_admin(request: Request) -> AdminActual:
    token = request.cookies.get("admin_session")
    if token is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    payload = security.decodificar_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    return AdminActual(id=payload["sub"], rol=payload["rol"], organismo_id=payload["organismo_id"])


def requiere_super_admin(admin: AdminActual = Depends(requiere_admin)) -> AdminActual:
    if admin.rol != "super_admin":
        raise HTTPException(status_code=403, detail="Requiere permisos de super admin")
    return admin
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_dependencies.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/dependencies.py backend/tests/test_admin_dependencies.py
git commit -m "feat: agrega AdminActual y requiere_super_admin"
```

---

## Task 5: `agent/admin/tramites_repository.py` — filtrado y gestión de organismos

**Files:**
- Modify: `backend/agent/admin/tramites_repository.py`
- Modify: `backend/tests/test_admin_tramites_repository.py`

**Interfaces:**
- Consumes: tablas `tramites`, `organismos` (sin cambios de schema).
- Produces:
  - `listar_tramites(conn, organismo_id: int | None = None) -> list[dict]` — mismo shape que hoy, filtrado si `organismo_id` no es `None`.
  - `listar_organismos(conn) -> list[dict]` — **cambia de `list[str]` a `list[dict]`**, cada uno `{"id": int, "nombre": str}`.
  - `obtener_organismo_id_de_tramite(conn, tramite_id: str) -> int | None`
  - `obtener_nombre_organismo(conn, organismo_id: int) -> str | None`
  - `obtener_organismo_id_por_nombre(conn, nombre: str) -> int | None`
  - `crear_organismo(conn, nombre: str) -> int` — `INSERT` simple (no upsert); deja que la constraint `UNIQUE` de Postgres levante `psycopg.errors.UniqueViolation` si el nombre ya existe (el caller, Task 10, decide cómo traducirlo a HTTP).

Usadas por Task 6 (chats), Task 9 (endpoints de trámites), Task 10 (endpoints de usuarios/organismos).

**Breaking change:** `listar_organismos` cambia de forma (`list[str]` → `list[dict]`). El endpoint `GET /admin/organismos` en `api.py` no tiene lógica propia — devuelve el resultado del repository tal cual — así que apenas este task se mergea, ese endpoint empieza a devolver objetos en lugar de strings sin que nadie toque `api.py`. Por eso este mismo task también actualiza el test de integración que depende de esa forma (`test_admin_tramites_api.py::test_listar_organismos_devuelve_nombres`), para no dejar la suite de `test_admin_tramites_api.py` rota entre este task y la Task 9. Los consumidores de frontend se actualizan en Task 13.

- [ ] **Step 1: Escribir los tests que fallan**

Reemplazar `backend/tests/test_admin_tramites_repository.py`:

```python
import psycopg
import pytest

from ingest import repository as repo
from agent.admin import tramites_repository


def test_listar_tramites_devuelve_resumen(db_conn, clean_db):
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
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    tramites = tramites_repository.listar_tramites(db_conn)

    assert tramites == [
        {
            "id": "RC-0001",
            "nombre_oficial": "Actas Regulares",
            "organismo": "Registro Civil",
            "categoria": "Actas",
            "veces_consultado": 0,
            "numero_version": 1,
        }
    ]


def test_listar_tramites_filtra_por_organismo_id(db_conn, clean_db):
    organismo_a = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_b = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_a, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RE-0001", organismo_b, "Pagos", "Pago de patente")
    db_conn.commit()

    tramites = tramites_repository.listar_tramites(db_conn, organismo_id=organismo_a)

    assert [t["id"] for t in tramites] == ["RC-0001"]


def test_listar_organismos_devuelve_id_y_nombre_ordenados(db_conn, clean_db):
    id_registro = repo.upsert_organismo(db_conn, "Registro Civil")
    id_rentas = repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramites_repository.listar_organismos(db_conn) == [
        {"id": id_rentas, "nombre": "Dirección de Rentas"},
        {"id": id_registro, "nombre": "Registro Civil"},
    ]


def test_obtener_organismo_id_de_tramite(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert tramites_repository.obtener_organismo_id_de_tramite(db_conn, "RC-0001") == organismo_id
    assert tramites_repository.obtener_organismo_id_de_tramite(db_conn, "RC-9999") is None


def test_obtener_nombre_organismo(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    assert tramites_repository.obtener_nombre_organismo(db_conn, organismo_id) == "Registro Civil"
    assert tramites_repository.obtener_nombre_organismo(db_conn, 999999) is None


def test_obtener_organismo_id_por_nombre(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    assert tramites_repository.obtener_organismo_id_por_nombre(db_conn, "Registro Civil") == organismo_id
    assert tramites_repository.obtener_organismo_id_por_nombre(db_conn, "No existe") is None


def test_crear_organismo_devuelve_id(db_conn, clean_db):
    organismo_id = tramites_repository.crear_organismo(db_conn, "Nuevo Organismo")
    db_conn.commit()

    assert tramites_repository.obtener_nombre_organismo(db_conn, organismo_id) == "Nuevo Organismo"


def test_crear_organismo_con_nombre_repetido_lanza_unique_violation(db_conn, clean_db):
    tramites_repository.crear_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    with pytest.raises(psycopg.errors.UniqueViolation):
        tramites_repository.crear_organismo(db_conn, "Registro Civil")
    db_conn.rollback()


def test_obtener_chunks_por_version_incluye_embedding(db_conn, clean_db):
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
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto descriptivo", "fuente_url": None}]
    embeddings = [[0.1] * 1536]
    version_id = repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings
    )
    db_conn.commit()

    chunks_obtenidos = tramites_repository.obtener_chunks_por_version(db_conn, version_id)

    assert len(chunks_obtenidos) == 1
    assert chunks_obtenidos[0]["tipo_chunk"] == "descripcion"
    assert chunks_obtenidos[0]["texto"] == "texto descriptivo"
    assert list(chunks_obtenidos[0]["embedding"][:3]) == [0.1, 0.1, 0.1]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_tramites_repository.py -v`
Expected: FAIL (funciones nuevas no existen, `listar_organismos` devuelve strings).

- [ ] **Step 3: Implementar `tramites_repository.py`**

Reemplazar `backend/agent/admin/tramites_repository.py` completo:

```python
def listar_tramites(conn, organismo_id: int | None = None) -> list[dict]:
    query = """
        SELECT t.id, t.nombre_oficial, o.nombre, t.categoria, t.veces_consultado, v.numero_version
        FROM tramites t
        JOIN organismos o ON o.id = t.organismo_id
        LEFT JOIN tramite_versiones v ON v.tramite_id = t.id AND v.es_vigente = true
    """
    params: tuple = ()
    if organismo_id is not None:
        query += " WHERE t.organismo_id = %s"
        params = (organismo_id,)
    query += " ORDER BY t.id"

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [
            {
                "id": tramite_id,
                "nombre_oficial": nombre_oficial,
                "organismo": organismo,
                "categoria": categoria,
                "veces_consultado": veces_consultado,
                "numero_version": numero_version,
            }
            for tramite_id, nombre_oficial, organismo, categoria, veces_consultado, numero_version in cur.fetchall()
        ]


def listar_organismos(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM organismos ORDER BY nombre")
        return [{"id": id_, "nombre": nombre} for id_, nombre in cur.fetchall()]


def obtener_organismo_id_de_tramite(conn, tramite_id: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT organismo_id FROM tramites WHERE id = %s", (tramite_id,))
        fila = cur.fetchone()
        return fila[0] if fila else None


def obtener_nombre_organismo(conn, organismo_id: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT nombre FROM organismos WHERE id = %s", (organismo_id,))
        fila = cur.fetchone()
        return fila[0] if fila else None


def obtener_organismo_id_por_nombre(conn, nombre: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM organismos WHERE nombre = %s", (nombre,))
        fila = cur.fetchone()
        return fila[0] if fila else None


def crear_organismo(conn, nombre: str) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def obtener_chunks_por_version(conn, version_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tipo_chunk, texto, fuente_url, embedding FROM tramite_chunks WHERE version_id = %s",
            (version_id,),
        )
        return [
            {"tipo_chunk": tipo_chunk, "texto": texto, "fuente_url": fuente_url, "embedding": embedding}
            for tipo_chunk, texto, fuente_url, embedding in cur.fetchall()
        ]
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_tramites_repository.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Actualizar el test de integración que depende de la forma vieja de `listar_organismos`**

`GET /admin/organismos` en `api.py` no tiene lógica propia — llama a `admin_tramites_repository.listar_organismos(conn)` y devuelve el resultado tal cual — así que ya devuelve objetos en vez de strings con el cambio del Step 3, sin que haga falta tocar `api.py` todavía. En `backend/tests/test_admin_tramites_api.py`, reemplazar `test_listar_organismos_devuelve_nombres`:

```python
def test_listar_organismos_devuelve_id_y_nombre(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/organismos")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == [{"id": organismo_id, "nombre": "Registro Civil"}]
```

Run: `cd backend && .venv/bin/pytest tests/test_admin_tramites_api.py -v -k organismos`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/agent/admin/tramites_repository.py backend/tests/test_admin_tramites_repository.py backend/tests/test_admin_tramites_api.py
git commit -m "feat: filtrado por organismo y gestion de organismos en tramites_repository"
```

---

## Task 6: `agent/admin/chats_repository.py` — filtrado de sesiones por organismo

**Files:**
- Modify: `backend/agent/admin/chats_repository.py`
- Modify: `backend/tests/test_admin_chats_repository.py`

**Interfaces:**
- Consumes: `_extraer_tramites_citados_batch` (ya existe en el mismo archivo), tabla `tramites`.
- Produces:
  - `listar_sesiones_de_organismo(conn, organismo_id: int, page: int, page_size: int) -> tuple[list[dict], int]` — `(sesiones_de_la_pagina, total_filtrado)`. Cada sesión tiene el mismo shape que `listar_sesiones` (ya existente, sin cambios).
  - `sesion_pertenece_a_organismo(conn, session_id: str, organismo_id: int) -> bool`
  - `listar_sesiones` y `contar_sesiones` (ya existentes) quedan **sin cambios** — siguen siendo el camino de `super_admin`.

Usadas por Task 8 (`GET /admin/sesiones`, `GET /admin/sesiones/{id}`).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `backend/tests/test_admin_chats_repository.py` (mantener todo lo existente arriba tal cual):

```python
def _crear_organismo(conn, nombre):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def _crear_tramite(conn, tramite_id, organismo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial) VALUES (%s, %s, '', %s)",
            (tramite_id, organismo_id, tramite_id),
        )


def _mensaje_cita_tramite(call_id, tramite_id):
    return [
        {
            "id": call_id,
            "type": "function",
            "function": {"name": "obtener_requisitos", "arguments": f'{{"tramite_id": "{tramite_id}"}}'},
        }
    ]


def test_listar_sesiones_de_organismo_incluye_solo_sesiones_con_tramite_propio(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    organismo_b = _crear_organismo(db_conn, "Rentas")
    _crear_tramite(db_conn, "RC-0001", organismo_a)
    _crear_tramite(db_conn, "RE-0001", organismo_b)

    sesion_a = str(uuid.uuid4())
    sesion_b = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_a, datetime.now(timezone.utc))
    _crear_sesion(db_conn, sesion_b, datetime.now(timezone.utc) + timedelta(minutes=1))
    sessions.guardar_mensaje(
        db_conn, sesion_a, rol="assistant", tool_calls=_mensaje_cita_tramite("call_1", "RC-0001")
    )
    sessions.guardar_mensaje(
        db_conn, sesion_b, rol="assistant", tool_calls=_mensaje_cita_tramite("call_2", "RE-0001")
    )
    db_conn.commit()

    sesiones, total = chats_repository.listar_sesiones_de_organismo(
        db_conn, organismo_a, page=1, page_size=20
    )

    assert total == 1
    assert [s["id"] for s in sesiones] == [sesion_a]


def test_listar_sesiones_de_organismo_excluye_sesiones_sin_tramites_citados(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    sesion_sin_citas = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_sin_citas, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, sesion_sin_citas, rol="user", contenido="hola")
    db_conn.commit()

    sesiones, total = chats_repository.listar_sesiones_de_organismo(
        db_conn, organismo_a, page=1, page_size=20
    )

    assert total == 0
    assert sesiones == []


def test_listar_sesiones_de_organismo_pagina_el_resultado_filtrado(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    _crear_tramite(db_conn, "RC-0001", organismo_a)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    base = datetime.now(timezone.utc)
    for i, sesion_id in enumerate(ids):
        _crear_sesion(db_conn, sesion_id, base + timedelta(minutes=i))
        sessions.guardar_mensaje(
            db_conn, sesion_id, rol="assistant", tool_calls=_mensaje_cita_tramite(f"call_{i}", "RC-0001")
        )
    db_conn.commit()

    sesiones, total = chats_repository.listar_sesiones_de_organismo(
        db_conn, organismo_a, page=1, page_size=2
    )

    assert total == 3
    assert len(sesiones) == 2
    assert sesiones[0]["id"] == ids[2]


def test_sesion_pertenece_a_organismo_true_si_cito_un_tramite_propio(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    _crear_tramite(db_conn, "RC-0001", organismo_a)
    sesion_id = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn, sesion_id, rol="assistant", tool_calls=_mensaje_cita_tramite("call_1", "RC-0001")
    )
    db_conn.commit()

    assert chats_repository.sesion_pertenece_a_organismo(db_conn, sesion_id, organismo_a) is True


def test_sesion_pertenece_a_organismo_false_si_no_cito_nada_de_ese_organismo(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    organismo_b = _crear_organismo(db_conn, "Rentas")
    _crear_tramite(db_conn, "RE-0001", organismo_b)
    sesion_id = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(
        db_conn, sesion_id, rol="assistant", tool_calls=_mensaje_cita_tramite("call_1", "RE-0001")
    )
    db_conn.commit()

    assert chats_repository.sesion_pertenece_a_organismo(db_conn, sesion_id, organismo_a) is False


def test_sesion_pertenece_a_organismo_false_si_no_cito_nada(db_conn, clean_db):
    organismo_a = _crear_organismo(db_conn, "Registro Civil")
    sesion_id = str(uuid.uuid4())
    _crear_sesion(db_conn, sesion_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, sesion_id, rol="user", contenido="hola")
    db_conn.commit()

    assert chats_repository.sesion_pertenece_a_organismo(db_conn, sesion_id, organismo_a) is False
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_chats_repository.py -v`
Expected: FAIL (`listar_sesiones_de_organismo`/`sesion_pertenece_a_organismo` no existen).

- [ ] **Step 3: Implementar las funciones nuevas**

Agregar al final de `backend/agent/admin/chats_repository.py` (todo lo existente queda tal cual, incluidas las funciones privadas que se reutilizan):

```python
def listar_sesiones_de_organismo(
    conn, organismo_id: int, page: int, page_size: int
) -> tuple[list[dict], int]:
    filas = _listar_todas_las_sesiones(conn)
    if not filas:
        return [], 0

    session_ids = [str(sesion_id) for sesion_id, _ in filas]
    citados = _extraer_tramites_citados_batch(conn, session_ids)
    organismos_de_tramites = _organismos_de_tramites(conn, citados)

    filtradas = [
        (sesion_id, creado_en)
        for sesion_id, creado_en in filas
        if any(
            organismos_de_tramites.get(tramite_id) == organismo_id
            for tramite_id in citados.get(str(sesion_id), [])
        )
    ]

    total = len(filtradas)
    offset = (page - 1) * page_size
    pagina = filtradas[offset : offset + page_size]

    if not pagina:
        return [], total

    ids_pagina = [str(sesion_id) for sesion_id, _ in pagina]
    conteos = _contar_mensajes_visibles_batch(conn, ids_pagina)
    ultimos = _obtener_ultimo_mensaje_batch(conn, ids_pagina)

    resultado = [
        {
            "id": str(sesion_id),
            "creado_en": creado_en.isoformat(),
            "cantidad_mensajes": conteos.get(str(sesion_id), 0),
            "ultimo_mensaje": ultimos.get(str(sesion_id)),
            "tramites_citados": citados.get(str(sesion_id), []),
        }
        for sesion_id, creado_en in pagina
    ]
    return resultado, total


def sesion_pertenece_a_organismo(conn, session_id: str, organismo_id: int) -> bool:
    citados = _extraer_tramites_citados_batch(conn, [session_id])
    tramites_citados = citados.get(session_id, [])
    if not tramites_citados:
        return False
    organismos_de_tramites = _organismos_de_tramites(conn, {session_id: tramites_citados})
    return any(organismos_de_tramites.get(t) == organismo_id for t in tramites_citados)


def _listar_todas_las_sesiones(conn) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, created_at FROM sesiones ORDER BY created_at DESC")
        return cur.fetchall()


def _organismos_de_tramites(conn, citados_por_sesion: dict[str, list[str]]) -> dict[str, int]:
    tramite_ids = {tid for citas in citados_por_sesion.values() for tid in citas}
    if not tramite_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, organismo_id FROM tramites WHERE id = ANY(%s)",
            (list(tramite_ids),),
        )
        return {tramite_id: organismo_id for tramite_id, organismo_id in cur.fetchall()}
```

Y agregar los imports que usan los tests nuevos al principio de `backend/tests/test_admin_chats_repository.py` (ya están `uuid`, `datetime`/`timedelta`/`timezone`, `sessions`, `chats_repository` — verificar que sigan ahí, no se tocan).

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_chats_repository.py -v`
Expected: PASS (todos, existentes + 6 nuevos).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/chats_repository.py backend/tests/test_admin_chats_repository.py
git commit -m "feat: filtrado de sesiones por organismo en chats_repository"
```

---

## Task 7: `agent/api.py` — login, me y activo

**Files:**
- Modify: `backend/agent/api.py:1-19` (imports), `:64-180` (login/logout/me)
- Modify: `backend/tests/test_admin_api.py`

**Interfaces:**
- Consumes: `admin_repository.crear_admin/obtener_admin_por_email/obtener_admin_por_id` (Task 2), `admin_security.crear_token` (Task 3), `dependencies.AdminActual/requiere_admin` (Task 4), `admin_tramites_repository.obtener_nombre_organismo` (Task 5).
- Produces: `POST /admin/login` y `GET /admin/me` devuelven `{"email": str, "rol": str, "organismo": str | None}`. Login falla `401` también si `admin["activo"]` es `False`.

- [ ] **Step 1: Actualizar los tests existentes que hoy comparan el body exacto**

En `backend/tests/test_admin_api.py`:

Cambiar el helper `_crear_admin` para poder parametrizar rol/organismo, con default `super_admin` (así el resto de tests del archivo, que asumen acceso total, no se rompen):

```python
def _crear_admin(
    conn, email="admin@macacha.gob.ar", password="secreta123", rol="super_admin", organismo_id=None
):
    admin_repository.crear_admin(conn, email, admin_security.hash_password(password), rol, organismo_id)
    conn.commit()
    return email, password
```

Actualizar los asserts de body exacto:

```python
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
    assert respuesta.json() == {"email": email, "rol": "super_admin", "organismo": None}
    assert "admin_session" in respuesta.cookies
```

```python
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
    assert respuesta.json() == {"email": email, "rol": "super_admin", "organismo": None}
```

Agregar dos tests nuevos (después de `test_login_email_inexistente_devuelve_401`):

```python
def test_login_admin_inactivo_devuelve_401(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    email, password = _crear_admin(db_conn)
    admin_id = admin_repository.obtener_admin_por_email(db_conn, email)["id"]
    admin_repository.editar_admin(db_conn, admin_id, rol="super_admin", organismo_id=None, activo=False)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post("/admin/login", json={"email": email, "password": password})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_login_admin_organismo_devuelve_rol_y_organismo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES ('Registro Civil') RETURNING id")
        organismo_id = cur.fetchone()[0]
    email, password = _crear_admin(
        db_conn, rol="admin_organismo", organismo_id=organismo_id
    )

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post("/admin/login", json={"email": email, "password": password})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"email": email, "rol": "admin_organismo", "organismo": "Registro Civil"}
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_api.py -v -k "login or me"`
Expected: FAIL (los bodies no incluyen `rol`/`organismo`, no hay chequeo de `activo`).

- [ ] **Step 3: Actualizar `api.py`**

En `backend/agent/api.py`, cambiar el import de dependencies (línea 19):

```python
from agent.admin.dependencies import AdminActual, requiere_admin, requiere_super_admin
```

Reemplazar `admin_login` (líneas 147-164):

```python
@app.post("/admin/login")
def admin_login(request: LoginRequest, response: Response, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin = admin_repository.obtener_admin_por_email(conn, request.email)

        if (
            admin is None
            or not admin["activo"]
            or not admin_security.verify_password(request.password, admin["password_hash"])
        ):
            raise HTTPException(status_code=401, detail="Credenciales inválidas")

        organismo = (
            admin_tramites_repository.obtener_nombre_organismo(conn, admin["organismo_id"])
            if admin["organismo_id"] is not None
            else None
        )

        token = admin_security.crear_token(admin)

    response.set_cookie(
        "admin_session",
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )
    return {"email": admin["email"], "rol": admin["rol"], "organismo": organismo}
```

Reemplazar `admin_me` (líneas 173-180):

```python
@app.get("/admin/me")
def admin_me(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        admin_db = admin_repository.obtener_admin_por_id(conn, admin.id)
        if admin_db is None or not admin_db["activo"]:
            raise HTTPException(status_code=401, detail="No autenticado")
        organismo = (
            admin_tramites_repository.obtener_nombre_organismo(conn, admin_db["organismo_id"])
            if admin_db["organismo_id"] is not None
            else None
        )
    return {"email": admin_db["email"], "rol": admin_db["rol"], "organismo": organismo}
```

Nota: el resto de endpoints (`admin_logout`, `admin_listar_sesiones`, etc.) siguen usando `admin_id: str = Depends(requiere_admin)` por ahora — se actualizan en las Tasks 8 y 9. No romperán con este cambio porque `requiere_admin` sigue siendo invocable igual (solo cambió lo que devuelve, de `str` a `AdminActual`); esos endpoints hoy no usan el valor de `admin_id` salvo para inyectar la dependencia, así que siguen funcionando aunque reciban un objeto en vez de un string sin usarlo.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_api.py -v`
Expected: PASS (todos, existentes actualizados + 2 nuevos).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_api.py
git commit -m "feat: login y me devuelven rol y organismo, bloquean admins inactivos"
```

---

## Task 8: `agent/api.py` — sesiones filtradas por organismo

**Files:**
- Modify: `backend/agent/api.py:183-205` (`admin_listar_sesiones`, `admin_obtener_sesion`)
- Modify: `backend/tests/test_admin_api.py`

**Interfaces:**
- Consumes: `admin_chats_repository.listar_sesiones_de_organismo/sesion_pertenece_a_organismo` (Task 6), `AdminActual` (Task 4).
- Produces: `GET /admin/sesiones` y `GET /admin/sesiones/{id}` filtran por organismo cuando `admin.rol == "admin_organismo"`.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `backend/tests/test_admin_api.py`, después de `test_obtener_sesion_devuelve_los_mensajes_completos`:

```python
def _crear_admin_organismo(conn, organismo_id, email="org@macacha.gob.ar", password="secreta123"):
    admin_repository.crear_admin(
        conn, email, admin_security.hash_password(password), rol="admin_organismo", organismo_id=organismo_id
    )
    conn.commit()
    return email, password


def _crear_organismo(conn, nombre):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def _crear_tramite(conn, tramite_id, organismo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial) VALUES (%s, %s, '', %s)",
            (tramite_id, organismo_id, tramite_id),
        )


def test_listar_sesiones_admin_organismo_solo_ve_las_de_su_organismo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = _crear_organismo(db_conn, "Registro Civil")
    organismo_ajeno = _crear_organismo(db_conn, "Rentas")
    _crear_tramite(db_conn, "RC-0001", organismo_propio)
    _crear_tramite(db_conn, "RE-0001", organismo_ajeno)

    sesion_propia = str(uuid.uuid4())
    sesion_ajena = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, sesion_propia)
    sessions.crear_sesion_si_no_existe(db_conn, sesion_ajena)
    sessions.guardar_mensaje(
        db_conn,
        sesion_propia,
        rol="assistant",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RC-0001"}'},
            }
        ],
    )
    sessions.guardar_mensaje(
        db_conn,
        sesion_ajena,
        rol="assistant",
        tool_calls=[
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RE-0001"}'},
            }
        ],
    )
    db_conn.commit()

    email, password = _crear_admin_organismo(db_conn, organismo_propio)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get("/admin/sesiones?page=1&page_size=20")
    finally:
        api.app.dependency_overrides.clear()

    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert [s["id"] for s in cuerpo["sesiones"]] == [sesion_propia]


def test_obtener_sesion_admin_organismo_sesion_ajena_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = _crear_organismo(db_conn, "Registro Civil")
    organismo_ajeno = _crear_organismo(db_conn, "Rentas")
    _crear_tramite(db_conn, "RE-0001", organismo_ajeno)

    sesion_ajena = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, sesion_ajena)
    sessions.guardar_mensaje(
        db_conn,
        sesion_ajena,
        rol="assistant",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RE-0001"}'},
            }
        ],
    )
    db_conn.commit()

    email, password = _crear_admin_organismo(db_conn, organismo_propio)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get(f"/admin/sesiones/{sesion_ajena}")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_obtener_sesion_admin_organismo_sesion_propia_devuelve_200(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = _crear_organismo(db_conn, "Registro Civil")
    _crear_tramite(db_conn, "RC-0001", organismo_propio)

    sesion_propia = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, sesion_propia)
    sessions.guardar_mensaje(
        db_conn,
        sesion_propia,
        rol="assistant",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "obtener_requisitos", "arguments": '{"tramite_id": "RC-0001"}'},
            }
        ],
    )
    db_conn.commit()

    email, password = _crear_admin_organismo(db_conn, organismo_propio)

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        client.post("/admin/login", json={"email": email, "password": password})
        respuesta = client.get(f"/admin/sesiones/{sesion_propia}")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_api.py -v -k organismo`
Expected: FAIL (los endpoints todavía no filtran por organismo).

- [ ] **Step 3: Actualizar los endpoints**

En `backend/agent/api.py`, reemplazar `admin_listar_sesiones` y `admin_obtener_sesion` (líneas 183-205):

```python
@app.get("/admin/sesiones")
def admin_listar_sesiones(
    page: int = 1,
    page_size: int = 20,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if admin.rol == "admin_organismo":
            sesiones, total = admin_chats_repository.listar_sesiones_de_organismo(
                conn, admin.organismo_id, page, page_size
            )
        else:
            sesiones = admin_chats_repository.listar_sesiones(conn, page, page_size)
            total = admin_chats_repository.contar_sesiones(conn)
    return {"sesiones": sesiones, "total": total, "page": page, "page_size": page_size}


@app.get("/admin/sesiones/{session_id}")
def admin_obtener_sesion(
    session_id: uuid.UUID,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if admin.rol == "admin_organismo":
            permitido = admin_chats_repository.sesion_pertenece_a_organismo(
                conn, str(session_id), admin.organismo_id
            )
        else:
            permitido = admin_chats_repository.sesion_existe(conn, str(session_id))

        if not permitido:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        return admin_chats_repository.obtener_mensajes_completos(conn, str(session_id))
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_api.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_api.py
git commit -m "feat: filtra sesiones de admin por organismo"
```

---

## Task 9: `agent/api.py` — trámites filtrados y validados por organismo

**Files:**
- Modify: `backend/agent/api.py:208-319` (`admin_listar_tramites`, `admin_listar_organismos`, `admin_obtener_tramite`, `admin_editar_tramite`, `admin_crear_tramite`)
- Modify: `backend/tests/test_admin_tramites_api.py`

**Interfaces:**
- Consumes: `admin_tramites_repository.listar_tramites/listar_organismos/obtener_organismo_id_de_tramite/obtener_nombre_organismo` (Task 5), `AdminActual` (Task 4).
- Produces: `/admin/tramites*` filtran/validan por organismo cuando `admin.rol == "admin_organismo"`. `GET /admin/organismos` ahora devuelve `list[{"id", "nombre"}]` en vez de `list[str]` (consumido por Task 13 en frontend).

- [ ] **Step 1: Actualizar el helper de login para aceptar rol/organismo**

En `backend/tests/test_admin_tramites_api.py`, cambiar `_crear_admin_y_loguear` para aceptar rol/organismo (default `super_admin`, igual criterio que en Task 7). Hasta ahora tenía la firma `(client, conn)` con email/password fijos — el test `test_listar_organismos_devuelve_id_y_nombre` (Task 5) la sigue usando sin pasar rol/organismo, así que el nuevo default no le cambia el comportamiento:

```python
def _crear_admin_y_loguear(client, conn, rol="super_admin", organismo_id=None, email="admin@macacha.gob.ar"):
    password = "secreta123"
    admin_repository.crear_admin(
        conn, email, admin_security.hash_password(password), rol, organismo_id
    )
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": password})
```

- [ ] **Step 2: Agregar los tests nuevos de filtrado/validación por organismo**

Agregar al final de `backend/tests/test_admin_tramites_api.py`:

```python
def test_listar_tramites_admin_organismo_solo_ve_los_suyos(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_ajeno = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_propio, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RE-0001", organismo_ajeno, "Pagos", "Pago de patente")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(
            client, db_conn, rol="admin_organismo", organismo_id=organismo_propio
        )
        respuesta = client.get("/admin/tramites")
    finally:
        api.app.dependency_overrides.clear()

    assert [t["id"] for t in respuesta.json()] == ["RC-0001"]


def test_obtener_tramite_admin_organismo_tramite_ajeno_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_ajeno = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RE-0001", organismo_ajeno, "Pagos", "Pago de patente")
    snapshot = {
        "id": "RE-0001",
        "organismo": "Rentas",
        "categoria": "Pagos",
        "nombre_oficial": "Pago de patente",
        "requisitos": [],
        "telefono_contacto": "",
        "email_contacto": "",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    repo.insert_version_with_chunks(db_conn, "RE-0001", 1, "hash-1", snapshot, chunks, [[0.0] * 1536])
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(
            client, db_conn, rol="admin_organismo", organismo_id=organismo_propio
        )
        respuesta = client.get("/admin/tramites/RE-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_editar_tramite_admin_organismo_tramite_ajeno_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_ajeno = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RE-0001", organismo_ajeno, "Pagos", "Pago de patente")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(
            client, db_conn, rol="admin_organismo", organismo_id=organismo_propio
        )
        respuesta = client.put(
            "/admin/tramites/RE-0001", json={"organismo": "Rentas", "nombre_oficial": "x"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_editar_tramite_admin_organismo_no_puede_cambiar_organismo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_propio, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
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
        "faq_generadas_automaticamente": False,
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, [[0.0] * 1536])
    db_conn.commit()

    payload = _payload_edicion(organismo="Rentas")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(
            client, db_conn, rol="admin_organismo", organismo_id=organismo_propio
        )
        respuesta = client.put("/admin/tramites/RC-0001", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 400


def test_crear_tramite_admin_organismo_no_puede_crear_para_otro_organismo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_organismo(db_conn, "Rentas")
    db_conn.commit()

    payload = {
        "organismo": "Rentas",
        "categoria": "",
        "nombre_oficial": "Trámite Nuevo",
        "descripcion": "",
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
        _crear_admin_y_loguear(
            client, db_conn, rol="admin_organismo", organismo_id=organismo_propio
        )
        respuesta = client.post("/admin/tramites", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 400


def test_crear_tramite_admin_organismo_puede_crear_para_su_organismo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_propio = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    payload = {
        "organismo": "Registro Civil",
        "categoria": "",
        "nombre_oficial": "Trámite Nuevo",
        "descripcion": "",
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
        _crear_admin_y_loguear(
            client, db_conn, rol="admin_organismo", organismo_id=organismo_propio
        )
        respuesta = client.post("/admin/tramites", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
```

- [ ] **Step 3: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_tramites_api.py -v -k organismo_devuelve or ajeno or organismo_no_puede or admin_organismo`
Expected: FAIL (los tests nuevos del Step 2 — los endpoints todavía no filtran/validan por organismo).

- [ ] **Step 4: Actualizar los endpoints**

En `backend/agent/api.py`, reemplazar el bloque `admin_listar_tramites` .. `admin_crear_tramite` (líneas 208-319):

```python
@app.get("/admin/tramites")
def admin_listar_tramites(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = admin.organismo_id if admin.rol == "admin_organismo" else None
        return admin_tramites_repository.listar_tramites(conn, organismo_id)


@app.get("/admin/organismos")
def admin_listar_organismos(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return admin_tramites_repository.listar_organismos(conn)


def _verificar_tramite_de_mi_organismo(conn, admin: AdminActual, tramite_id: str) -> None:
    if admin.rol != "admin_organismo":
        return
    organismo_del_tramite = admin_tramites_repository.obtener_organismo_id_de_tramite(conn, tramite_id)
    if organismo_del_tramite != admin.organismo_id:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")


def _verificar_payload_de_mi_organismo(conn, admin: AdminActual, organismo_payload: str) -> None:
    if admin.rol != "admin_organismo":
        return
    nombre_organismo_admin = admin_tramites_repository.obtener_nombre_organismo(conn, admin.organismo_id)
    if organismo_payload != nombre_organismo_admin:
        raise HTTPException(
            status_code=400, detail="No podés asignar un trámite a otro organismo"
        )


@app.get("/admin/tramites/{tramite_id}")
def admin_obtener_tramite(
    tramite_id: str, admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
        _verificar_tramite_de_mi_organismo(conn, admin, tramite_id)
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")
        return {
            "organismo": snapshot["organismo"],
            "categoria": snapshot["categoria"],
            "nombre_oficial": snapshot["nombre_oficial"],
            "descripcion": snapshot.get("descripcion", ""),
            "objetivo": snapshot.get("objetivo", ""),
            "requisitos": snapshot.get("requisitos", []),
            "pasos": snapshot.get("pasos", []),
            "costo": snapshot.get("costo", ""),
            "modalidad": snapshot.get("modalidad", ""),
            "duracion": snapshot.get("duracion", ""),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
            "problemas_frecuentes": snapshot.get("problemas_frecuentes", []),
            "sinonimos": snapshot.get("sinonimos", []),
            "keywords": snapshot.get("keywords", []),
            "enlaces_oficiales": snapshot.get("enlaces_oficiales", []),
            "preguntas_frecuentes": snapshot.get("preguntas_frecuentes", []),
        }


@app.put("/admin/tramites/{tramite_id}")
def admin_editar_tramite(
    tramite_id: str,
    request: TramitePayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
    openai_client=Depends(obtener_openai_client),
):
    with pool.connection() as conn:
        _verificar_tramite_de_mi_organismo(conn, admin, tramite_id)
        _verificar_payload_de_mi_organismo(conn, admin, request.organismo)

        if admin.rol != "admin_organismo" and obtener_snapshot_vigente(conn, tramite_id) is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")

        try:
            resultado = admin_tramite_editor.editar_tramite(
                conn, tramite_id, request.model_dump(), openai_client.generate_embeddings
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(
                status_code=502,
                detail="No se pudieron generar los embeddings. Verificá la configuración de OpenAI.",
            )
    return resultado


@app.post("/admin/tramites")
def admin_crear_tramite(
    request: TramitePayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
    openai_client=Depends(obtener_openai_client),
):
    with pool.connection() as conn:
        _verificar_payload_de_mi_organismo(conn, admin, request.organismo)
        try:
            resultado = admin_tramite_editor.crear_tramite(
                conn, request.model_dump(), openai_client.generate_embeddings
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise HTTPException(
                status_code=502,
                detail="No se pudieron generar los embeddings. Verificá la configuración de OpenAI.",
            )
    return resultado
```

Nota sobre `admin_editar_tramite`: para `admin_organismo`, `_verificar_tramite_de_mi_organismo` ya cubre tanto "no existe" como "es de otro organismo" con `404` (si `tramite_id` no existe, `obtener_organismo_id_de_tramite` devuelve `None`, que nunca es igual a un `organismo_id` entero). Por eso el chequeo original con `obtener_snapshot_vigente(...) is None` solo se ejecuta cuando `admin.rol != "admin_organismo"` — evita hacer ese chequeo dos veces para el caso `admin_organismo`.

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_tramites_api.py -v`
Expected: PASS (todos, existentes actualizados + 6 nuevos).

- [ ] **Step 6: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (todo — confirma que no rompimos nada en `test_admin_api.py`, `test_admin_repository.py`, etc. de tasks anteriores).

- [ ] **Step 7: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_tramites_api.py
git commit -m "feat: filtra y valida tramites de admin por organismo"
```

---

## Task 10: `agent/api.py` — endpoints de usuarios y organismos (solo super-admin)

**Files:**
- Modify: `backend/agent/api.py` (imports, nuevos Pydantic models, nuevos endpoints al final del archivo)
- Create: `backend/tests/test_admin_usuarios_api.py`

**Interfaces:**
- Consumes: `admin_repository.listar_admins/crear_admin/obtener_admin_por_email/obtener_admin_por_id/editar_admin` (Task 2), `admin_tramites_repository.obtener_organismo_id_por_nombre/crear_organismo` (Task 5), `requiere_super_admin` (Task 4).
- Produces:
  - `GET /admin/usuarios` → `list[dict]` (mismo shape que `listar_admins`).
  - `POST /admin/usuarios` → `{"ok": True}`, `400`/`409` en payload inconsistente/email duplicado.
  - `PUT /admin/usuarios/{admin_id}` → `{"ok": True}`, `400`/`404`.
  - `POST /admin/organismos` → `{"id": int, "nombre": str}`, `409` si ya existe.
  - Los cuatro devuelven `403` si el admin autenticado no es `super_admin` (vía `requiere_super_admin`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_usuarios_api.py`:

```python
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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_usuarios_api.py -v`
Expected: FAIL (`404` para todas las rutas — no existen).

- [ ] **Step 3: Implementar los endpoints**

En `backend/agent/api.py`, agregar `Literal` al import de `typing` al principio del archivo (agregar la línea si no existe un import de `typing`):

```python
from typing import Iterator, Literal
```

(reemplaza la línea existente `from typing import Iterator`).

Agregar al final del archivo:

```python
class UsuarioPayload(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=8)
    rol: Literal["super_admin", "admin_organismo"]
    organismo_id: int | None = None


class UsuarioEdicionPayload(BaseModel):
    rol: Literal["super_admin", "admin_organismo"]
    organismo_id: int | None = None
    activo: bool
    password: str | None = Field(default=None, min_length=8)


class OrganismoPayload(BaseModel):
    nombre: str = Field(min_length=1)


def _validar_consistencia_rol_organismo(rol: str, organismo_id: int | None) -> None:
    if rol == "admin_organismo" and organismo_id is None:
        raise HTTPException(
            status_code=400, detail="Un admin de organismo necesita un organismo asignado"
        )
    if rol == "super_admin" and organismo_id is not None:
        raise HTTPException(
            status_code=400, detail="Un super admin no puede tener un organismo asignado"
        )


@app.get("/admin/usuarios")
def admin_listar_usuarios(
    admin: AdminActual = Depends(requiere_super_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
        return admin_repository.listar_admins(conn)


@app.post("/admin/usuarios")
def admin_crear_usuario(
    request: UsuarioPayload,
    admin: AdminActual = Depends(requiere_super_admin),
    pool=Depends(obtener_pool),
):
    _validar_consistencia_rol_organismo(request.rol, request.organismo_id)
    password_hash = admin_security.hash_password(request.password)
    with pool.connection() as conn:
        if admin_repository.obtener_admin_por_email(conn, request.email) is not None:
            raise HTTPException(status_code=409, detail="Ya existe un admin con ese email")
        admin_repository.crear_admin(
            conn, request.email, password_hash, request.rol, request.organismo_id
        )
        conn.commit()
    return {"ok": True}


@app.put("/admin/usuarios/{admin_id}")
def admin_editar_usuario(
    admin_id: uuid.UUID,
    request: UsuarioEdicionPayload,
    admin: AdminActual = Depends(requiere_super_admin),
    pool=Depends(obtener_pool),
):
    _validar_consistencia_rol_organismo(request.rol, request.organismo_id)
    password_hash = admin_security.hash_password(request.password) if request.password else None
    with pool.connection() as conn:
        if admin_repository.obtener_admin_por_id(conn, str(admin_id)) is None:
            raise HTTPException(status_code=404, detail="Admin no encontrado")
        admin_repository.editar_admin(
            conn, str(admin_id), request.rol, request.organismo_id, request.activo, password_hash
        )
        conn.commit()
    return {"ok": True}


@app.post("/admin/organismos")
def admin_crear_organismo(
    request: OrganismoPayload,
    admin: AdminActual = Depends(requiere_super_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        if admin_tramites_repository.obtener_organismo_id_por_nombre(conn, request.nombre) is not None:
            raise HTTPException(status_code=409, detail="Ya existe un organismo con ese nombre")
        organismo_id = admin_tramites_repository.crear_organismo(conn, request.nombre)
        conn.commit()
    return {"id": organismo_id, "nombre": request.nombre}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_usuarios_api.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (todo).

- [ ] **Step 6: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_usuarios_api.py
git commit -m "feat: endpoints de gestion de usuarios y organismos para super admin"
```

---

## Task 11: `create_admin.py` — bootstrapping siempre como super-admin

**Files:**
- Modify: `backend/agent/admin/create_admin.py`
- Modify: `backend/tests/test_create_admin_cli.py`
- Modify: `docs/deploy-dokploy.md`

**Interfaces:**
- Consumes: `admin_repository.crear_admin` (Task 2, ahora con parámetro `rol`).
- Produces: `create_admin.main(argv, password_input=getpass)` sin cambios de firma; el admin creado siempre tiene `rol="super_admin"`.

- [ ] **Step 1: Actualizar el test**

Reemplazar `backend/tests/test_create_admin_cli.py`:

```python
from agent.admin import create_admin


class _FakeConn:
    def commit(self):
        pass


def test_main_crea_admin_super_admin_con_password_hasheada(monkeypatch, capsys):
    llamada = {}

    monkeypatch.setattr(create_admin, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        create_admin.security, "hash_password", lambda password: f"hash-de-{password}"
    )

    def _fake_crear_admin(conn, email, password_hash, rol):
        llamada["email"] = email
        llamada["password_hash"] = password_hash
        llamada["rol"] = rol

    monkeypatch.setattr(create_admin, "crear_admin", _fake_crear_admin)

    create_admin.main(["admin@macacha.gob.ar"], password_input=lambda prompt: "secreta123")

    assert llamada == {
        "email": "admin@macacha.gob.ar",
        "password_hash": "hash-de-secreta123",
        "rol": "super_admin",
    }
    assert "admin@macacha.gob.ar" in capsys.readouterr().out


def test_main_sin_email_imprime_uso_y_sale(capsys):
    try:
        create_admin.main([])
        assert False, "debería haber salido con sys.exit"
    except SystemExit as exc:
        assert exc.code == 1
    assert "Uso:" in capsys.readouterr().out
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd backend && .venv/bin/pytest tests/test_create_admin_cli.py -v`
Expected: FAIL (`_fake_crear_admin` recibe solo 3 posicionales hoy).

- [ ] **Step 3: Actualizar `create_admin.py`**

Reemplazar `backend/agent/admin/create_admin.py` completo:

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
    crear_admin(conn, email, password_hash, "super_admin")
    conn.commit()

    print(f"Admin creado (super_admin): {email}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd backend && .venv/bin/pytest tests/test_create_admin_cli.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Documentar el paso de migración manual en el runbook de deploy**

En `docs/deploy-dokploy.md`, después de la línea que dice `psql "<connection-string-de-produccion>" -f backend/db/schema.sql` (línea 38 según lo visto durante el brainstorming), agregar un paso nuevo indicando que, la primera vez que se aplica este cambio de schema, hay que promover al admin existente a super-admin:

```sql
UPDATE admins SET rol = 'super_admin' WHERE email = 'admin@macacha.gob.ar';
```

(Ubicar el texto exacto de esta adición dentro de la estructura de pasos numerados que ya tiene el runbook — leer el archivo antes de editarlo para insertarlo como un paso propio, no como un bloque de código suelto.)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/admin/create_admin.py backend/tests/test_create_admin_cli.py docs/deploy-dokploy.md
git commit -m "feat: create_admin.py crea siempre super_admin, documenta migracion"
```

---

## Task 12: Backend completo — verificación final

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS, todos los tests (existentes + nuevos de las Tasks 1-11).

- [ ] **Step 2: Si algo falla, arreglarlo antes de seguir a frontend**

No avanzar a la Task 13 con la suite de backend en rojo.

---

## Task 13: Frontend — `listarOrganismos` con id, `TramiteForm` con `organismoFijo`

**Files:**
- Modify: `frontend/lib/admin-tramites-api.ts`
- Modify: `frontend/components/TramiteForm.tsx`
- Modify: `frontend/app/admin/tramites/nuevo/page.tsx`
- Modify: `frontend/app/admin/tramites/[id]/page.tsx`

**Interfaces:**
- Consumes: `GET /admin/organismos` ahora devuelve `{id, nombre}[]` (Task 9).
- Produces:
  - `Organismo = { id: number; nombre: string }` (tipo nuevo, exportado desde `admin-tramites-api.ts`).
  - `listarOrganismos(): Promise<Organismo[]>` (antes `Promise<string[]>`).
  - `TramiteForm` gana la prop opcional `organismoFijo?: string`.

Usadas por Task 15 (formulario de usuarios reutiliza `Organismo`) y Task 17.

- [ ] **Step 1: Actualizar `admin-tramites-api.ts`**

En `frontend/lib/admin-tramites-api.ts`, agregar el tipo `Organismo` (después de `Faq`) y cambiar `listarOrganismos`:

```typescript
export type Organismo = { id: number; nombre: string };
```

```typescript
export async function listarOrganismos(): Promise<Organismo[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/organismos`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    throw new Error("No se pudieron cargar los organismos");
  }
  return respuesta.json();
}
```

- [ ] **Step 2: Actualizar `TramiteForm.tsx`**

En `frontend/components/TramiteForm.tsx`:

Cambiar el import y la firma de props:

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { ListaFAQ } from "./ListaFAQ";
import { ListaTextos } from "./ListaTextos";
import type { Organismo, TramiteDetalleAdmin } from "../lib/admin-tramites-api";

export function TramiteForm({
  valoresIniciales,
  organismosExistentes,
  organismoFijo,
  guardando,
  error,
  onGuardar,
}: {
  valoresIniciales: TramiteDetalleAdmin;
  organismosExistentes: Organismo[];
  organismoFijo?: string;
  guardando: boolean;
  error: string | null;
  onGuardar: (datos: TramiteDetalleAdmin) => void;
}) {
  const [datos, setDatos] = useState<TramiteDetalleAdmin>(
    organismoFijo ? { ...valoresIniciales, organismo: organismoFijo } : valoresIniciales
  );
  const [organismoEsNuevo, setOrganismoEsNuevo] = useState(
    !organismosExistentes.some((o) => o.nombre === valoresIniciales.organismo)
  );
```

Reemplazar el bloque del campo Organismo (dentro del JSX, el `<div>` que contiene la label "Organismo"):

```tsx
      <div>
        <label className="mb-1 block text-sm font-medium">Organismo</label>
        {organismoFijo ? (
          <input
            type="text"
            value={organismoFijo}
            disabled
            className="w-full rounded border border-gray-300 bg-gray-100 px-2 py-1 text-sm text-gray-500"
          />
        ) : organismoEsNuevo ? (
          <input
            type="text"
            value={datos.organismo}
            onChange={(e) => actualizar("organismo", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        ) : (
          <select
            value={datos.organismo}
            onChange={(e) => actualizar("organismo", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {organismosExistentes.map((organismo) => (
              <option key={organismo.id} value={organismo.nombre}>
                {organismo.nombre}
              </option>
            ))}
          </select>
        )}
        {!organismoFijo && (
          <button
            type="button"
            onClick={() => setOrganismoEsNuevo(!organismoEsNuevo)}
            className="mt-1 text-sm text-blue-700 underline"
          >
            {organismoEsNuevo ? "Elegir uno existente" : "Otro… (crear nuevo)"}
          </button>
        )}
      </div>
```

El resto del componente (categoría, nombre oficial, etc.) no cambia.

- [ ] **Step 3: Actualizar `nuevo/page.tsx` y `[id]/page.tsx`**

En `frontend/app/admin/tramites/nuevo/page.tsx`, cambiar el tipo de estado de organismos:

```tsx
import { Organismo, crearTramite, listarOrganismos, type TramiteDetalleAdmin } from "../../../../lib/admin-tramites-api";
```

```tsx
const [organismos, setOrganismos] = useState<Organismo[]>([]);
```

(El resto del archivo no cambia — no se aplica `organismoFijo` todavía, eso ocurre en la Task 17 cuando exista `useAdminActual`.)

En `frontend/app/admin/tramites/[id]/page.tsx`, mismo cambio de tipo:

```tsx
import { Organismo, editarTramite, listarOrganismos, obtenerTramiteAdmin, type TramiteDetalleAdmin } from "../../../../lib/admin-tramites-api";
```

```tsx
const [organismos, setOrganismos] = useState<Organismo[]>([]);
```

- [ ] **Step 4: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores de tipos.

- [ ] **Step 5: Correr los tests de frontend**

Run: `cd frontend && npm test`
Expected: PASS (los tests existentes no dependen de estos archivos).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/admin-tramites-api.ts frontend/components/TramiteForm.tsx frontend/app/admin/tramites/nuevo/page.tsx frontend/app/admin/tramites/\[id\]/page.tsx
git commit -m "feat: listarOrganismos devuelve id+nombre, TramiteForm soporta organismoFijo"
```

---

## Task 14: Frontend — `AdminAuthContext` y nav condicional

**Files:**
- Modify: `frontend/lib/admin-api.ts`
- Create: `frontend/hooks/useAdminActual.tsx`
- Modify: `frontend/app/admin/layout.tsx`

**Interfaces:**
- Consumes: `GET /admin/me` ahora devuelve `{email, rol, organismo}` (Task 7).
- Produces:
  - `AdminSesionInfo = { email: string; rol: "super_admin" | "admin_organismo"; organismo: string | null }` (exportado desde `admin-api.ts`).
  - `obtenerMe(): Promise<AdminSesionInfo | null>` — `null` si `401`.
  - `AdminAuthProvider` (componente), `useAdminActual(): AdminSesionInfo | null` (hook).

Usadas por Task 16 y 17.

- [ ] **Step 1: Agregar `obtenerMe` a `admin-api.ts`**

En `frontend/lib/admin-api.ts`, agregar el tipo y la función (después de los tipos existentes, antes de `login`):

```typescript
export type AdminSesionInfo = {
  email: string;
  rol: "super_admin" | "admin_organismo";
  organismo: string | null;
};
```

```typescript
export async function obtenerMe(): Promise<AdminSesionInfo | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/me`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    return null;
  }
  return respuesta.json();
}
```

- [ ] **Step 2: Crear el hook y provider**

Crear `frontend/hooks/useAdminActual.tsx`:

```tsx
"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { obtenerMe, type AdminSesionInfo } from "../lib/admin-api";

const AdminAuthContext = createContext<AdminSesionInfo | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<AdminSesionInfo | null>(null);

  useEffect(() => {
    obtenerMe().then(setAdmin);
  }, []);

  return <AdminAuthContext.Provider value={admin}>{children}</AdminAuthContext.Provider>;
}

export function useAdminActual(): AdminSesionInfo | null {
  return useContext(AdminAuthContext);
}
```

- [ ] **Step 3: Envolver `AdminLayout` con el provider y agregar el link condicional**

Reemplazar `frontend/app/admin/layout.tsx` completo:

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "../../lib/admin-api";
import { AdminAuthProvider, useAdminActual } from "../../hooks/useAdminActual";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminAuthProvider>
      <AdminLayoutInner>{children}</AdminLayoutInner>
    </AdminAuthProvider>
  );
}

function AdminLayoutInner({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const admin = useAdminActual();

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
            <li>
              <Link href="/admin/tramites" className="text-blue-700 hover:underline">
                Trámites
              </Link>
            </li>
            {admin?.rol === "super_admin" && (
              <li>
                <Link href="/admin/usuarios" className="text-blue-700 hover:underline">
                  Usuarios
                </Link>
              </li>
            )}
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

- [ ] **Step 4: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores de tipos.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/admin-api.ts frontend/hooks/useAdminActual.tsx frontend/app/admin/layout.tsx
git commit -m "feat: AdminAuthContext y link de Usuarios condicional a super_admin"
```

---

## Task 15: Frontend — `lib/admin-usuarios-api.ts`

**Files:**
- Create: `frontend/lib/admin-usuarios-api.ts`

**Interfaces:**
- Consumes: `GET/POST/PUT /admin/usuarios`, `POST /admin/organismos` (Task 10).
- Produces:
  - `AdminUsuario = { id: string; email: string; rol: "super_admin" | "admin_organismo"; organismo: string | null; activo: boolean }`
  - `UsuarioFormValores = { email: string; password: string; rol: "super_admin" | "admin_organismo"; organismo_id: number | null; activo: boolean }`
  - `obtenerUsuarios(): Promise<AdminUsuario[]>`
  - `crearUsuario(datos: UsuarioFormValores): Promise<void>`
  - `editarUsuario(id: string, datos: UsuarioFormValores): Promise<void>`
  - `crearOrganismo(nombre: string): Promise<Organismo>` (tipo `Organismo` importado de `admin-tramites-api.ts`, Task 13).

Usadas por Task 16.

- [ ] **Step 1: Crear el archivo**

Crear `frontend/lib/admin-usuarios-api.ts`:

```typescript
import type { Organismo } from "./admin-tramites-api";

export type AdminUsuario = {
  id: string;
  email: string;
  rol: "super_admin" | "admin_organismo";
  organismo: string | null;
  activo: boolean;
};

export type UsuarioFormValores = {
  email: string;
  password: string;
  rol: "super_admin" | "admin_organismo";
  organismo_id: number | null;
  activo: boolean;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function parsearOLanzar<T>(respuesta: Response, mensajePorDefecto: string): Promise<T> {
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => null);
    throw new Error(cuerpo?.detail ?? mensajePorDefecto);
  }
  return respuesta.json();
}

export async function obtenerUsuarios(): Promise<AdminUsuario[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/usuarios`, { credentials: "include" });
  return parsearOLanzar(respuesta, "No se pudo cargar la lista de usuarios");
}

export async function crearUsuario(datos: UsuarioFormValores): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/admin/usuarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(datos),
  });
  await parsearOLanzar(respuesta, "No se pudo crear el usuario");
}

export async function editarUsuario(id: string, datos: UsuarioFormValores): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/admin/usuarios/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({
      rol: datos.rol,
      organismo_id: datos.organismo_id,
      activo: datos.activo,
      password: datos.password || null,
    }),
  });
  await parsearOLanzar(respuesta, "No se pudo editar el usuario");
}

export async function crearOrganismo(nombre: string): Promise<Organismo> {
  const respuesta = await fetch(`${BASE_URL}/admin/organismos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ nombre }),
  });
  return parsearOLanzar(respuesta, "No se pudo crear el organismo");
}
```

Nota: `editarUsuario` arma el body a mano (en vez de mandar `datos` completo) porque `UsuarioFormValores` incluye `email` (no editable — el backend no lo espera en `UsuarioEdicionPayload`) y `password` vacío se traduce a `null` explícito para que el backend interprete "no cambiar la contraseña".

- [ ] **Step 2: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores de tipos.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/admin-usuarios-api.ts
git commit -m "feat: cliente API de usuarios y organismos"
```

---

## Task 16: Frontend — pantalla `/admin/usuarios`

**Files:**
- Create: `frontend/components/UsuarioForm.tsx`
- Create: `frontend/app/admin/usuarios/page.tsx`

**Interfaces:**
- Consumes: `UsuarioFormValores`, `AdminUsuario`, `obtenerUsuarios/crearUsuario/editarUsuario/crearOrganismo` (Task 15), `Organismo`, `listarOrganismos` (Task 13).
- Produces: pantalla completa de gestión de usuarios, alcanzable en `/admin/usuarios`.

- [ ] **Step 1: Crear `UsuarioForm.tsx`**

Crear `frontend/components/UsuarioForm.tsx`:

```tsx
"use client";

import { useState, type FormEvent } from "react";
import type { Organismo } from "../lib/admin-tramites-api";
import type { UsuarioFormValores } from "../lib/admin-usuarios-api";

export function UsuarioForm({
  valoresIniciales,
  organismos,
  esEdicion,
  guardando,
  error,
  onGuardar,
  onCancelar,
}: {
  valoresIniciales: UsuarioFormValores;
  organismos: Organismo[];
  esEdicion: boolean;
  guardando: boolean;
  error: string | null;
  onGuardar: (datos: UsuarioFormValores) => void;
  onCancelar: () => void;
}) {
  const [datos, setDatos] = useState<UsuarioFormValores>(valoresIniciales);

  function actualizar<K extends keyof UsuarioFormValores>(campo: K, valor: UsuarioFormValores[K]) {
    setDatos((anterior) => ({ ...anterior, [campo]: valor }));
  }

  function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    onGuardar(datos);
  }

  const puedeGuardar =
    datos.email.trim() !== "" &&
    (esEdicion || datos.password.trim().length >= 8) &&
    (datos.rol === "super_admin" || datos.organismo_id !== null);

  return (
    <form onSubmit={handleSubmit} className="max-w-md space-y-3 rounded border border-gray-200 p-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Email</label>
        <input
          type="email"
          value={datos.email}
          disabled={esEdicion}
          onChange={(e) => actualizar("email", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm disabled:bg-gray-100"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          {esEdicion ? "Nueva contraseña (dejar en blanco para no cambiar)" : "Contraseña"}
        </label>
        <input
          type="password"
          value={datos.password}
          onChange={(e) => actualizar("password", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Rol</label>
        <select
          value={datos.rol}
          onChange={(e) => actualizar("rol", e.target.value as UsuarioFormValores["rol"])}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        >
          <option value="admin_organismo">Admin de organismo</option>
          <option value="super_admin">Super admin</option>
        </select>
      </div>

      {datos.rol === "admin_organismo" && (
        <div>
          <label className="mb-1 block text-sm font-medium">Organismo</label>
          <select
            value={datos.organismo_id ?? ""}
            onChange={(e) => actualizar("organismo_id", e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          >
            <option value="">Elegir…</option>
            {organismos.map((organismo) => (
              <option key={organismo.id} value={organismo.id}>
                {organismo.nombre}
              </option>
            ))}
          </select>
        </div>
      )}

      {esEdicion && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={datos.activo}
            onChange={(e) => actualizar("activo", e.target.checked)}
          />
          Activo
        </label>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!puedeGuardar || guardando}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {guardando ? "Guardando…" : "Guardar"}
        </button>
        <button
          type="button"
          onClick={onCancelar}
          className="rounded px-4 py-2 text-sm text-gray-500"
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Crear `app/admin/usuarios/page.tsx`**

Crear `frontend/app/admin/usuarios/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { UsuarioForm } from "../../../components/UsuarioForm";
import { listarOrganismos, type Organismo } from "../../../lib/admin-tramites-api";
import {
  crearOrganismo,
  crearUsuario,
  editarUsuario,
  obtenerUsuarios,
  type AdminUsuario,
  type UsuarioFormValores,
} from "../../../lib/admin-usuarios-api";

const VALORES_VACIOS: UsuarioFormValores = {
  email: "",
  password: "",
  rol: "admin_organismo",
  organismo_id: null,
  activo: true,
};

export default function UsuariosPage() {
  const [usuarios, setUsuarios] = useState<AdminUsuario[] | null>(null);
  const [organismos, setOrganismos] = useState<Organismo[]>([]);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [editando, setEditando] = useState<AdminUsuario | "nuevo" | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [errorGuardado, setErrorGuardado] = useState<string | null>(null);
  const [nombreOrganismoNuevo, setNombreOrganismoNuevo] = useState("");
  const [errorOrganismo, setErrorOrganismo] = useState<string | null>(null);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const [listaUsuarios, listaOrganismos] = await Promise.all([
        obtenerUsuarios(),
        listarOrganismos(),
      ]);
      setUsuarios(listaUsuarios);
      setOrganismos(listaOrganismos);
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }

  async function handleCrearOrganismo() {
    if (!nombreOrganismoNuevo.trim()) return;
    setErrorOrganismo(null);
    try {
      await crearOrganismo(nombreOrganismoNuevo.trim());
      setNombreOrganismoNuevo("");
      setOrganismos(await listarOrganismos());
    } catch (err) {
      setErrorOrganismo(err instanceof Error ? err.message : "No se pudo crear el organismo");
    }
  }

  async function handleGuardar(datos: UsuarioFormValores) {
    setGuardando(true);
    setErrorGuardado(null);
    try {
      if (editando === "nuevo") {
        await crearUsuario(datos);
      } else if (editando) {
        await editarUsuario(editando.id, datos);
      }
      setEditando(null);
      await cargar();
    } catch (err) {
      setErrorGuardado(err instanceof Error ? err.message : "No se pudo guardar el usuario");
    } finally {
      setGuardando(false);
    }
  }

  function valoresParaEditar(usuario: AdminUsuario): UsuarioFormValores {
    return {
      email: usuario.email,
      password: "",
      rol: usuario.rol,
      organismo_id: organismos.find((o) => o.nombre === usuario.organismo)?.id ?? null,
      activo: usuario.activo,
    };
  }

  if (cargando) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la lista de usuarios</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Usuarios</h1>
        <button
          onClick={() => setEditando("nuevo")}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
        >
          Nuevo usuario
        </button>
      </div>

      <div className="mb-4 flex items-end gap-2">
        <div>
          <label className="mb-1 block text-sm font-medium">Nuevo organismo</label>
          <input
            type="text"
            value={nombreOrganismoNuevo}
            onChange={(e) => setNombreOrganismoNuevo(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <button onClick={handleCrearOrganismo} className="rounded bg-gray-200 px-3 py-1.5 text-sm">
          Crear organismo
        </button>
        {errorOrganismo && <p className="text-sm text-red-600">{errorOrganismo}</p>}
      </div>

      {editando && (
        <div className="mb-4">
          <UsuarioForm
            valoresIniciales={editando === "nuevo" ? VALORES_VACIOS : valoresParaEditar(editando)}
            organismos={organismos}
            esEdicion={editando !== "nuevo"}
            guardando={guardando}
            error={errorGuardado}
            onGuardar={handleGuardar}
            onCancelar={() => setEditando(null)}
          />
        </div>
      )}

      {usuarios && usuarios.length === 0 ? (
        <p className="text-sm text-gray-500">Todavía no hay usuarios cargados</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="p-2">Email</th>
              <th className="p-2">Rol</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Activo</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {usuarios!.map((usuario) => (
              <tr key={usuario.id} className="border-b border-gray-100">
                <td className="p-2">{usuario.email}</td>
                <td className="p-2">
                  {usuario.rol === "super_admin" ? "Super admin" : "Admin de organismo"}
                </td>
                <td className="p-2">{usuario.organismo ?? "—"}</td>
                <td className="p-2">{usuario.activo ? "Sí" : "No"}</td>
                <td className="p-2">
                  <button
                    onClick={() => setEditando(usuario)}
                    className="text-sm text-blue-700 underline"
                  >
                    Editar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores de tipos.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/UsuarioForm.tsx frontend/app/admin/usuarios/page.tsx
git commit -m "feat: pantalla de gestion de usuarios y organismos"
```

---

## Task 17: Frontend — `organismoFijo` en las páginas de trámites

**Files:**
- Modify: `frontend/app/admin/tramites/nuevo/page.tsx`
- Modify: `frontend/app/admin/tramites/[id]/page.tsx`

**Interfaces:**
- Consumes: `useAdminActual` (Task 14), `organismoFijo` prop de `TramiteForm` (Task 13).

- [ ] **Step 1: Pasar `organismoFijo` en `nuevo/page.tsx`**

En `frontend/app/admin/tramites/nuevo/page.tsx`, agregar el import y usar el hook:

```tsx
import { useAdminActual } from "../../../../hooks/useAdminActual";
```

```tsx
export default function NuevoTramitePage() {
  const router = useRouter();
  const admin = useAdminActual();
  const [organismos, setOrganismos] = useState<Organismo[]>([]);
  // ... resto sin cambios ...

  return (
    <TramiteForm
      valoresIniciales={VALORES_VACIOS}
      organismosExistentes={organismos}
      organismoFijo={admin?.rol === "admin_organismo" ? admin.organismo ?? undefined : undefined}
      guardando={guardando}
      error={error}
      onGuardar={handleGuardar}
    />
  );
}
```

- [ ] **Step 2: Pasar `organismoFijo` en `[id]/page.tsx`**

En `frontend/app/admin/tramites/[id]/page.tsx`, mismo patrón:

```tsx
import { useAdminActual } from "../../../../hooks/useAdminActual";
```

```tsx
export default function EditarTramitePage() {
  const params = useParams<{ id: string }>();
  const admin = useAdminActual();
  // ... resto sin cambios ...

  return (
    <div>
      {confirmacion && <p className="p-4 pb-0 text-sm text-green-700">{confirmacion}</p>}
      <TramiteForm
        valoresIniciales={tramite}
        organismosExistentes={organismos}
        organismoFijo={admin?.rol === "admin_organismo" ? admin.organismo ?? undefined : undefined}
        guardando={guardando}
        error={errorGuardado}
        onGuardar={handleGuardar}
      />
    </div>
  );
}
```

- [ ] **Step 3: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores de tipos.

- [ ] **Step 4: Correr los tests de frontend una vez más**

Run: `cd frontend && npm test`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/admin/tramites/nuevo/page.tsx frontend/app/admin/tramites/\[id\]/page.tsx
git commit -m "feat: fija el organismo en el formulario de tramites para admin_organismo"
```

---

## Task 18: Verificación end-to-end

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Suite completa de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS, todos.

- [ ] **Step 2: Suite completa de frontend**

Run: `cd frontend && npm test`
Expected: PASS, todos.

- [ ] **Step 3: Typecheck completo de frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 4: Levantar la app y probar manualmente el flujo de super-admin**

Seguir `.claude/skills/run-macacha/SKILL.md` para levantar backend + frontend + Postgres local. Aplicar el schema actualizado a la base local:

```bash
docker compose up -d postgres
psql "postgresql://macacha:macacha@localhost:5432/macacha" -f backend/db/schema.sql
cd backend && echo "<password-de-prueba>" | .venv/bin/python -m agent.admin.create_admin super@macacha.local
```

Con el driver del skill (`.claude/skills/run-macacha/driver.mjs`), loguearse como `super@macacha.local`, navegar a `/admin/usuarios`, crear un organismo, crear un admin de organismo asignado a ese organismo, verificar que aparece en la tabla. Sacar screenshot.

- [ ] **Step 5: Probar el flujo de admin de organismo**

Loguearse con el admin de organismo recién creado. Verificar: no ve el link "Usuarios" en el nav; `/admin/tramites` solo muestra trámites de su organismo (si no hay ninguno todavía, crear uno de prueba primero como el super-admin, o crearlo como este mismo admin y confirmar que el campo Organismo aparece fijo, no editable); `/admin/chats` solo muestra chats que citaron trámites de su organismo.

- [ ] **Step 6: Limpiar los datos de prueba creados en el paso anterior**

Si se usó la base remota en vez de la local por error, revisar `.env` — el proyecto ya documenta en `.claude/skills/run-macacha/SKILL.md` que `DATABASE_URL` apunta a una base remota real por defecto; para esta verificación usar explícitamente la base local (`postgresql://macacha:macacha@localhost:5432/macacha`), no la del `.env` committeado.
