# Casilla de mail de contacto por organismo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el aviso de una solicitud de contacto llegue a una casilla de mail propia de cada organismo, cargada desde la sección Contacto del panel admin.

**Architecture:** Columna nueva `organismos.email_contacto`. `resolver_destinatarios` usa esa casilla si existe y, si no, el comportamiento actual. Dos endpoints (`GET`/`PUT /admin/contacto/casillas…`) con permisos por rol, y un bloque nuevo en la pantalla Contacto. La validación del email vive en una función pura del backend y en otra del frontend con la misma regla.

**Tech Stack:** FastAPI + psycopg + pytest (backend, `backend/.venv`); Next.js + React + vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-10-01-casilla-contacto-organismo-design.md`

## Global Constraints

- Una sola dirección por organismo. `NULL` significa "sin casilla"; **nunca** se guarda una cadena vacía: vaciar el campo guarda `NULL`.
- Valor no vacío: se recorta, máximo **254** caracteres y debe cumplir el patrón `^[^@\s]+@[^@\s]+\.[^@\s]+$` (sin espacios, un solo `@`, un punto en el dominio). Si no cumple: **422** y no se escribe nada.
- `GET /admin/contacto/casillas`: super admin ve **todos** los organismos ordenados por nombre; admin de organismo ve **solo el suyo**.
- `PUT /admin/contacto/casillas/{organismo_id}` con `{"email_contacto": str | null}`: un admin de organismo sobre un organismo distinto del suyo recibe **404**, y ese chequeo va **antes** que la validación del email (404, no 422); un organismo inexistente también devuelve **404**. Responde `{"id", "nombre", "email_contacto"}`.
- Destinatarios: casilla del organismo → `[casilla]`; si no hay casilla, los emails de los admins activos del organismo; si tampoco hay, los de los super admins. Solicitudes sin organismo → super admins.
- Las rutas `/admin/contacto/casillas` y `/admin/contacto/casillas/{organismo_id}` se definen en `api.py` **antes** de `/admin/contacto/{solicitud_id}`, o FastAPI las captura como un id.
- Textos de la interfaz en español rioplatense (voseo). Comentarios del código con la misma densidad del código existente (pocos).
- Backend: ejecutar desde `backend/` con `.venv/bin/pytest`; los tests usan la base `macacha_test` del `docker compose` (`docker compose up -d postgres`). Frontend: desde `frontend/` con `npx vitest run` y `npx tsc --noEmit`.
- Las verificaciones visuales se hacen **solo** contra la base de test (nunca la de `.env`, que es la de producción).
- No hacer push ni tocar `frontend/package.json` / `frontend/package-lock.json`.

## Review Focus

Condiciones que el spec implica pero que ninguna tarea cubriría por defecto. Cada línea tiene su test en la tarea indicada.

1. `GET /admin/contacto/casillas` no debe ser capturado por la ruta `/admin/contacto/{solicitud_id}` (que devolvería 422) (Task 4).
2. Casilla con espacios alrededor → se recorta; solo espacios → se guarda `NULL` y no una cadena vacía (Tasks 2 y 3).
3. Emails con forma rara que "parecen" válidos (`a@b`, `a b@c.com`, `a@@b.com`, `@x.com`) → se rechazan sin escribir (Tasks 2, 4 y 5).
4. Un admin de organismo que edita otro organismo con un email **inválido** recibe 404, no 422 (no se filtra qué organismos existen) (Task 4).
5. Casilla vaciada → el aviso vuelve al respaldo (emails de los admins) (Task 3).
6. La casilla de un organismo no se usa para solicitudes de otro organismo ni para las que no tienen organismo (Task 3).
7. Al guardar con éxito la pantalla dice "Casilla guardada." o "Se quitó la casilla." según corresponda, y nunca "guardada" si el servidor devolvió error (Tasks 5 y 6).

---

## File Structure

**Backend — crear**
- `backend/agent/admin/email_contacto.py` — normalización y validación del email de la casilla.
- `backend/tests/test_email_contacto.py`

**Backend — modificar**
- `backend/db/schema.sql` — columna `email_contacto` y su restricción de largo.
- `backend/agent/admin/contacto_repository.py` — `listar_casillas`, `guardar_casilla`, `resolver_destinatarios`.
- `backend/agent/api.py` — endpoints de casillas.
- `backend/tests/test_admin_contacto_repository.py`, `backend/tests/test_admin_contacto_api.py`, `backend/tests/test_contacto_api.py`, `backend/tests/test_schema_smoke.py`.
- `backend/agent/mail.py`, `backend/tests/test_mail.py` — arreglo del puerto 465 (ya hecho, solo se commitea en la Task 1).

**Frontend — crear**
- `frontend/lib/email-contacto.ts` + `frontend/lib/email-contacto.test.ts`
- `frontend/components/CasillasContacto.tsx`

**Frontend — modificar**
- `frontend/lib/admin-contacto-api.ts` — tipo `Casilla`, `listarCasillas`, `guardarCasilla`.
- `frontend/app/admin/contacto/page.tsx` — monta el bloque.

---

### Task 1: Commitear el arreglo del puerto 465

El cambio ya está hecho en el árbol de trabajo (`SMTP_SSL` para el puerto 465, `SMTP` + STARTTLS para el resto). Sin él ninguna casilla recibiría nada en producción.

**Files:**
- Modify (ya modificados, sin commitear): `backend/agent/mail.py`, `backend/tests/test_mail.py`

**Interfaces:**
- Produces: `mail.enviar_mail(destinatarios: list[str], asunto: str, cuerpo_texto: str) -> None`, sin cambio de firma.

- [ ] **Step 1: Verificar que los tests del arreglo pasan**

Run (desde `backend/`): `.venv/bin/pytest tests/test_mail.py -v`
Expected: 4 PASS, entre ellos `test_enviar_mail_en_puerto_465_usa_ssl_implicito_sin_starttls` y `test_enviar_mail_en_puerto_587_sigue_usando_starttls`.

- [ ] **Step 2: Verificar que el diff es solo el esperado**

Run: `git diff --stat -- backend/agent/mail.py backend/tests/test_mail.py`
Expected: solo esos dos archivos.

- [ ] **Step 3: Commit**

```bash
git add backend/agent/mail.py backend/tests/test_mail.py
git commit -m "fix: envía el mail con SSL implícito cuando el puerto SMTP es 465"
```

---

### Task 2: Validación del email de la casilla (backend)

**Files:**
- Create: `backend/agent/admin/email_contacto.py`
- Test: `backend/tests/test_email_contacto.py`

**Interfaces:**
- Produces:
  - `email_contacto.MAX_LONGITUD_EMAIL: int` (254).
  - `email_contacto.normalizar_email_contacto(valor: str | None) -> str | None`: devuelve el email recortado, `None` si el valor es `None`, vacío o solo espacios; lanza `ValueError` (con un mensaje en español) si el valor no vacío no cumple el patrón o supera los 254 caracteres.

- [ ] **Step 1: Write the failing tests**

Crear `backend/tests/test_email_contacto.py`:

```python
import pytest

