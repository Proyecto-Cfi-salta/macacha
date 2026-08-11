# Contacto humano desde el chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un formulario de contacto humano en el chat (nombre, email, teléfono, consulta) que se guarda, se manda por mail al admin del organismo del trámite elegido (o a los super_admin si no hay), y aparece en una sección nueva "Contacto" del panel admin junto con la conversación completa, con estado pendiente/resuelto.

**Architecture:** Una tool nueva (`ofrecer_contacto_humano`) que el LLM invoca con criterio marca el turno como `sugerir_contacto: true` en el evento SSE `"fin"` — mismo mecanismo que ya usan `fuentes`/`candidatos_ambiguos`. El frontend usa esa señal para resaltar un CTA, además de un botón fijo siempre visible. El envío del formulario pasa por un endpoint público nuevo (`POST /contacto`) que persiste la solicitud primero (fuente de verdad) y manda el mail después, en modo best-effort (un fallo de SMTP no rompe la respuesta ni pierde el dato). Los endpoints de administración (`/admin/contacto*`) siguen el mismo patrón de filtrado/404 cross-organismo ya usado para sesiones y trámites.

**Tech Stack:** FastAPI + psycopg3 + Postgres (backend), `smtplib` (stdlib, sin dependencia nueva), Next.js 15 + React 19 + TypeScript (frontend), pytest, vitest.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-11-contacto-humano-design.md` — toda tarea implementa una sección de ese documento.
- Estilo de nombres del proyecto: identificadores en español (`crear_solicitud`, `listar_solicitudes`, `resolver_destinatarios`), consistente con el código existente.
- Backend: cada función nueva en `agent/*`/`agent/admin/*` que toque la base recibe `conn` como primer parámetro (patrón ya usado en todo el proyecto).
- Frontend: `"use client"` en cualquier componente/página con estado o efectos. `credentials: "include"` en todo fetch a un endpoint de `/admin/*`; los endpoints públicos (`POST /contacto`) NO llevan `credentials: "include"`.
- Este repo no testea componentes React ni fetch wrappers de frontend (`lib/*-api.ts`) — solo funciones puras de transformación (ver `lib/admin-chats.ts`/`hooks/usePanelTramite.ts`). Las tareas de frontend solo agregan tests para la nueva función pura de selección de trámite.
- Todo cambio de schema va en `backend/db/schema.sql`, agregado al final, con el mismo estilo idempotente (`CREATE TABLE IF NOT EXISTS`) que ya usa el archivo.
- `smtplib` es de la librería estándar de Python — no se agrega ninguna dependencia nueva a `backend/requirements.txt`.

---

## Task 1: Schema — tabla `solicitudes_contacto`

**Files:**
- Modify: `backend/db/schema.sql`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_schema_smoke.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: tabla `solicitudes_contacto` (`id`, `session_id`, `tramite_id`, `organismo_id`, `nombre`, `email`, `telefono`, `consulta`, `estado`, `creado_en`). Usada por todas las tareas siguientes.

- [ ] **Step 1: Agregar la tabla al schema**

Al final de `backend/db/schema.sql`, agregar:

```sql
CREATE TABLE IF NOT EXISTS solicitudes_contacto (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sesiones(id),
    tramite_id TEXT REFERENCES tramites(id),
    organismo_id INTEGER REFERENCES organismos(id),
    nombre TEXT NOT NULL,
    email TEXT NOT NULL,
    telefono TEXT NOT NULL,
    consulta TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Reordenar la limpieza de tests para la nueva FK**

`solicitudes_contacto` referencia `sesiones`, `tramites` y `organismos`. En `backend/tests/conftest.py`, dentro de `_clean()`, agregar `cur.execute("DELETE FROM solicitudes_contacto")` **antes** de `sesiones`/`tramites`/`organismos` (después de `mensajes` está bien, ya que no depende de mensajes):

```python
def _clean() -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM mensajes")
        cur.execute("DELETE FROM solicitudes_contacto")
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

Expected: sin errores. Correrlo dos veces seguidas no debe dar error (idempotencia).

- [ ] **Step 4: Extender el smoke test de schema**

En `backend/tests/test_schema_smoke.py`, en `test_extension_and_tables_exist`, agregar `"solicitudes_contacto"` al set de tablas esperadas:

```python
        assert {
            "organismos",
            "tramites",
            "tramite_versiones",
            "tramite_chunks",
            "sesiones",
            "mensajes",
            "admins",
            "solicitudes_contacto",
        } <= tables
```

- [ ] **Step 5: Documentar las variables de entorno de SMTP**

En `.env.example`, agregar al final:

```
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=notificaciones@macacha.gob.ar
```

- [ ] **Step 6: Correr los tests de schema**

Run: `cd backend && .venv/bin/pytest tests/test_schema_smoke.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/db/schema.sql backend/tests/conftest.py backend/tests/test_schema_smoke.py .env.example
git commit -m "feat: agrega tabla solicitudes_contacto"
```

---

## Task 2: `agent/mail.py` — envío de correo por SMTP

**Files:**
- Create: `backend/agent/mail.py`
- Create: `backend/tests/test_mail.py`

**Interfaces:**
- Produces: `enviar_mail(destinatarios: list[str], asunto: str, cuerpo_texto: str) -> None`.

Usada por Task 6 (`POST /contacto`).

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_mail.py`:

```python
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from agent import mail


def test_enviar_mail_usa_configuracion_del_entorno(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "usuario@ejemplo.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreta")
    monkeypatch.setenv("SMTP_FROM", "notificaciones@macacha.gob.ar")

    smtp_instance = MagicMock()
    smtp_instance.__enter__.return_value = smtp_instance

    with patch("agent.mail.smtplib.SMTP", return_value=smtp_instance) as smtp_cls:
        mail.enviar_mail(
            ["admin@ejemplo.com", "otro@ejemplo.com"],
            asunto="Nueva consulta de Juan",
            cuerpo_texto="Hola, tengo una consulta.",
        )

    smtp_cls.assert_called_once_with("smtp.ejemplo.com", 587)
    smtp_instance.starttls.assert_called_once()
    smtp_instance.login.assert_called_once_with("usuario@ejemplo.com", "secreta")

    assert smtp_instance.send_message.call_count == 1
    mensaje_enviado: EmailMessage = smtp_instance.send_message.call_args[0][0]
    assert mensaje_enviado["Subject"] == "Nueva consulta de Juan"
    assert mensaje_enviado["From"] == "notificaciones@macacha.gob.ar"
    assert mensaje_enviado["To"] == "admin@ejemplo.com, otro@ejemplo.com"
    assert mensaje_enviado.get_content().strip() == "Hola, tengo una consulta."


def test_enviar_mail_sin_destinatarios_no_hace_nada(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "usuario@ejemplo.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secreta")
    monkeypatch.setenv("SMTP_FROM", "notificaciones@macacha.gob.ar")

    with patch("agent.mail.smtplib.SMTP") as smtp_cls:
        mail.enviar_mail([], asunto="Asunto", cuerpo_texto="Cuerpo")

    smtp_cls.assert_not_called()
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd backend && .venv/bin/pytest tests/test_mail.py -v`
Expected: FAIL (`agent.mail` no existe).

- [ ] **Step 3: Implementar `mail.py`**

Crear `backend/agent/mail.py`:

```python
import os
import smtplib
from email.message import EmailMessage


def enviar_mail(destinatarios: list[str], asunto: str, cuerpo_texto: str) -> None:
    if not destinatarios:
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = os.environ["SMTP_FROM"]
    mensaje["To"] = ", ".join(destinatarios)
    mensaje.set_content(cuerpo_texto)

    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(mensaje)
```

Nota: lee las variables de entorno con `os.environ[...]` dentro de la función (no a nivel de módulo), para que el proceso no falle al arrancar si SMTP todavía no está configurado — solo falla en el momento en que efectivamente se intenta mandar un mail. Esto es intencionalmente distinto de `ADMIN_JWT_SECRET`, que si falta rompe el arranque completo porque se usa en cada request de admin.

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd backend && .venv/bin/pytest tests/test_mail.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/mail.py backend/tests/test_mail.py
git commit -m "feat: agrega envio de mail por SMTP"
```

---

## Task 3: `agent/admin/contacto_repository.py` — CRUD de solicitudes de contacto

**Files:**
- Create: `backend/agent/admin/contacto_repository.py`
- Create: `backend/tests/test_admin_contacto_repository.py`

**Interfaces:**
- Consumes: tabla `solicitudes_contacto` (Task 1).
- Produces:
  - `crear_solicitud(conn, session_id: str, tramite_id: str | None, organismo_id: int | None, nombre: str, email: str, telefono: str, consulta: str) -> str` — devuelve el id (uuid como string) de la fila creada.
  - `resolver_destinatarios(conn, organismo_id: int | None) -> list[str]` — emails de `admins` activos de ese organismo; si esa lista queda vacía o `organismo_id` es `None`, emails de todos los `super_admin` activos.
  - `listar_solicitudes(conn, organismo_id: int | None) -> list[dict]` — cada dict: `id, nombre, email, telefono, consulta, estado, creado_en, tramite_id, tramite_nombre, organismo, session_id`. Si `organismo_id` no es `None`, filtra `WHERE organismo_id = %s`; si es `None`, sin filtro (todas).
  - `obtener_solicitud(conn, solicitud_id: str) -> dict | None` — mismo shape que un elemento de `listar_solicitudes`.
  - `actualizar_estado(conn, solicitud_id: str, estado: str) -> None`.

Usadas por Task 6 (`POST /contacto`) y Task 7 (`/admin/contacto*`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_contacto_repository.py`:

```python
import uuid

from agent import sessions
from agent.admin import contacto_repository
from ingest import repository as repo


def _crear_sesion(conn, session_id):
    sessions.crear_sesion_si_no_existe(conn, session_id)


def _crear_admin(conn, email, rol="admin_organismo", organismo_id=None, activo=True):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO admins (email, password_hash, rol, organismo_id, activo) VALUES (%s, 'hash', %s, %s, %s)",
            (email, rol, organismo_id, activo),
        )


def test_crear_solicitud_devuelve_id(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id)

    solicitud_id = contacto_repository.crear_solicitud(
        db_conn, session_id, None, None, "Juan Pérez", "juan@x.com", "3871234567", "Necesito ayuda"
    )
    db_conn.commit()

    assert solicitud_id
    solicitud = contacto_repository.obtener_solicitud(db_conn, solicitud_id)
    assert solicitud["nombre"] == "Juan Pérez"
    assert solicitud["estado"] == "pendiente"
    assert solicitud["tramite_id"] is None
    assert solicitud["organismo"] is None


def test_crear_solicitud_con_tramite_y_organismo(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id)
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    solicitud_id = contacto_repository.crear_solicitud(
        db_conn, session_id, "RC-0001", organismo_id, "Ana", "ana@x.com", "3870000000", "Consulta"
    )
    db_conn.commit()

    solicitud = contacto_repository.obtener_solicitud(db_conn, solicitud_id)
    assert solicitud["tramite_id"] == "RC-0001"
    assert solicitud["tramite_nombre"] == "Actas Regulares"
    assert solicitud["organismo"] == "Registro Civil"


def test_obtener_solicitud_inexistente_devuelve_none(db_conn, clean_db):
    assert contacto_repository.obtener_solicitud(db_conn, str(uuid.uuid4())) is None


def test_actualizar_estado(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id)
    solicitud_id = contacto_repository.crear_solicitud(
        db_conn, session_id, None, None, "Juan", "juan@x.com", "387", "Consulta"
    )
    db_conn.commit()

    contacto_repository.actualizar_estado(db_conn, solicitud_id, "resuelto")
    db_conn.commit()

    assert contacto_repository.obtener_solicitud(db_conn, solicitud_id)["estado"] == "resuelto"


def test_listar_solicitudes_filtra_por_organismo(db_conn, clean_db):
    session_id_a = str(uuid.uuid4())
    session_id_b = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id_a)
    _crear_sesion(db_conn, session_id_b)
    organismo_a = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_b = repo.upsert_organismo(db_conn, "Rentas")

    contacto_repository.crear_solicitud(
        db_conn, session_id_a, None, organismo_a, "A", "a@x.com", "1", "consulta a"
    )
    contacto_repository.crear_solicitud(
        db_conn, session_id_b, None, organismo_b, "B", "b@x.com", "2", "consulta b"
    )
    db_conn.commit()

    filtradas = contacto_repository.listar_solicitudes(db_conn, organismo_a)
    assert [s["nombre"] for s in filtradas] == ["A"]

    todas = contacto_repository.listar_solicitudes(db_conn, None)
    assert {s["nombre"] for s in todas} == {"A", "B"}


def test_resolver_destinatarios_organismo_con_admin_activo(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "org@x.com", rol="admin_organismo", organismo_id=organismo_id)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["org@x.com"]


def test_resolver_destinatarios_organismo_sin_admin_devuelve_super_admins(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["super@x.com"]


def test_resolver_destinatarios_sin_organismo_devuelve_super_admins(db_conn, clean_db):
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, None) == ["super@x.com"]


def test_resolver_destinatarios_ignora_admins_inactivos(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "org@x.com", rol="admin_organismo", organismo_id=organismo_id, activo=False)
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None, activo=True)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["super@x.com"]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_contacto_repository.py -v`
Expected: FAIL (`agent.admin.contacto_repository` no existe).

- [ ] **Step 3: Implementar `contacto_repository.py`**

Crear `backend/agent/admin/contacto_repository.py`:

```python
def crear_solicitud(
    conn,
    session_id: str,
    tramite_id: str | None,
    organismo_id: int | None,
    nombre: str,
    email: str,
    telefono: str,
    consulta: str,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO solicitudes_contacto
                (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta),
        )
        return str(cur.fetchone()[0])


def resolver_destinatarios(conn, organismo_id: int | None) -> list[str]:
    if organismo_id is not None:
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


_SELECT_SOLICITUD = """
    SELECT
        s.id, s.session_id, s.tramite_id, t.nombre_oficial, s.organismo_id, o.nombre,
        s.nombre, s.email, s.telefono, s.consulta, s.estado, s.creado_en
    FROM solicitudes_contacto s
    LEFT JOIN tramites t ON t.id = s.tramite_id
    LEFT JOIN organismos o ON o.id = s.organismo_id
"""


def _fila_a_dict(fila) -> dict:
    (
        id_, session_id, tramite_id, tramite_nombre, organismo_id, organismo,
        nombre, email, telefono, consulta, estado, creado_en,
    ) = fila
    return {
        "id": str(id_),
        "session_id": str(session_id),
        "tramite_id": tramite_id,
        "tramite_nombre": tramite_nombre,
        "organismo_id": organismo_id,
        "organismo": organismo,
        "nombre": nombre,
        "email": email,
        "telefono": telefono,
        "consulta": consulta,
        "estado": estado,
        "creado_en": creado_en.isoformat(),
    }


def listar_solicitudes(conn, organismo_id: int | None) -> list[dict]:
    query = _SELECT_SOLICITUD
    params: tuple = ()
    if organismo_id is not None:
        query += " WHERE s.organismo_id = %s"
        params = (organismo_id,)
    query += " ORDER BY s.creado_en DESC"

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [_fila_a_dict(fila) for fila in cur.fetchall()]


def obtener_solicitud(conn, solicitud_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(_SELECT_SOLICITUD + " WHERE s.id = %s", (solicitud_id,))
        fila = cur.fetchone()
        return _fila_a_dict(fila) if fila else None


def actualizar_estado(conn, solicitud_id: str, estado: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE solicitudes_contacto SET estado = %s WHERE id = %s", (estado, solicitud_id)
        )
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_contacto_repository.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/contacto_repository.py backend/tests/test_admin_contacto_repository.py
git commit -m "feat: repository de solicitudes de contacto"
```

---

## Task 4: `agent/tools.py` — tool `ofrecer_contacto_humano`

**Files:**
- Modify: `backend/agent/tools.py`
- Modify: `backend/tests/test_tools.py`

**Interfaces:**
- Produces: entrada `ofrecer_contacto_humano` en `TOOL_SCHEMAS`; función `ofrecer_contacto_humano() -> dict` devolviendo `{"sugerido": True}`; entrada correspondiente en `ejecutar_tool`.

Usada por Task 5 (`orchestrator.py`, que detecta esta tool entre los `tool_calls` del turno).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `backend/tests/test_tools.py`:

```python
def test_ofrecer_contacto_humano_devuelve_sugerido():
    assert tools.ofrecer_contacto_humano() == {"sugerido": True}


def test_ejecutar_tool_ofrecer_contacto_humano(db_conn, clean_db):
    resultado = tools.ejecutar_tool(
        "ofrecer_contacto_humano", {}, db_conn, _fake_embed_fn, _fake_rerank_fn
    )
    assert resultado == {"sugerido": True}


def test_ofrecer_contacto_humano_esta_en_tool_schemas():
    nombres = [t["function"]["name"] for t in tools.TOOL_SCHEMAS]
    assert "ofrecer_contacto_humano" in nombres
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_tools.py -v -k ofrecer_contacto`
Expected: FAIL (`ofrecer_contacto_humano` no existe en `tools`).

- [ ] **Step 3: Implementar**

En `backend/agent/tools.py`, agregar a `TOOL_SCHEMAS` (al final de la lista, antes del `]` de cierre):

```python
    {
        "type": "function",
        "function": {
            "name": "ofrecer_contacto_humano",
            "description": (
                "Usala cuando no puedas resolver la consulta de la persona — no "
                "encontrás el trámite, la información no alcanza, o la persona te "
                "dice explícitamente que la respuesta no le sirve o que necesita "
                "hablar con alguien. No la uses como primera opción: intentá "
                "resolver la consulta primero."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
```

Agregar la función (junto a las demás funciones `obtener_*`/`buscar_tramite`, antes de `ejecutar_tool`):

```python
def ofrecer_contacto_humano() -> dict:
    return {"sugerido": True}
```

En `ejecutar_tool`, agregar el caso (antes del `raise ValueError` final):

```python
    if nombre == "ofrecer_contacto_humano":
        return ofrecer_contacto_humano()
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_tools.py -v`
Expected: PASS (todos, existentes + 3 nuevos).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/tools.py backend/tests/test_tools.py
git commit -m "feat: agrega tool ofrecer_contacto_humano"
```

---

## Task 5: `agent/orchestrator.py` — señal `sugerir_contacto`

**Files:**
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `tools.ejecutar_tool` (Task 4, ya maneja `"ofrecer_contacto_humano"` sin lanzar `ValueError`).
- Produces: el evento `{"tipo": "fin", ...}` que `procesar_turno` ya emite gana una clave más: `"sugerir_contacto": bool`. `True` si en ese turno el LLM invocó `ofrecer_contacto_humano`, o si se agotaron `MAX_ITERACIONES_TOOLS`. `False` en cualquier otro caso.

**Breaking change de forma:** todo el código y los tests que hoy comparan el evento `"fin"` con un dict literal (`{"tipo": "fin", "fuentes": [...], "candidatos_ambiguos": [...]}`) necesitan la clave nueva agregada — se actualizan en este mismo task (Step 1), no quedan rotos para una task futura (a diferencia del caso de `listar_organismos` en el trabajo de roles, acá no hay ninguna razón para diferir el arreglo: todos los consumidores de este evento están en el mismo archivo de test).

- [ ] **Step 1: Actualizar los tests existentes y agregar los nuevos**

En `backend/tests/test_orchestrator.py`, actualizar **todos** los asserts que comparan `eventos[-1]` (o `eventos[-1]["fin"]`/claves sueltas) con un dict literal, agregando `"sugerir_contacto": False` en cada uno. Concretamente:

- `test_procesar_turno_sin_tool_calls`: `eventos[-1] == {"tipo": "fin", "fuentes": [], "candidatos_ambiguos": [], "sugerir_contacto": False}`.
- `test_procesar_turno_con_tool_call_arma_fuentes`: el dict de `eventos[-1]` gana `"sugerir_contacto": False`.
- `test_procesar_turno_busqueda_con_match_unico_cita_la_fuente`: ídem.
- `test_procesar_turno_resuelto_no_expone_candidatos_ambiguos`: no compara dict completo, sin cambios.
- `test_procesar_turno_busqueda_sin_resultados_no_cita_fuentes`: `eventos[-1] == {"tipo": "fin", "fuentes": [], "candidatos_ambiguos": [], "sugerir_contacto": False}`.
- El resto de los tests existentes (`..._preserva_orden_de_citacion`, `..._varios_candidatos_cita_el_mencionado...`, `..._candidatos_parafraseados...`, `..._busqueda_ambigua...`, `..._persiste_los_mensajes_visibles`, `..._persiste_el_proveedor...`) no comparan el dict completo (acceden a claves puntuales como `eventos[-1]["fuentes"]`) — no necesitan cambios.

Agregar al final del archivo:

```python
def test_procesar_turno_tool_ofrecer_contacto_humano_marca_sugerir_contacto(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "ofrecer_contacto_humano", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "¿Querés que te ayude una persona? Completá este formulario.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "no entiendo nada")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is True


def test_procesar_turno_agotar_iteraciones_marca_sugerir_contacto(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    respuesta_con_tool_call_infinita = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_x",
                "type": "function",
                "function": {"name": "buscar_tramite", "arguments": '{"query": "algo"}'},
            }
        ],
    }
    chat_client = _FakeChatClient([respuesta_con_tool_call_infinita] * 6)

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is True


def test_procesar_turno_normal_no_marca_sugerir_contacto(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": "Hola, en qué te ayudo?", "tool_calls": None}]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is False
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_orchestrator.py -v`
Expected: FAIL (los dicts no tienen `sugerir_contacto`, las 3 nuevas fallan con `KeyError`).

- [ ] **Step 3: Implementar la señal en `orchestrator.py`**

En `backend/agent/orchestrator.py`:

Agregar una línea al `SYSTEM_PROMPT` (al final, antes del cierre de la cadena), mencionando la nueva tool:

```python
    "Si en algún momento no podés resolver la consulta con la información "
    "disponible, o la persona te dice que la respuesta no le sirve o que "
    "necesita hablar con alguien, usá la herramienta ofrecer_contacto_humano "
    "y después invitala con calidez a completar el formulario de contacto "
    "que va a aparecer."
)
```

En `procesar_turno`, inicializar la bandera junto a `tramites_citados`/`candidatos_buscados`:

```python
    tramites_citados: list[str] = []
    candidatos_buscados: dict[str, str] = {}
    sugerir_contacto = False
```

Dentro del loop `for tool_call in tool_calls:` (donde ya se procesa cada tool call), agregar la detección:

```python
        for tool_call in tool_calls:
            nombre = tool_call["function"]["name"]
            argumentos = json.loads(tool_call["function"]["arguments"])
            resultado = ejecutar_tool(nombre, argumentos, conn, embed_fn, rerank_fn)

            if nombre == "ofrecer_contacto_humano":
                sugerir_contacto = True

            if "tramite_id" in argumentos and argumentos["tramite_id"] not in tramites_citados:
```

(la línea `if "tramite_id" in argumentos...` ya existe — solo se agrega el bloque `if nombre == "ofrecer_contacto_humano": sugerir_contacto = True` antes de ella, sin tocar el resto de ese bloque).

En el punto donde se emite el evento `"fin"` del flujo normal (cuando `not tool_calls`), agregar la clave:

```python
            yield {
                "tipo": "fin",
                "fuentes": _armar_fuentes(conn, tramites_citados),
                "candidatos_ambiguos": (
                    [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
                ),
                "sugerir_contacto": sugerir_contacto,
            }
```

En el punto donde se emite el evento `"fin"` tras agotar `MAX_ITERACIONES_TOOLS` (al final de la función), la clave siempre es `True`:

```python
    yield {
        "tipo": "fin",
        "fuentes": _armar_fuentes(conn, tramites_citados),
        "candidatos_ambiguos": (
            [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
        ),
        "sugerir_contacto": True,
    }
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_orchestrator.py -v`
Expected: PASS (todos, existentes actualizados + 3 nuevos).

- [ ] **Step 5: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (todo — confirma que `test_api.py` y demás, que solo chequean `eventos[-1]["tipo"] == "fin"` sin comparar el dict completo, siguen pasando).

- [ ] **Step 6: Commit**

```bash
git add backend/agent/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: agrega senial sugerir_contacto al evento fin del chat"
```

---

## Task 6: `agent/api.py` — `POST /contacto` (endpoint público)

**Files:**
- Modify: `backend/agent/api.py`
- Create: `backend/tests/test_contacto_api.py`

**Interfaces:**
- Consumes: `contacto_repository.crear_solicitud`/`resolver_destinatarios` (Task 3), `mail.enviar_mail` (Task 2), `sessions.obtener_mensajes_visibles` (ya existente), `admin_tramites_repository.obtener_organismo_id_de_tramite` (ya existente, del trabajo de roles).
- Produces: `POST /contacto` → `{"ok": True}`. Sin autenticación — accesible desde el chat público.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_contacto_api.py`:

```python
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent import api, sessions
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


def _payload(session_id, **overrides):
    payload = {
        "session_id": session_id,
        "tramite_id": None,
        "nombre": "Juan Pérez",
        "email": "juan@x.com",
        "telefono": "3871234567",
        "consulta": "Necesito ayuda con mi trámite",
    }
    payload.update(overrides)
    return payload


def test_post_contacto_crea_solicitud_sin_tramite(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail") as enviar_mail_mock:
            respuesta = client.post("/contacto", json=_payload(session_id))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    enviar_mail_mock.assert_called_once()


def test_post_contacto_resuelve_organismo_desde_tramite(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail"):
            respuesta = client.post("/contacto", json=_payload(session_id, tramite_id="RC-0001"))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    with db_conn.cursor() as cur:
        cur.execute("SELECT organismo_id FROM solicitudes_contacto WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] == organismo_id


def test_post_contacto_persiste_aunque_el_mail_falle(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        with patch("agent.api.mail.enviar_mail", side_effect=RuntimeError("SMTP caído")):
            respuesta = client.post("/contacto", json=_payload(session_id))
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM solicitudes_contacto WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] == 1


def test_post_contacto_campo_faltante_devuelve_422(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        payload = _payload(session_id)
        del payload["nombre"]
        respuesta = client.post("/contacto", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_contacto_api.py -v`
Expected: FAIL (`POST /contacto` no existe → 404).

- [ ] **Step 3: Implementar el endpoint**

En `backend/agent/api.py`, agregar el import al principio del archivo (junto a los demás imports de `agent`):

```python
from agent import mail
from agent.admin import contacto_repository
```

Agregar el modelo y el endpoint, después de `top_tramites` (línea ~139, antes de la sección `/admin/*`):

```python
class ContactoPayload(BaseModel):
    session_id: uuid.UUID
    tramite_id: str | None = None
    nombre: str = Field(min_length=1)
    email: str = Field(min_length=1)
    telefono: str = Field(min_length=1)
    consulta: str = Field(min_length=1)


def _armar_cuerpo_mail(request: ContactoPayload, mensajes: list[dict]) -> str:
    lineas = [
        f"Nombre: {request.nombre}",
        f"Email: {request.email}",
        f"Teléfono: {request.telefono}",
        "",
        "Consulta:",
        request.consulta,
        "",
        "--- Conversación completa ---",
    ]
    for mensaje in mensajes:
        etiqueta = "Persona" if mensaje["rol"] == "user" else "Macacha"
        lineas.append(f"{etiqueta}: {mensaje['contenido']}")
    return "\n".join(lineas)


@app.post("/contacto")
def crear_solicitud_contacto(request: ContactoPayload, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = (
            admin_tramites_repository.obtener_organismo_id_de_tramite(conn, request.tramite_id)
            if request.tramite_id
            else None
        )
        contacto_repository.crear_solicitud(
            conn,
            str(request.session_id),
            request.tramite_id,
            organismo_id,
            request.nombre,
            request.email,
            request.telefono,
            request.consulta,
        )
        conn.commit()

        destinatarios = contacto_repository.resolver_destinatarios(conn, organismo_id)
        mensajes = sessions.obtener_mensajes_visibles(conn, str(request.session_id))

    try:
        mail.enviar_mail(
            destinatarios,
            asunto=f"Nueva consulta de {request.nombre}",
            cuerpo_texto=_armar_cuerpo_mail(request, mensajes),
        )
    except Exception:
        pass  # best-effort: la solicitud ya está guardada y visible en /admin/contacto

    return {"ok": True}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_contacto_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (todo).

- [ ] **Step 6: Commit**

```bash
git add backend/agent/api.py backend/tests/test_contacto_api.py
git commit -m "feat: endpoint publico POST /contacto"
```

---

## Task 7: `agent/api.py` — `/admin/contacto*` (endpoints de administración)

**Files:**
- Modify: `backend/agent/api.py`
- Create: `backend/tests/test_admin_contacto_api.py`

**Interfaces:**
- Consumes: `contacto_repository.listar_solicitudes`/`obtener_solicitud`/`actualizar_estado` (Task 3), `AdminActual`/`requiere_admin` (ya existentes).
- Produces: `GET /admin/contacto`, `GET /admin/contacto/{id}`, `PUT /admin/contacto/{id}` — mismo patrón de filtrado/404 cross-organismo ya usado para sesiones y trámites. Ambos roles pueden usarlos (no requiere `requiere_super_admin`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_contacto_api.py`:

```python
import uuid

from fastapi.testclient import TestClient

from agent import api, sessions
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


def _crear_solicitud(conn, organismo_id=None, tramite_id=None, nombre="Juan"):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO solicitudes_contacto (session_id, tramite_id, organismo_id, nombre, email, telefono, consulta)
            VALUES (%s, %s, %s, %s, 'x@x.com', '387', 'consulta')
            RETURNING id
            """,
            (session_id, tramite_id, organismo_id, nombre),
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

    assert [s["nombre"] for s in respuesta.json()] == ["Propia"]


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

    assert {s["nombre"] for s in respuesta.json()} == {"Con organismo", "Sin organismo"}


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
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_contacto_api.py -v`
Expected: FAIL (los endpoints no existen → 404, y el helper `_crear_admin_y_loguear` está definido inline en este archivo nuevo así que eso no falla — solo las llamadas a rutas inexistentes).

- [ ] **Step 3: Implementar los endpoints**

En `backend/agent/api.py`, agregar al final del archivo:

```python
class ContactoEstadoPayload(BaseModel):
    estado: Literal["pendiente", "resuelto"]


@app.get("/admin/contacto")
def admin_listar_contacto(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = admin.organismo_id if admin.rol == "admin_organismo" else None
        return contacto_repository.listar_solicitudes(conn, organismo_id)


def _verificar_solicitud_de_mi_organismo(conn, admin: AdminActual, solicitud: dict | None) -> None:
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if admin.rol == "admin_organismo" and solicitud["organismo_id"] != admin.organismo_id:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")


@app.get("/admin/contacto/{solicitud_id}")
def admin_obtener_contacto(
    solicitud_id: uuid.UUID, admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
        solicitud = contacto_repository.obtener_solicitud(conn, str(solicitud_id))
        _verificar_solicitud_de_mi_organismo(conn, admin, solicitud)
        mensajes = admin_chats_repository.obtener_mensajes_completos(conn, solicitud["session_id"])
    return {**solicitud, "mensajes": mensajes}


@app.put("/admin/contacto/{solicitud_id}")
def admin_editar_estado_contacto(
    solicitud_id: uuid.UUID,
    request: ContactoEstadoPayload,
    admin: AdminActual = Depends(requiere_admin),
    pool=Depends(obtener_pool),
):
    with pool.connection() as conn:
        solicitud = contacto_repository.obtener_solicitud(conn, str(solicitud_id))
        _verificar_solicitud_de_mi_organismo(conn, admin, solicitud)
        contacto_repository.actualizar_estado(conn, str(solicitud_id), request.estado)
        conn.commit()
    return {"ok": True}
```

Nota: `admin_obtener_contacto` devuelve la solicitud junto con `mensajes` (la conversación completa) en un solo response — el frontend (Task 18) no necesita dos requests separados para el detalle.

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_admin_contacto_api.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS (todo).

- [ ] **Step 6: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_contacto_api.py
git commit -m "feat: endpoints admin de solicitudes de contacto"
```

---

## Task 8: Backend completo — verificación final

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Correr toda la suite de backend**

Run: `cd backend && .venv/bin/pytest -q`
Expected: PASS, todos los tests (existentes + nuevos de las Tasks 1-7).

- [ ] **Step 2: Si algo falla, arreglarlo antes de seguir a frontend**

No avanzar a la Task 9 con la suite de backend en rojo.

---

## Task 9: Frontend — señal `sugerirContacto` en `useChatStream`

**Files:**
- Modify: `frontend/hooks/useChatStream.ts`
- Modify: `frontend/hooks/useChatStream.test.ts`

**Interfaces:**
- Consumes: el evento SSE `"fin"` (backend, Task 5) ahora trae `sugerir_contacto: boolean`.
- Produces: `Mensaje` gana `sugerirContacto?: boolean`; `EventoSSE`'s variante `"fin"` gana `sugerir_contacto: boolean`.

Usada por Task 12 (`ChatMessage`).

- [ ] **Step 1: Actualizar los tests existentes y agregar uno nuevo**

En `frontend/hooks/useChatStream.test.ts`, los dos tests que arman un evento `"fin"` con JSON literal necesitan la clave nueva en el JSON de entrada y en el objeto esperado:

```typescript
  it("parsea un evento de fin con fuentes y candidatos ambiguos vacíos", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[{"tramite_id":"RC-0001","nombre_oficial":"Actas Regulares","fuente_url":"https://x"}],"candidatos_ambiguos":[],"sugerir_contacto":false}';

    expect(parsearLineasSSE(bloque)).toEqual([
      {
        tipo: "fin",
        fuentes: [
          {
            tramite_id: "RC-0001",
            nombre_oficial: "Actas Regulares",
            fuente_url: "https://x",
          },
        ],
        candidatos_ambiguos: [],
        sugerir_contacto: false,
      },
    ]);
  });

  it("parsea un evento de fin con candidatos ambiguos", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[],"candidatos_ambiguos":[{"tramite_id":"TR-0002","nombre_oficial":"Denuncia laboral","descripcion":"Reclamos laborales."}],"sugerir_contacto":false}';

    expect(parsearLineasSSE(bloque)).toEqual([
      {
        tipo: "fin",
        fuentes: [],
        candidatos_ambiguos: [
          {
            tramite_id: "TR-0002",
            nombre_oficial: "Denuncia laboral",
            descripcion: "Reclamos laborales.",
          },
        ],
        sugerir_contacto: false,
      },
    ]);
  });
```

Agregar un test nuevo, después de esos dos:

```typescript
  it("parsea un evento de fin que sugiere contacto humano", () => {
    const bloque =
      'data: {"tipo":"fin","fuentes":[],"candidatos_ambiguos":[],"sugerir_contacto":true}';

    expect(parsearLineasSSE(bloque)).toEqual([
      { tipo: "fin", fuentes: [], candidatos_ambiguos: [], sugerir_contacto: true },
    ]);
  });
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd frontend && npm test -- useChatStream`
Expected: `parsearLineasSSE` hace un parseo JSON genérico sin validar el shape en runtime, así que los 3 tests (2 actualizados + 1 nuevo) probablemente ya pasen a nivel de valores — lo que SÍ debe fallar es la compilación de TypeScript, porque el tipo `EventoSSE` todavía no declara `sugerir_contacto` en su variante `"fin"`. Confirmar el fallo de tipos con `cd frontend && npx tsc --noEmit` (debe reportar error en este archivo) antes de tocar el tipo — ese es el "RED" real de este step, no necesariamente el test runner.

- [ ] **Step 3: Implementar**

En `frontend/hooks/useChatStream.ts`:

```typescript
export type Mensaje = {
  rol: "user" | "assistant";
  contenido: string;
  fuentes?: Fuente[];
  candidatosAmbiguos?: CandidatoAmbiguo[];
  sugerirContacto?: boolean;
  error?: boolean;
};

export type EventoSSE =
  | { tipo: "texto"; delta: string }
  | {
      tipo: "fin";
      fuentes: Fuente[];
      candidatos_ambiguos: CandidatoAmbiguo[];
      sugerir_contacto: boolean;
    }
  | { tipo: "error"; mensaje: string };
```

En `aplicarEvento`, dentro de la rama `evento.tipo === "fin"`:

```typescript
      } else if (evento.tipo === "fin") {
        copia[copia.length - 1] = {
          ...ultimo,
          fuentes: evento.fuentes,
          candidatosAmbiguos: evento.candidatos_ambiguos,
          sugerirContacto: evento.sugerir_contacto,
        };
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd frontend && npm test -- useChatStream`
Expected: PASS (todos, existentes actualizados + 1 nuevo).

- [ ] **Step 5: Verificar tsc**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 6: Commit**

```bash
git add frontend/hooks/useChatStream.ts frontend/hooks/useChatStream.test.ts
git commit -m "feat: propaga sugerir_contacto en useChatStream"
```

---

## Task 10: Frontend — selección de trámite para el formulario de contacto

**Files:**
- Create: `frontend/lib/contacto-tramites.ts`
- Create: `frontend/lib/contacto-tramites.test.ts`

**Interfaces:**
- Consumes: `Mensaje`/`Fuente` (`hooks/useChatStream.ts`, ya existentes).
- Produces: `tramitesCitadosEnConversacion(mensajes: Mensaje[]) -> { tramite_id: string; nombre_oficial: string }[]` — la unión deduplicada de todos los trámites citados en `fuentes` a lo largo de toda la conversación, en orden de primera aparición.

Usada por Task 11 (`ContactoHumanoModal`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `frontend/lib/contacto-tramites.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { tramitesCitadosEnConversacion } from "./contacto-tramites";
import type { Mensaje } from "../hooks/useChatStream";

describe("tramitesCitadosEnConversacion", () => {
  it("devuelve lista vacía si ningún mensaje citó trámites", () => {
    const mensajes: Mensaje[] = [{ rol: "assistant", contenido: "Hola" }];
    expect(tramitesCitadosEnConversacion(mensajes)).toEqual([]);
  });

  it("devuelve un único trámite citado", () => {
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "qué necesito para un acta" },
      {
        rol: "assistant",
        contenido: "Necesitás tu DNI.",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
    ];
    expect(tramitesCitadosEnConversacion(mensajes)).toEqual([
      { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares" },
    ]);
  });

  it("deduplica trámites citados en más de un mensaje, en orden de primera aparición", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "primero",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Acta A", fuente_url: null }],
      },
      {
        rol: "assistant",
        contenido: "segundo",
        fuentes: [
          { tramite_id: "RC-0002", nombre_oficial: "Acta B", fuente_url: null },
          { tramite_id: "RC-0001", nombre_oficial: "Acta A", fuente_url: null },
        ],
      },
    ];
    expect(tramitesCitadosEnConversacion(mensajes)).toEqual([
      { tramite_id: "RC-0001", nombre_oficial: "Acta A" },
      { tramite_id: "RC-0002", nombre_oficial: "Acta B" },
    ]);
  });
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd frontend && npm test -- contacto-tramites`
Expected: FAIL (`lib/contacto-tramites.ts` no existe).

- [ ] **Step 3: Implementar**

Crear `frontend/lib/contacto-tramites.ts`:

```typescript
import type { Mensaje } from "../hooks/useChatStream";

export type TramiteCitado = { tramite_id: string; nombre_oficial: string };

export function tramitesCitadosEnConversacion(mensajes: Mensaje[]): TramiteCitado[] {
  const vistos = new Map<string, string>();
  for (const mensaje of mensajes) {
    for (const fuente of mensaje.fuentes ?? []) {
      if (!vistos.has(fuente.tramite_id)) {
        vistos.set(fuente.tramite_id, fuente.nombre_oficial);
      }
    }
  }
  return [...vistos.entries()].map(([tramite_id, nombre_oficial]) => ({
    tramite_id,
    nombre_oficial,
  }));
}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd frontend && npm test -- contacto-tramites`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/contacto-tramites.ts frontend/lib/contacto-tramites.test.ts
git commit -m "feat: funcion pura de tramites citados para el formulario de contacto"
```

---

## Task 11: Frontend — `lib/contacto-api.ts`

**Files:**
- Create: `frontend/lib/contacto-api.ts`

**Interfaces:**
- Consumes: `POST /contacto` (backend, Task 6).
- Produces: `enviarSolicitudContacto(datos: SolicitudContactoInput): Promise<void>`.

Usada por Task 12 (`ContactoHumanoModal`).

- [ ] **Step 1: Crear el archivo**

Crear `frontend/lib/contacto-api.ts`:

```typescript
export type SolicitudContactoInput = {
  session_id: string;
  tramite_id: string | null;
  nombre: string;
  email: string;
  telefono: string;
  consulta: string;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function enviarSolicitudContacto(datos: SolicitudContactoInput): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/contacto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo enviar la consulta");
  }
}
```

Nota: sin `credentials: "include"` — es un endpoint público, no requiere sesión de admin (a diferencia de todos los `lib/admin-*-api.ts`).

- [ ] **Step 2: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/contacto-api.ts
git commit -m "feat: cliente API publico de contacto"
```

---

## Task 12: Frontend — `ContactoHumanoModal` y wiring en el chat

**Files:**
- Create: `frontend/components/ContactoHumanoModal.tsx`
- Modify: `frontend/components/ChatMessage.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `tramitesCitadosEnConversacion` (Task 10), `enviarSolicitudContacto` (Task 11), `Mensaje.sugerirContacto` (Task 9).
- Produces: botón fijo en el header del chat que abre el modal; CTA inline en mensajes con `sugerirContacto: true` que también lo abre; el modal envía la solicitud y se cierra con confirmación.

- [ ] **Step 1: Crear `ContactoHumanoModal`**

Crear `frontend/components/ContactoHumanoModal.tsx`:

```tsx
"use client";

import { useState } from "react";
import { enviarSolicitudContacto } from "../lib/contacto-api";
import { tramitesCitadosEnConversacion } from "../lib/contacto-tramites";
import type { Mensaje } from "../hooks/useChatStream";

export function ContactoHumanoModal({
  sessionId,
  mensajes,
  onCerrar,
}: {
  sessionId: string;
  mensajes: Mensaje[];
  onCerrar: () => void;
}) {
  const tramites = tramitesCitadosEnConversacion(mensajes);
  const [tramiteId, setTramiteId] = useState<string | null>(
    tramites.length === 1 ? tramites[0].tramite_id : null
  );
  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [telefono, setTelefono] = useState("");
  const [consulta, setConsulta] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviado, setEnviado] = useState(false);

  const puedeEnviar =
    nombre.trim() !== "" &&
    email.trim() !== "" &&
    telefono.trim() !== "" &&
    consulta.trim() !== "";

  async function handleSubmit(evento: React.FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await enviarSolicitudContacto({
        session_id: sessionId,
        tramite_id: tramiteId,
        nombre,
        email,
        telefono,
        consulta,
      });
      setEnviado(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo enviar la consulta");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6">
        {enviado ? (
          <div>
            <p className="text-sm text-gray-800">
              Recibimos tu consulta. Alguien del área correspondiente se va a poner en
              contacto con vos.
            </p>
            <button
              onClick={onCerrar}
              className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white"
            >
              Cerrar
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <h2 className="text-lg font-semibold">Hablar con una persona</h2>

            {tramites.length > 1 && (
              <div>
                <label className="mb-1 block text-sm font-medium">¿Sobre qué trámite?</label>
                <select
                  value={tramiteId ?? ""}
                  onChange={(e) => setTramiteId(e.target.value || null)}
                  className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                >
                  <option value="">Elegir…</option>
                  {tramites.map((t) => (
                    <option key={t.tramite_id} value={t.tramite_id}>
                      {t.nombre_oficial}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {tramites.length === 1 && (
              <p className="text-sm text-gray-600">Trámite: {tramites[0].nombre_oficial}</p>
            )}
            {tramites.length === 0 && (
              <p className="text-sm text-gray-500">
                No identificamos un trámite en esta conversación — tu consulta la recibe el
                equipo general.
              </p>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium">Nombre</label>
              <input
                type="text"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Teléfono / WhatsApp</label>
              <input
                type="text"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Tu consulta</label>
              <textarea
                value={consulta}
                onChange={(e) => setConsulta(e.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
                rows={3}
              />
            </div>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!puedeEnviar || enviando}
                className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                {enviando ? "Enviando…" : "Enviar"}
              </button>
              <button
                type="button"
                onClick={onCerrar}
                className="rounded px-4 py-2 text-sm text-gray-500"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Agregar el CTA inline en `ChatMessage`**

En `frontend/components/ChatMessage.tsx`, agregar una prop `onPedirContacto` y renderizar el link cuando `mensaje.sugerirContacto` es verdadero:

```tsx
import type { Mensaje } from "../hooks/useChatStream";
import { BurbujaMensaje } from "./BurbujaMensaje";

export function ChatMessage({
  mensaje,
  onReintentar,
  onPedirContacto,
}: {
  mensaje: Mensaje;
  onReintentar?: () => void;
  onPedirContacto?: () => void;
}) {
  const esUsuario = mensaje.rol === "user";

  return (
    <BurbujaMensaje esUsuario={esUsuario} className={mensaje.error ? "border border-red-500" : ""}>
      <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
      {mensaje.fuentes && mensaje.fuentes.length > 0 && (
        <ul className="mt-2 border-t border-gray-300 pt-2 text-sm">
          {mensaje.fuentes.map((fuente) => (
            <li key={fuente.tramite_id}>
              {fuente.fuente_url ? (
                <a
                  href={fuente.fuente_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-700 underline"
                >
                  {fuente.nombre_oficial}
                </a>
              ) : (
                fuente.nombre_oficial
              )}
            </li>
          ))}
        </ul>
      )}
      {mensaje.sugerirContacto && onPedirContacto && (
        <button
          onClick={onPedirContacto}
          className="mt-2 block text-sm text-blue-700 underline"
        >
          ¿Querés que te ayude una persona? Completá este formulario
        </button>
      )}
      {mensaje.error && onReintentar && (
        <button
          onClick={onReintentar}
          className="mt-2 text-sm text-red-700 underline"
        >
          Reintentar
        </button>
      )}
    </BurbujaMensaje>
  );
}
```

- [ ] **Step 3: Agregar el botón fijo y el wiring del modal en `app/page.tsx`**

En `frontend/app/page.tsx`, dentro del componente `Chat` (que ya recibe `sessionId` y usa `useChatStream`):

1. Importar `ContactoHumanoModal`.
2. Agregar estado `const [modalContactoAbierto, setModalContactoAbierto] = useState(false);`.
3. En el `<header>` existente (el que tiene el `<h1>Macacha</h1>`), agregar un botón:

```tsx
        <header className="border-b border-gray-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold">Macacha</h1>
              <p className="text-sm text-gray-500">
                Asistente de trámites — Provincia de Salta
              </p>
            </div>
            <button
              onClick={() => setModalContactoAbierto(true)}
              className="text-sm text-blue-700 underline"
            >
              ¿Necesitás hablar con una persona?
            </button>
          </div>
        </header>
```

4. Pasar `onPedirContacto={() => setModalContactoAbierto(true)}` a cada `<ChatMessage>` del `.map`.
5. Al final del JSX del componente `Chat` (como hermano del `<div className="mx-auto flex h-screen ...">` raíz, o dentro de él — como overlay `fixed`, la posición en el árbol no importa visualmente), renderizar el modal condicionalmente:

```tsx
      {modalContactoAbierto && (
        <ContactoHumanoModal
          sessionId={sessionId}
          mensajes={mensajes}
          onCerrar={() => setModalContactoAbierto(false)}
        />
      )}
```

- [ ] **Step 4: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 5: Correr los tests de frontend**

Run: `cd frontend && npm test`
Expected: PASS (todos — este task no agrega tests nuevos, es UI de componentes que este repo no testea).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ContactoHumanoModal.tsx frontend/components/ChatMessage.tsx frontend/app/page.tsx
git commit -m "feat: formulario de contacto humano en el chat"
```

---

## Task 13: Frontend — extracción de `ConversacionChat`

**Files:**
- Create: `frontend/components/ConversacionChat.tsx`
- Modify: `frontend/app/admin/chats/[id]/page.tsx`

**Interfaces:**
- Consumes: `MensajeAdmin` (`lib/admin-api.ts`, ya existente), `extraerDetalleToolCalls` (`lib/admin-chats.ts`, ya existente), `BurbujaMensaje` (ya existente).
- Produces: `<ConversacionChat mensajes={MensajeAdmin[]} />` — renderiza exactamente lo que hoy renderiza `SesionDetallePage` para la lista de mensajes (burbujas + detalle técnico), reutilizable.

Usada por Task 18 (detalle de una solicitud de contacto).

- [ ] **Step 1: Crear el componente**

Crear `frontend/components/ConversacionChat.tsx`, moviendo el bloque de renderizado de mensajes y el componente `DetalleTecnico` desde `app/admin/chats/[id]/page.tsx` tal cual, sin cambios de comportamiento:

```tsx
"use client";

import { useState } from "react";
import type { MensajeAdmin } from "../lib/admin-api";
import { extraerDetalleToolCalls } from "../lib/admin-chats";
import { BurbujaMensaje } from "./BurbujaMensaje";

export function ConversacionChat({ mensajes }: { mensajes: MensajeAdmin[] }) {
  const visibles = mensajes.filter((m) => m.rol === "user" || m.rol === "assistant");

  return (
    <div className="mx-auto max-w-2xl space-y-3">
      {visibles.map((mensaje, indice) => (
        <BurbujaMensaje key={indice} esUsuario={mensaje.rol === "user"}>
          <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
          {mensaje.rol === "assistant" && mensaje.proveedor && (
            <span className="mt-1 inline-block rounded bg-gray-200 px-1.5 py-0.5 text-xs text-gray-600">
              {mensaje.proveedor === "gemini" ? "Gemini" : "OpenAI"}
            </span>
          )}
          {mensaje.rol === "assistant" && mensaje.tool_calls && mensaje.tool_calls.length > 0 && (
            <DetalleTecnico mensaje={mensaje} todosLosMensajes={mensajes} />
          )}
        </BurbujaMensaje>
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

Nota: el bloque original tenía `className="mx-auto max-w-2xl space-y-3 p-4"` en el div raíz de `SesionDetallePage`; acá se quita el `p-4` del componente (queda `"mx-auto max-w-2xl space-y-3"`) para que el padding lo controle quien lo use — `SesionDetallePage` lo agrega en su propio wrapper (Step 2).

- [ ] **Step 2: Refactorizar `SesionDetallePage` para usar el componente nuevo**

Reemplazar `frontend/app/admin/chats/[id]/page.tsx` completo:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { obtenerSesion, type MensajeAdmin } from "../../../../lib/admin-api";
import { ConversacionChat } from "../../../../components/ConversacionChat";

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

  return (
    <div className="p-4">
      <ConversacionChat mensajes={mensajes} />
    </div>
  );
}
```

- [ ] **Step 3: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 4: Correr los tests de frontend**

Run: `cd frontend && npm test`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ConversacionChat.tsx frontend/app/admin/chats/\[id\]/page.tsx
git commit -m "refactor: extrae ConversacionChat para reusarla en contacto"
```

---

## Task 14: Frontend — `lib/admin-contacto-api.ts`

**Files:**
- Create: `frontend/lib/admin-contacto-api.ts`

**Interfaces:**
- Consumes: `GET/PUT /admin/contacto*` (backend, Task 7), `MensajeAdmin` (`lib/admin-api.ts`, ya existente).
- Produces: `SolicitudContacto`, `SolicitudContactoDetalle` (tipos); `listarSolicitudesContacto()`, `obtenerSolicitudContacto(id)`, `editarEstadoContacto(id, estado)`.

Usada por Task 17 (lista) y Task 18 (detalle).

- [ ] **Step 1: Crear el archivo**

Crear `frontend/lib/admin-contacto-api.ts`:

```typescript
import type { MensajeAdmin } from "./admin-api";

export type SolicitudContacto = {
  id: string;
  session_id: string;
  tramite_id: string | null;
  tramite_nombre: string | null;
  organismo_id: number | null;
  organismo: string | null;
  nombre: string;
  email: string;
  telefono: string;
  consulta: string;
  estado: "pendiente" | "resuelto";
  creado_en: string;
};

export type SolicitudContactoDetalle = SolicitudContacto & {
  mensajes: MensajeAdmin[];
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listarSolicitudesContacto(): Promise<SolicitudContacto[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto`, { credentials: "include" });
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la lista de contacto");
  }
  return respuesta.json();
}

export async function obtenerSolicitudContacto(
  id: string
): Promise<SolicitudContactoDetalle | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/${id}`, {
    credentials: "include",
  });
  if (respuesta.status === 404) {
    return null;
  }
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la solicitud");
  }
  return respuesta.json();
}

export async function editarEstadoContacto(
  id: string,
  estado: "pendiente" | "resuelto"
): Promise<void> {
  const respuesta = await fetch(`${BASE_URL}/admin/contacto/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ estado }),
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo actualizar el estado");
  }
}
```

- [ ] **Step 2: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/admin-contacto-api.ts
git commit -m "feat: cliente API admin de solicitudes de contacto"
```

---

## Task 15: Frontend — link "Contacto" en el nav de admin

**Files:**
- Modify: `frontend/app/admin/layout.tsx`

**Interfaces:**
- Consumes: nada nuevo.
- Produces: un link "Contacto" visible para **ambos** roles (a diferencia de "Usuarios", que sigue siendo solo `super_admin`).

- [ ] **Step 1: Agregar el link**

En `frontend/app/admin/layout.tsx`, dentro de `AdminLayoutInner`, en el `<ul>` de la nav, agregar el link "Contacto" después de "Trámites" y antes del condicional de "Usuarios":

```tsx
            <li>
              <Link href="/admin/tramites" className="text-blue-700 hover:underline">
                Trámites
              </Link>
            </li>
            <li>
              <Link href="/admin/contacto" className="text-blue-700 hover:underline">
                Contacto
              </Link>
            </li>
            {admin?.rol === "super_admin" && (
```

(el resto del archivo, incluyendo el guard de `/admin/login` agregado en la corrección anterior, no cambia).

- [ ] **Step 2: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/layout.tsx
git commit -m "feat: agrega link Contacto al nav de admin"
```

---

## Task 16: Frontend — pantalla `/admin/contacto` (lista)

**Files:**
- Create: `frontend/app/admin/contacto/page.tsx`

**Interfaces:**
- Consumes: `listarSolicitudesContacto` (Task 14).

- [ ] **Step 1: Crear la página**

Crear `frontend/app/admin/contacto/page.tsx`, siguiendo el mismo patrón visual que `app/admin/tramites/page.tsx` (tabla + carga/error/reintentar, sin botón de "nuevo" porque las solicitudes las crea el público, no el admin):

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listarSolicitudesContacto, type SolicitudContacto } from "../../../lib/admin-contacto-api";

export default function ContactoPage() {
  const [solicitudes, setSolicitudes] = useState<SolicitudContacto[] | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const resultado = await listarSolicitudesContacto();
      setSolicitudes(resultado);
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
        <p className="text-sm text-red-600">No se pudo cargar la lista de contacto</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h1 className="mb-4 text-lg font-semibold">Contacto</h1>
      {solicitudes && solicitudes.length === 0 ? (
        <p className="text-sm text-gray-500">Todavía no hay solicitudes de contacto</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="p-2">Fecha</th>
              <th className="p-2">Nombre</th>
              <th className="p-2">Trámite</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Estado</th>
            </tr>
          </thead>
          <tbody>
            {solicitudes!.map((solicitud) => (
              <tr key={solicitud.id} className="border-b border-gray-100">
                <td className="p-2">{new Date(solicitud.creado_en).toLocaleString()}</td>
                <td className="p-2">
                  <Link
                    href={`/admin/contacto/${solicitud.id}`}
                    className="text-blue-700 hover:underline"
                  >
                    {solicitud.nombre}
                  </Link>
                </td>
                <td className="p-2">{solicitud.tramite_nombre ?? "—"}</td>
                <td className="p-2">{solicitud.organismo ?? "—"}</td>
                <td className="p-2">
                  {solicitud.estado === "resuelto" ? "Resuelto" : "Pendiente"}
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

- [ ] **Step 2: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/contacto/page.tsx
git commit -m "feat: pantalla de lista de contacto en admin"
```

---

## Task 17: Frontend — pantalla `/admin/contacto/[id]` (detalle)

**Files:**
- Create: `frontend/app/admin/contacto/[id]/page.tsx`

**Interfaces:**
- Consumes: `obtenerSolicitudContacto`/`editarEstadoContacto` (Task 14), `<ConversacionChat>` (Task 13).

- [ ] **Step 1: Crear la página**

Crear `frontend/app/admin/contacto/[id]/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  editarEstadoContacto,
  obtenerSolicitudContacto,
  type SolicitudContactoDetalle,
} from "../../../../lib/admin-contacto-api";
import { ConversacionChat } from "../../../../components/ConversacionChat";

export default function ContactoDetallePage() {
  const params = useParams<{ id: string }>();
  const [solicitud, setSolicitud] = useState<SolicitudContactoDetalle | null | undefined>(undefined);
  const [error, setError] = useState(false);
  const [actualizandoEstado, setActualizandoEstado] = useState(false);

  useEffect(() => {
    cargar();
  }, [params.id]);

  async function cargar() {
    setError(false);
    setSolicitud(undefined);
    try {
      const resultado = await obtenerSolicitudContacto(params.id);
      setSolicitud(resultado);
    } catch {
      setError(true);
    }
  }

  async function handleCambiarEstado() {
    if (!solicitud) return;
    const nuevoEstado = solicitud.estado === "pendiente" ? "resuelto" : "pendiente";
    setActualizandoEstado(true);
    try {
      await editarEstadoContacto(solicitud.id, nuevoEstado);
      setSolicitud({ ...solicitud, estado: nuevoEstado });
    } catch {
      setError(true);
    } finally {
      setActualizandoEstado(false);
    }
  }

  if (error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar la solicitud</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (solicitud === undefined) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (solicitud === null) {
    return (
      <div className="p-4">
        <p className="text-sm text-gray-600">Solicitud no encontrada</p>
        <Link href="/admin/contacto" className="text-sm text-blue-700 underline">
          Volver a la lista
        </Link>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 max-w-2xl rounded border border-gray-200 p-4">
        <p><span className="font-semibold">Nombre:</span> {solicitud.nombre}</p>
        <p><span className="font-semibold">Email:</span> {solicitud.email}</p>
        <p><span className="font-semibold">Teléfono:</span> {solicitud.telefono}</p>
        <p><span className="font-semibold">Trámite:</span> {solicitud.tramite_nombre ?? "—"}</p>
        <p className="mt-2"><span className="font-semibold">Consulta:</span></p>
        <p className="whitespace-pre-wrap text-sm">{solicitud.consulta}</p>
        <button
          onClick={handleCambiarEstado}
          disabled={actualizandoEstado}
          className="mt-3 rounded bg-blue-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {solicitud.estado === "pendiente" ? "Marcar como resuelto" : "Marcar como pendiente"}
        </button>
      </div>

      <h2 className="mb-2 text-sm font-semibold text-gray-600">Conversación completa</h2>
      <ConversacionChat mensajes={solicitud.mensajes} />
    </div>
  );
}
```

- [ ] **Step 2: Verificar que el frontend compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Correr todos los tests de frontend una vez más**

Run: `cd frontend && npm test`
Expected: PASS (todos).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/contacto/\[id\]/page.tsx
git commit -m "feat: pantalla de detalle de contacto en admin"
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

- [ ] **Step 4: Levantar la app y probar manualmente el flujo completo**

Seguir `.claude/skills/run-macacha/SKILL.md` para levantar backend + frontend + Postgres **local** (no la base remota — para no generar solicitudes de contacto ni mails de prueba contra el sistema real). Configurar `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM` en el `.env` local apuntando a un servidor SMTP de prueba (o dejar sin configurar y confirmar que el flujo sigue funcionando igual gracias al try/except best-effort — la solicitud debe guardarse aunque el mail falle por falta de configuración).

Con el driver del skill (`.claude/skills/run-macacha/driver.mjs`):
1. Ir al chat público, escribir una consulta que identifique un trámite, hacer clic en "¿Necesitás hablar con una persona?", completar el formulario y enviarlo. Confirmar el mensaje de confirmación.
2. Como super-admin, entrar a `/admin/contacto`, verificar que la solicitud aparece con el trámite y organismo correctos, entrar al detalle, verificar que se ve la conversación completa, marcarla como resuelta y confirmar que el estado cambia.
3. Repetir el flujo de chat sin que se identifique ningún trámite (pregunta genérica) y confirmar que el formulario se envía sin selector de trámite, con el aviso de "equipo general", y que la solicitud aparece en `/admin/contacto` con trámite y organismo en blanco (`—`).
4. Como admin de organismo, confirmar que solo ve en `/admin/contacto` las solicitudes de su propio organismo.

Sacar screenshots de cada paso relevante.

- [ ] **Step 5: Limpiar los datos de prueba creados en el paso anterior**

Igual que en el trabajo anterior: usar explícitamente la base local (`postgresql://macacha:macacha@localhost:5432/macacha`), no la del `.env` committeado, para esta verificación. Borrar las solicitudes de contacto de prueba creadas (`DELETE FROM solicitudes_contacto WHERE ...`) al terminar.