from agent.admin.email_contacto import MAX_LONGITUD_EMAIL, normalizar_email_contacto


def test_none_devuelve_none():
    assert normalizar_email_contacto(None) is None


@pytest.mark.parametrize("valor", ["", "   ", "\n\t "])
def test_vacio_o_solo_espacios_devuelve_none_y_no_cadena_vacia(valor):
    assert normalizar_email_contacto(valor) is None


def test_recorta_los_espacios_alrededor():
    assert normalizar_email_contacto("  mesa@salta.gob.ar \n") == "mesa@salta.gob.ar"


@pytest.mark.parametrize("valor", ["mesa@salta.gob.ar", "a@b.co", "nombre.apellido+tag@dominio.com.ar"])
def test_acepta_emails_validos(valor):
    assert normalizar_email_contacto(valor) == valor


@pytest.mark.parametrize(
    "valor",
    ["sin-arroba", "a@b", "a b@c.com", "a@@b.com", "@x.com", "a@", "a@x .com", "dos@a.com tres@b.com"],
)
def test_rechaza_emails_con_forma_invalida(valor):
    with pytest.raises(ValueError):
        normalizar_email_contacto(valor)


def test_acepta_exactamente_el_largo_maximo():
    valor = "a" * (MAX_LONGITUD_EMAIL - len("@x.co")) + "@x.co"
    assert len(valor) == MAX_LONGITUD_EMAIL
    assert normalizar_email_contacto(valor) == valor


def test_rechaza_un_caracter_de_mas():
    valor = "a" * (MAX_LONGITUD_EMAIL - len("@x.co") + 1) + "@x.co"
    assert len(valor) == MAX_LONGITUD_EMAIL + 1
    with pytest.raises(ValueError):
        normalizar_email_contacto(valor)
```

- [ ] **Step 2: Run tests to verify they fail**

Run (desde `backend/`): `.venv/bin/pytest tests/test_email_contacto.py -v`
Expected: FAIL en la colección (`ModuleNotFoundError: No module named 'agent.admin.email_contacto'`).

- [ ] **Step 3: Write minimal implementation**

Crear `backend/agent/admin/email_contacto.py`:

```python
import re

MAX_LONGITUD_EMAIL = 254
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email_contacto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = valor.strip()
    if not limpio:
        return None
    if len(limpio) > MAX_LONGITUD_EMAIL or not _PATRON_EMAIL.match(limpio):
        raise ValueError("Ingresá un email válido, por ejemplo mesa@organismo.gob.ar")
    return limpio
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_email_contacto.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/email_contacto.py backend/tests/test_email_contacto.py
git commit -m "feat: validación del email de la casilla de contacto"
```

---

### Task 3: Columna, repositorio y destinatarios

**Files:**
- Modify: `backend/db/schema.sql` (al final)
- Modify: `backend/tests/test_schema_smoke.py`
- Modify: `backend/agent/admin/contacto_repository.py`
- Test: `backend/tests/test_admin_contacto_repository.py`

**Interfaces:**
- Consumes: nada de tareas anteriores (la validación se aplica en la capa de API, Task 4).
- Produces:
  - Columna `organismos.email_contacto TEXT NULL`.
  - `contacto_repository.listar_casillas(conn, organismo_id: int | None) -> list[dict]`: `[{"id": int, "nombre": str, "email_contacto": str | None}]`. Con `organismo_id=None` devuelve todos ordenados por nombre; con un id devuelve solo ese organismo (lista vacía si no existe).
  - `contacto_repository.guardar_casilla(conn, organismo_id: int, email_contacto: str | None) -> dict | None`: actualiza y devuelve `{"id", "nombre", "email_contacto"}`, o `None` si el organismo no existe. No hace commit.
  - `contacto_repository.resolver_destinatarios(conn, organismo_id: int | None) -> list[str]` ahora prioriza la casilla.

- [ ] **Step 1: Agregar la columna al schema y aplicarla a la base de test**

Agregar al final de `backend/db/schema.sql`:

```sql

ALTER TABLE organismos ADD COLUMN IF NOT EXISTS email_contacto TEXT;
ALTER TABLE organismos DROP CONSTRAINT IF EXISTS organismos_email_contacto_largo;
ALTER TABLE organismos ADD CONSTRAINT organismos_email_contacto_largo
    CHECK (email_contacto IS NULL OR char_length(email_contacto) <= 254);
```

Aplicarlo a la base de test (idempotente; correr desde la raíz del repo):

Run: `docker compose up -d postgres && docker exec -i macacha-postgres-1 psql -U macacha -d macacha_test < backend/db/schema.sql 2>&1 | grep -E "ERROR" ; echo "exit: $?"`
Expected: no imprime ninguna línea con `ERROR` (el `exit: 1` del `grep` significa "no encontró errores").

Agregar a `backend/tests/test_schema_smoke.py` un test al final:

```python
def test_organismos_tiene_columna_email_contacto(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'organismos' AND column_name = 'email_contacto'
            """
        )
        assert cur.fetchone() is not None
```

Run: `cd backend && .venv/bin/pytest tests/test_schema_smoke.py -v`
Expected: PASS (la columna ya existe en la base de test).

- [ ] **Step 2: Write the failing tests**

Agregar al final de `backend/tests/test_admin_contacto_repository.py`:

```python
def test_listar_casillas_sin_filtro_devuelve_todos_ordenados_por_nombre(db_conn, clean_db):
    rentas = repo.upsert_organismo(db_conn, "Rentas")
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    contacto_repository.guardar_casilla(db_conn, rentas, "rentas@x.com")
    db_conn.commit()

    casillas = contacto_repository.listar_casillas(db_conn, None)

    assert casillas == [
        {"id": registro, "nombre": "Registro Civil", "email_contacto": None},
        {"id": rentas, "nombre": "Rentas", "email_contacto": "rentas@x.com"},
    ]


def test_listar_casillas_con_organismo_devuelve_solo_ese(db_conn, clean_db):
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_organismo(db_conn, "Rentas")
    db_conn.commit()

    casillas = contacto_repository.listar_casillas(db_conn, registro)

    assert [c["nombre"] for c in casillas] == ["Registro Civil"]


def test_listar_casillas_de_organismo_inexistente_devuelve_lista_vacia(db_conn, clean_db):
    assert contacto_repository.listar_casillas(db_conn, 99999) == []


def test_guardar_casilla_actualiza_y_devuelve_el_organismo(db_conn, clean_db):
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    guardada = contacto_repository.guardar_casilla(db_conn, registro, "mesa@x.com")
    db_conn.commit()

    assert guardada == {"id": registro, "nombre": "Registro Civil", "email_contacto": "mesa@x.com"}
    assert contacto_repository.listar_casillas(db_conn, registro)[0]["email_contacto"] == "mesa@x.com"


def test_guardar_casilla_none_borra_la_casilla_y_queda_null(db_conn, clean_db):
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    contacto_repository.guardar_casilla(db_conn, registro, "mesa@x.com")

    contacto_repository.guardar_casilla(db_conn, registro, None)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT email_contacto IS NULL FROM organismos WHERE id = %s", (registro,))
        assert cur.fetchone()[0] is True


def test_guardar_casilla_de_organismo_inexistente_devuelve_none(db_conn, clean_db):
    assert contacto_repository.guardar_casilla(db_conn, 99999, "mesa@x.com") is None


def test_resolver_destinatarios_prioriza_la_casilla_sobre_los_admins(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "org@x.com", rol="admin_organismo", organismo_id=organismo_id)
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    contacto_repository.guardar_casilla(db_conn, organismo_id, "mesa@registro.gob.ar")
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["mesa@registro.gob.ar"]


def test_resolver_destinatarios_con_casilla_borrada_vuelve_al_respaldo_de_admins(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "org@x.com", rol="admin_organismo", organismo_id=organismo_id)
    contacto_repository.guardar_casilla(db_conn, organismo_id, "mesa@registro.gob.ar")
    contacto_repository.guardar_casilla(db_conn, organismo_id, None)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["org@x.com"]


def test_resolver_destinatarios_no_usa_la_casilla_de_otro_organismo(db_conn, clean_db):
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    rentas = repo.upsert_organismo(db_conn, "Rentas")
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    contacto_repository.guardar_casilla(db_conn, rentas, "rentas@x.com")
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, registro) == ["super@x.com"]


def test_resolver_destinatarios_sin_organismo_ignora_todas_las_casillas(db_conn, clean_db):
    registro = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    contacto_repository.guardar_casilla(db_conn, registro, "mesa@x.com")
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, None) == ["super@x.com"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_admin_contacto_repository.py -v`
Expected: FAIL en los 10 tests nuevos (`AttributeError: module ... has no attribute 'guardar_casilla'` / `'listar_casillas'`); los existentes siguen en PASS.

- [ ] **Step 4: Write minimal implementation**

En `backend/agent/admin/contacto_repository.py`, reemplazar la función `resolver_destinatarios` completa por:

```python
def resolver_destinatarios(conn, organismo_id: int | None) -> list[str]:
    if organismo_id is not None:
        with conn.cursor() as cur:
            cur.execute("SELECT email_contacto FROM organismos WHERE id = %s", (organismo_id,))
            fila = cur.fetchone()
        if fila is not None and fila[0]:
            return [fila[0]]

        with conn.cursor() as cur:
            cur.execute(
                "SELECT email FROM admins WHERE organismo_id = %s AND activo = true",
                (organismo_id,),
            )
            emails = [row[0] for row in cur.fetchall()]
        if emails:
            return emails

    with conn.cursor() as cur:
        cur.execute("SELECT email FROM admins WHERE rol = 'super_admin' AND activo = true")
        return [row[0] for row in cur.fetchall()]
```

Y agregar al final del archivo:

```python
def listar_casillas(conn, organismo_id: int | None) -> list[dict]:
    with conn.cursor() as cur:
        if organismo_id is None:
            cur.execute("SELECT id, nombre, email_contacto FROM organismos ORDER BY nombre")
        else:
            cur.execute(
                "SELECT id, nombre, email_contacto FROM organismos WHERE id = %s", (organismo_id,)
            )
        return [
            {"id": id_, "nombre": nombre, "email_contacto": email}
            for id_, nombre, email in cur.fetchall()
        ]


def guardar_casilla(conn, organismo_id: int, email_contacto: str | None) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE organismos SET email_contacto = %s WHERE id = %s RETURNING id, nombre, email_contacto",
            (email_contacto, organismo_id),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"id": fila[0], "nombre": fila[1], "email_contacto": fila[2]}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_admin_contacto_repository.py tests/test_schema_smoke.py tests/test_contacto_api.py -v`
Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/db/schema.sql backend/tests/test_schema_smoke.py backend/agent/admin/contacto_repository.py backend/tests/test_admin_contacto_repository.py
git commit -m "feat: casilla de contacto por organismo en la base y en los destinatarios"
```

---

### Task 4: Endpoints de casillas y envío a la casilla

**Files:**
- Modify: `backend/agent/api.py`
- Test: `backend/tests/test_admin_contacto_api.py` (agregar)
- Test: `backend/tests/test_contacto_api.py` (agregar)

**Interfaces:**
- Consumes: `normalizar_email_contacto` (Task 2); `contacto_repository.listar_casillas`, `guardar_casilla`, `resolver_destinatarios` (Task 3).
- Produces: `GET /admin/contacto/casillas` y `PUT /admin/contacto/casillas/{organismo_id}` según las Global Constraints.

- [ ] **Step 1: Write the failing tests (API admin)**

Agregar al final de `backend/tests/test_admin_contacto_api.py`:

```python
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
```

Y en los imports de ese archivo: agregar `import pytest` justo antes de `from fastapi.testclient import TestClient` (el archivo queda con `import uuid`, una línea en blanco, `import pytest`, `from fastapi.testclient import TestClient`), y agregar `from agent.admin import contacto_repository` junto a los otros `from agent.admin import ...`.

- [ ] **Step 2: Write the failing tests (POST /contacto envía a la casilla)**

Agregar al final de `backend/tests/test_contacto_api.py` (agregar también `from agent.admin import contacto_repository` a sus imports):

```python
def _organismo_con_tramite(db_conn, casilla=None, admin_email=None):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    if casilla:
        contacto_repository.guardar_casilla(db_conn, organismo_id, casilla)
    if admin_email:
        with db_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO admins (email, password_hash, rol, organismo_id) VALUES (%s, 'hash', 'admin_organismo', %s)",
                (admin_email, organismo_id),
            )
    db_conn.commit()
    return organismo_id


def _post_contacto_y_destinatarios(db_conn):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail") as enviar_mail_mock:
            respuesta = client.post("/contacto", json=_payload(session_id, tramite_id="RC-0001"))
    finally:
        api.app.dependency_overrides.clear()
    assert respuesta.status_code == 200
    enviar_mail_mock.assert_called_once()
    return enviar_mail_mock.call_args.args[0]


def test_post_contacto_envia_el_aviso_solo_a_la_casilla_del_organismo(db_conn, clean_db):
    _organismo_con_tramite(db_conn, casilla="mesa@registro.gob.ar", admin_email="admin@registro.gob.ar")

    assert _post_contacto_y_destinatarios(db_conn) == ["mesa@registro.gob.ar"]


def test_post_contacto_sin_casilla_envia_a_los_admins_del_organismo(db_conn, clean_db):
    _organismo_con_tramite(db_conn, admin_email="admin@registro.gob.ar")

    assert _post_contacto_y_destinatarios(db_conn) == ["admin@registro.gob.ar"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run (desde `backend/`): `.venv/bin/pytest tests/test_admin_contacto_api.py tests/test_contacto_api.py -q 2>&1 | tail -8`
Expected: FAIL en los tests de casillas (404 porque la ruta no existe, o 422 porque `/admin/contacto/casillas` cae en `/{solicitud_id}`); `test_post_contacto_envia_el_aviso_solo_a_la_casilla_del_organismo` ya pasa porque Task 3 cambió el resolver, y el de "sin casilla" también. Anotar cuáles fallan.

- [ ] **Step 4: Write minimal implementation**

En `backend/agent/api.py`, agregar el import junto a los demás `from agent.admin import ...`:

```python
from agent.admin.email_contacto import normalizar_email_contacto
```

Y agregar este bloque **inmediatamente antes** de `@app.get("/admin/contacto/{solicitud_id}")` (después de `_verificar_solicitud_de_mi_organismo`):

```python
class CasillaPayload(BaseModel):
    email_contacto: str | None = None


@app.get("/admin/contacto/casillas")
def admin_listar_casillas(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = admin.organismo_id if admin.rol == "admin_organismo" else None
        return contacto_repository.listar_casillas(conn, organismo_id)


@app.put("/admin/contacto/casillas/{organismo_id}")
def admin_guardar_casilla(
    organismo_id: int,
    request: CasillaPayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    if admin.rol == "admin_organismo" and organismo_id != admin.organismo_id:
        raise HTTPException(status_code=404, detail="Organismo no encontrado")
    try:
        email = normalizar_email_contacto(request.email_contacto)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))

    with pool.connection() as conn:
        casilla = contacto_repository.guardar_casilla(conn, organismo_id, email)
        if casilla is None:
            raise HTTPException(status_code=404, detail="Organismo no encontrado")
        conn.commit()
    return casilla
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_admin_contacto_api.py tests/test_contacto_api.py -v 2>&1 | tail -6`
Expected: todos PASS. Luego la suite completa: `.venv/bin/pytest -q 2>&1 | tail -2` → sin fallos.

- [ ] **Step 6: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_contacto_api.py backend/tests/test_contacto_api.py
git commit -m "feat: endpoints para ver y guardar la casilla de contacto de cada organismo"
```

---

### Task 5: Validación y cliente de la casilla (frontend)

**Files:**
- Create: `frontend/lib/email-contacto.ts`
- Test: `frontend/lib/email-contacto.test.ts`
- Modify: `frontend/lib/admin-contacto-api.ts`

**Interfaces:**
- Consumes: `GET`/`PUT /admin/contacto/casillas…` (Task 4).
- Produces:
  - `MAX_LONGITUD_EMAIL = 254`.
  - `normalizarEmailContacto(valor: string): { ok: true; email: string | null } | { ok: false; mensaje: string }`: recorta; vacío o solo espacios → `{ok: true, email: null}`; inválido o de más de 254 caracteres → `{ok: false, mensaje: "Ingresá un email válido, por ejemplo mesa@organismo.gob.ar"}`.
  - `textoCasillaGuardada(email: string | null): string` → `"Casilla guardada."` si hay email, `"Se quitó la casilla."` si es `null`.
  - En `lib/admin-contacto-api.ts`: `type Casilla = { id: number; nombre: string; email_contacto: string | null }`, `listarCasillas(): Promise<Casilla[]>` y `guardarCasilla(organismoId: number, email: string | null): Promise<Casilla>` (lanza `Error` con el mensaje del servidor si falla).

- [ ] **Step 1: Write the failing tests**

Crear `frontend/lib/email-contacto.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  MAX_LONGITUD_EMAIL,
  normalizarEmailContacto,
  textoCasillaGuardada,
} from "./email-contacto";

describe("normalizarEmailContacto", () => {
  it("vacío o solo espacios devuelve null, no cadena vacía", () => {
    for (const valor of ["", "   ", "\n\t "]) {
      expect(normalizarEmailContacto(valor)).toEqual({ ok: true, email: null });
    }
  });

  it("recorta los espacios alrededor", () => {
    expect(normalizarEmailContacto("  mesa@salta.gob.ar \n")).toEqual({
      ok: true,
      email: "mesa@salta.gob.ar",
    });
  });

  it("acepta emails válidos", () => {
    for (const valor of ["mesa@salta.gob.ar", "a@b.co", "nombre.apellido+tag@dominio.com.ar"]) {
      expect(normalizarEmailContacto(valor)).toEqual({ ok: true, email: valor });
    }
  });

  it("rechaza emails con forma inválida", () => {
    for (const valor of ["sin-arroba", "a@b", "a b@c.com", "a@@b.com", "@x.com", "a@", "a@x .com"]) {
      const resultado = normalizarEmailContacto(valor);
      expect(resultado.ok).toBe(false);
    }
  });

  it("acepta exactamente el largo máximo y rechaza uno más", () => {
    const sufijo = "@x.co";
    const justo = "a".repeat(MAX_LONGITUD_EMAIL - sufijo.length) + sufijo;
    expect(normalizarEmailContacto(justo)).toEqual({ ok: true, email: justo });
    expect(normalizarEmailContacto("a" + justo).ok).toBe(false);
  });

  it("el mensaje de error está en español", () => {
    expect(normalizarEmailContacto("nope")).toEqual({
      ok: false,
      mensaje: "Ingresá un email válido, por ejemplo mesa@organismo.gob.ar",
    });
  });
});

describe("textoCasillaGuardada", () => {
  it("avisa que se guardó cuando hay email", () => {
    expect(textoCasillaGuardada("mesa@x.com")).toBe("Casilla guardada.");
  });

  it("avisa que se quitó cuando no hay email", () => {
    expect(textoCasillaGuardada(null)).toBe("Se quitó la casilla.");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (desde `frontend/`): `npx vitest run lib/email-contacto.test.ts 2>&1 | grep -E "Error|FAIL|Failed" | head -3`
Expected: FAIL (`Failed to load url ./email-contacto`).

- [ ] **Step 3: Write minimal implementation**

Crear `frontend/lib/email-contacto.ts`:

```ts
export const MAX_LONGITUD_EMAIL = 254;
const PATRON_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MENSAJE_INVALIDO = "Ingresá un email válido, por ejemplo mesa@organismo.gob.ar";

export type ResultadoEmail = { ok: true; email: string | null } | { ok: false; mensaje: string };

export function normalizarEmailContacto(valor: string): ResultadoEmail {
  const limpio = valor.trim();
  if (limpio === "") return { ok: true, email: null };
  if (limpio.length > MAX_LONGITUD_EMAIL || !PATRON_EMAIL.test(limpio)) {
    return { ok: false, mensaje: MENSAJE_INVALIDO };
  }
  return { ok: true, email: limpio };
}

export function textoCasillaGuardada(email: string | null): string {
  return email ? "Casilla guardada." : "Se quitó la casilla.";
}
```

Agregar al final de `frontend/lib/admin-contacto-api.ts`:

```ts

export type Casilla = {
  id: number;
  nombre: string;
  email_contacto: string | null;
};

export async function listarCasillas(): Promise<Casilla[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/casillas`, { credentials: "include" });
  if (!respuesta.ok) {
    throw new Error("No se pudieron cargar las casillas de contacto");
  }
  return respuesta.json();
}

export async function guardarCasilla(organismoId: number, email: string | null): Promise<Casilla> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/casillas/${organismoId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email_contacto: email }),
  });
  if (!respuesta.ok) {
    let mensaje = "No se pudo guardar la casilla";
    try {
      const cuerpo = await respuesta.json();
      if (typeof cuerpo.detail === "string") mensaje = cuerpo.detail;
    } catch {
      // el cuerpo no era JSON: se usa el mensaje genérico
    }
    throw new Error(mensaje);
  }
  return respuesta.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run 2>&1 | grep -E "Test Files|Tests " ; npx tsc --noEmit 2>&1 | head -3; echo "tsc: $?"`
Expected: todos los tests PASS y `tsc` sin errores.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/email-contacto.ts frontend/lib/email-contacto.test.ts frontend/lib/admin-contacto-api.ts
git commit -m "feat: validación y cliente de la casilla de contacto en el frontend"
```

---

### Task 6: Bloque "Casillas de mail de contacto" en la pantalla Contacto

El componente no tiene test unitario (vitest corre en entorno `node`, sin DOM): la lógica pura ya está cubierta en la Task 5 y el componente se verifica en el navegador.

**Files:**
- Create: `frontend/components/CasillasContacto.tsx`
- Modify: `frontend/app/admin/contacto/page.tsx`

**Interfaces:**
- Consumes: `listarCasillas`, `guardarCasilla`, `Casilla` (Task 5); `normalizarEmailContacto`, `textoCasillaGuardada` (Task 5).
- Produces: `<CasillasContacto />` sin props.

- [ ] **Step 1: Crear el componente**

Crear `frontend/components/CasillasContacto.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { guardarCasilla, listarCasillas, type Casilla } from "../lib/admin-contacto-api";
import { normalizarEmailContacto, textoCasillaGuardada } from "../lib/email-contacto";

type Aviso = { tipo: "ok" | "error"; texto: string };

export function CasillasContacto() {
  const [casillas, setCasillas] = useState<Casilla[] | null>(null);
  const [valores, setValores] = useState<Record<number, string>>({});
  const [avisos, setAvisos] = useState<Record<number, Aviso>>({});
  const [guardando, setGuardando] = useState<number | null>(null);
  const [errorCarga, setErrorCarga] = useState(false);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setErrorCarga(false);
    try {
      const lista = await listarCasillas();
      setCasillas(lista);
      setValores(Object.fromEntries(lista.map((c) => [c.id, c.email_contacto ?? ""])));
    } catch {
      setErrorCarga(true);
    }
  }

  async function handleGuardar(casilla: Casilla) {
    const resultado = normalizarEmailContacto(valores[casilla.id] ?? "");
    if (!resultado.ok) {
      setAvisos((a) => ({ ...a, [casilla.id]: { tipo: "error", texto: resultado.mensaje } }));
      return;
    }
    setGuardando(casilla.id);
    setAvisos((a) => {
      const { [casilla.id]: _quitado, ...resto } = a;
      return resto;
    });
    try {
      const guardada = await guardarCasilla(casilla.id, resultado.email);
      setValores((v) => ({ ...v, [casilla.id]: guardada.email_contacto ?? "" }));
      setAvisos((a) => ({
        ...a,
        [casilla.id]: { tipo: "ok", texto: textoCasillaGuardada(guardada.email_contacto) },
      }));
    } catch (err) {
      setAvisos((a) => ({
        ...a,
        [casilla.id]: {
          tipo: "error",
          texto: err instanceof Error ? err.message : "No se pudo guardar la casilla",
        },
      }));
    } finally {
      setGuardando(null);
    }
  }

  if (errorCarga) {
    return (
      <div className="tarjeta mb-6 max-w-2xl">
        <p className="text-sm texto-error">No se pudieron cargar las casillas de contacto</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  if (casillas === null || casillas.length === 0) {
    return null;
  }

  return (
    <section className="tarjeta mb-6 max-w-2xl">
      <h2 className="mb-1 font-semibold">Casillas de mail de contacto</h2>
      <p className="mb-3 text-xs texto-secundario">
        El aviso de cada solicitud se envía a la casilla del organismo. Si el organismo no tiene
        casilla, se envía a los emails de sus usuarios.
      </p>
      <ul className="space-y-3">
        {casillas.map((casilla) => (
          <li key={casilla.id}>
            <label className="campo-label" htmlFor={`casilla-${casilla.id}`}>
              {casilla.nombre}
            </label>
            <div className="flex gap-2">
              <input
                id={`casilla-${casilla.id}`}
                type="text"
                inputMode="email"
                value={valores[casilla.id] ?? ""}
                onChange={(e) => setValores((v) => ({ ...v, [casilla.id]: e.target.value }))}
                placeholder="mesa@organismo.gob.ar"
                className="campo-input flex-1"
              />
              <button
                type="button"
                onClick={() => handleGuardar(casilla)}
                disabled={guardando === casilla.id}
                className="boton-secundario"
              >
                {guardando === casilla.id ? "Guardando…" : "Guardar"}
              </button>
            </div>
            {avisos[casilla.id] && (
              <p
                className={`mt-1 text-sm ${
                  avisos[casilla.id].tipo === "ok" ? "text-green-700" : "texto-error"
                }`}
              >
                {avisos[casilla.id].texto}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

- [ ] **Step 2: Montarlo en la página**

En `frontend/app/admin/contacto/page.tsx`, agregar el import:

```tsx
import { CasillasContacto } from "../../../components/CasillasContacto";
```

y en el `return` final, justo debajo de `<h1 className="mb-4 text-lg font-semibold">Contacto</h1>` agregar:

```tsx
      <CasillasContacto />
```

- [ ] **Step 3: Typecheck y tests**

Run (desde `frontend/`): `npx tsc --noEmit 2>&1 | head -3; echo "tsc: $?"; npx vitest run 2>&1 | grep -E "Test Files|Tests "`
Expected: `tsc` sin errores y todos los tests PASS.

- [ ] **Step 4: Verificación visual (solo base de test)**

Cargar organismos y dos admins en la base de test:

```bash
cd backend && PYTHONPATH=. DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha_test .venv/bin/python - <<'EOF' 2>&1 | grep "ok"
import os, psycopg
from agent.admin import repository as r, security as s
from ingest import repository as repo
with psycopg.connect(os.environ["DATABASE_URL"]) as c:
    rc = repo.upsert_organismo(c, "Registro Civil"); repo.upsert_organismo(c, "Secretaría de Trabajo")
    r.crear_admin(c, "visual@macacha.local", s.hash_password("visual123"), "super_admin", None)
    r.crear_admin(c, "registro@example.com", s.hash_password("registro123"), "admin_organismo", rc)
    c.commit()
print("seed ok")
EOF
(DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha_test ADMIN_JWT_SECRET=visual-secret FRONTEND_ORIGIN=http://localhost:3001 nohup .venv/bin/uvicorn agent.api:app --port 8001 &> /tmp/backend8001.log &)
cd ../frontend && (NEXT_PUBLIC_API_URL=http://localhost:8001 nohup npx next dev -p 3001 &> /tmp/frontend3001.log &)
timeout 90 bash -c 'until curl -sf http://localhost:3001 >/dev/null; do sleep 1; done' && echo front-ok
```

Escribir `/tmp/casillas-visual.cjs`:

```js
const { createRequire } = require("module");
const req = createRequire(process.cwd() + "/package.json");
const puppeteer = req("puppeteer-core");
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({ executablePath: "/snap/bin/chromium", headless: "new", args: ["--no-sandbox"] });
  async function ingresar(email, pass, nombre) {
    const ctx = await b.createBrowserContext();
    const p = await ctx.newPage();
    await p.setViewport({ width: 1280, height: 800 });
    await p.goto("http://localhost:3001/admin/login", { waitUntil: "networkidle0" });
    await p.type("input[type=email]", email);
    await p.type("input[placeholder=Contraseña]", pass);
    await Promise.all([p.waitForNavigation({ waitUntil: "networkidle0" }), p.click("button[type=submit]")]);
    await p.goto("http://localhost:3001/admin/contacto", { waitUntil: "networkidle0" });
    await p.addStyleTag({ content: "nextjs-portal{display:none!important}" });
    await espera(600);
    return { p, ctx, nombre };
  }
  const texto = (p) => p.evaluate(() => document.body.innerText);
  // super admin
  let s = await ingresar("visual@macacha.local", "visual123", "super");
  const filas = await s.p.$$eval("section li", (l) => l.length);
  console.log("super admin: filas de casillas =", filas, "(esperado 2)");
  await s.p.type("#casilla-" + (await s.p.$eval("section li label", (l) => l.htmlFor.replace("casilla-", ""))), "no-es-un-email");
  await s.p.evaluate(() => [...document.querySelectorAll("section button")].find((x) => x.textContent === "Guardar").click());
  await espera(300);
  console.log("email inválido ->", (await texto(s.p)).includes("Ingresá un email válido") ? "muestra el error" : "NO muestra el error");
  const input = await s.p.$("section li input");
  await input.click({ clickCount: 3 });
  await input.type("mesa@registro.gob.ar");
  await s.p.evaluate(() => [...document.querySelectorAll("section button")].find((x) => x.textContent === "Guardar").click());
  await espera(700);
  console.log("email válido ->", (await texto(s.p)).includes("Casilla guardada.") ? "Casilla guardada." : "NO confirmó");
  await s.p.screenshot({ path: "/tmp/casillas-super.png", clip: { x: 240, y: 0, width: 1040, height: 520 } });
  await input.click({ clickCount: 3 });
  await input.press("Backspace");
  await s.p.evaluate(() => [...document.querySelectorAll("section button")].find((x) => x.textContent === "Guardar").click());
  await espera(700);
  console.log("vaciar ->", (await texto(s.p)).includes("Se quitó la casilla.") ? "Se quitó la casilla." : "NO confirmó");
  await s.ctx.close();
  // admin de organismo
  s = await ingresar("registro@example.com", "registro123", "organismo");
  console.log("admin de organismo: filas de casillas =", await s.p.$$eval("section li", (l) => l.length), "(esperado 1)");
  await s.p.screenshot({ path: "/tmp/casillas-organismo.png", clip: { x: 240, y: 0, width: 1040, height: 360 } });
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
```

Run: `cd frontend && node /tmp/casillas-visual.cjs`
Expected: `super admin: filas de casillas = 2`, el error con el email inválido, `Casilla guardada.`, `Se quitó la casilla.` y `admin de organismo: filas de casillas = 1`. Revisar `/tmp/casillas-super.png` y `/tmp/casillas-organismo.png` (sin textos superpuestos ni desbordes).

Limpiar y apagar al terminar:

```bash
docker exec -i macacha-postgres-1 psql -U macacha -d macacha_test -c "DELETE FROM admins; DELETE FROM organismos;"
for p in 8001 3001; do ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill; done
```

- [ ] **Step 5: Commit**

```bash
git add frontend/components/CasillasContacto.tsx frontend/app/admin/contacto/page.tsx
git commit -m "feat: bloque de casillas de mail de contacto en la pantalla Contacto"
```

---

### Task 7: Verificación final y nota de despliegue

**Files:**
- Modify: `docs/deploy-dokploy.md`

- [ ] **Step 1: Suites completas**

Run: `cd backend && .venv/bin/pytest -q 2>&1 | tail -1`
Expected: toda la suite PASS.

Run: `cd frontend && npx vitest run 2>&1 | grep -E "Tests " ; npx tsc --noEmit && echo "tsc ok"`
Expected: todos los tests PASS y `tsc ok`.

- [ ] **Step 2: Nota de despliegue**

En `docs/deploy-dokploy.md`, en el paso 6 ("Instrucción permanente — cada vez que `schema.sql` cambie"), a continuación del párrafo sobre `feedback_respuestas`, agregar:

```markdown

   La casilla de mail de contacto por organismo agrega la columna
   `organismos.email_contacto`. Mismo orden obligatorio: **primero** correr
   el comando, **después** desplegar el backend y por último el frontend. Si
   el backend sale antes que la columna, `POST /contacto` y
   `/admin/contacto/casillas` devuelven 500 (leen `email_contacto`). Las
   casillas arrancan vacías, así que hasta que alguien las cargue desde
   Contacto el aviso sigue yendo a los emails de los usuarios del organismo.
   Además, el servidor SMTP de producción usa el puerto 465 (SSL implícito):
   el backend lo soporta desde el arreglo de `enviar_mail`; con otro puerto se
   usa STARTTLS.
```

- [ ] **Step 3: Commit**

```bash
git add docs/deploy-dokploy.md
git commit -m "docs: orden de despliegue de la columna email_contacto"
```

- [ ] **Step 4: Revisión de estado**

Run: `git status --short && git log --oneline -8`
Expected: el árbol solo muestra los cambios previos ajenos a este plan (`frontend/package*.json`, `.claude/`); los commits del plan están presentes. No hacer push sin que el usuario lo pida. Aplicar el esquema en la base de producción (`ALTER TABLE …`) también requiere que el usuario lo pida.
