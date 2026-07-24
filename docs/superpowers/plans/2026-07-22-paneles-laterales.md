# Paneles laterales (info del trámite + ranking) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar un layout de tres columnas al chat de Macacha: panel derecho con la info del trámite identificado en la charla (requisitos, teléfono, mail), panel izquierdo con el ranking de trámites más consultados del organismo de ese trámite, y tabs para navegar entre las tres secciones en mobile.

**Architecture:** Dos endpoints REST nuevos en el backend (`GET /tramites/{id}`, `GET /organismos/{organismo}/tramites-frecuentes`) respaldados por una columna de contador (`veces_consultado`) incrementada por turno de chat y dos campos nuevos de contacto en el snapshot del trámite. En el frontend, dos hooks nuevos (`useTramiteActual`, `useTramitesFrecuentes`) derivan estado de los mensajes existentes de `useChatStream` y consumen los endpoints nuevos; dos componentes de panel consumen esos hooks; `app/page.tsx` pasa de una columna a tres (con tabs en mobile).

**Tech Stack:** FastAPI + psycopg (backend, Python 3.12), Next.js 15 + React 19 + TypeScript + Tailwind (frontend), pytest (backend tests), Vitest (frontend tests).

## Global Constraints

- Español para toda la UI y mensajes de usuario; identificadores de código en el estilo ya usado en el repo (nombres de función/variable en español, tipos en inglés cuando corresponde a convenciones de TS).
- Sin librerías de estado adicionales (React Query, SWR, Zustand, Redux) — hooks propios con `useState`/`useEffect`, igual que el resto del frontend.
- El campo `{organismo}` en las rutas es el **nombre** del organismo (mismo string que devuelve `buscar_tramite`), no un ID interno.
- El ranking devuelve como máximo 5 trámites, ordenados por `veces_consultado` descendente, excluyendo los que tienen `veces_consultado = 0`.
- Los comandos de backend se corren desde `backend/` usando el intérprete del venv del proyecto: `backend/.venv/bin/pytest` y `backend/.venv/bin/uvicorn`. Los de frontend se corren desde `frontend/` con `npm test` / `npm run dev`.
- Cambiar `backend/db/schema.sql` requiere recrear el volumen de Postgres (`docker compose down -v && docker compose up -d postgres`) antes de correr los tests — el volumen nombrado conserva el esquema viejo si solo se reinicia el contenedor (ver Task 1).

---

## Backend

### Task 1: Columna `veces_consultado` + contador de consultas

**Files:**
- Modify: `backend/db/schema.sql:8-14` (definición de `tramites`), y agregar una línea de migración al final del archivo.
- Modify: `backend/ingest/repository.py` (agregar función al final del archivo).
- Test: `backend/tests/test_repository.py` (agregar al final del archivo).

**Interfaces:**
- Produces: `repository.incrementar_veces_consultado(conn, tramite_id: str) -> None` — usada por Task 4.
- Produces: columna `tramites.veces_consultado INTEGER NOT NULL DEFAULT 0` — usada por Task 2.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `backend/tests/test_repository.py`:

```python
def test_incrementar_veces_consultado_suma_uno(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT veces_consultado FROM tramites WHERE id = %s", ("RC-0001",))
        assert cur.fetchone()[0] == 2
```

- [ ] **Step 2: Recrear la base de test con el esquema actual (antes de tocar nada más)**

El test todavía va a fallar por `AttributeError` (la función no existe), no por la
columna faltante. Igual, dejamos la base lista ahora para no olvidarnos:

Run: `cd /home/seba/Escritorio/workspace/macacha && docker compose down -v && docker compose up -d postgres`
Expected: contenedor recreado, sin datos previos (se pierde cualquier dato cargado
localmente — esperado, ver nota de `README.md`).

- [ ] **Step 3: Correr el test para verificar que falla**

Run: `cd backend && .venv/bin/pytest tests/test_repository.py::test_incrementar_veces_consultado_suma_uno -v`
Expected: FAIL con `AttributeError: module 'ingest.repository' has no attribute 'incrementar_veces_consultado'`

- [ ] **Step 4: Agregar la columna al esquema**

En `backend/db/schema.sql`, reemplazar el bloque de `tramites` (líneas 8-14):

```sql
CREATE TABLE IF NOT EXISTS tramites (
    id TEXT PRIMARY KEY,
    organismo_id INTEGER NOT NULL REFERENCES organismos(id),
    categoria TEXT NOT NULL,
    nombre_oficial TEXT NOT NULL,
    veces_consultado INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Y agregar al final del archivo (después de la línea 65, siguiendo el mismo patrón
usado para `mensajes.orden`):

```sql

ALTER TABLE tramites ADD COLUMN IF NOT EXISTS veces_consultado INTEGER NOT NULL DEFAULT 0;
```

- [ ] **Step 5: Recrear la base con el esquema nuevo**

Run: `cd /home/seba/Escritorio/workspace/macacha && docker compose down -v && docker compose up -d postgres`
Expected: contenedor recreado; esperar unos segundos a que quede healthy antes del
siguiente paso (`docker compose ps` debe mostrar el servicio corriendo).

- [ ] **Step 6: Implementar la función de repositorio**

Agregar al final de `backend/ingest/repository.py`:

```python
def incrementar_veces_consultado(conn, tramite_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tramites SET veces_consultado = veces_consultado + 1 WHERE id = %s",
            (tramite_id,),
        )
```

- [ ] **Step 7: Correr el test para verificar que pasa**

Run: `cd backend && .venv/bin/pytest tests/test_repository.py::test_incrementar_veces_consultado_suma_uno -v`
Expected: PASS

- [ ] **Step 8: Correr toda la suite de tests de backend para confirmar que el cambio de esquema no rompió nada**

Run: `cd backend && .venv/bin/pytest -v`
Expected: todos los tests existentes siguen en PASS.

- [ ] **Step 9: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/db/schema.sql backend/ingest/repository.py backend/tests/test_repository.py
git commit -m "feat: agregar columna veces_consultado y su incremento en el repositorio"
```

---

### Task 2: Ranking de trámites frecuentes por organismo

**Files:**
- Modify: `backend/ingest/repository.py` (agregar función al final del archivo).
- Test: `backend/tests/test_repository.py` (agregar al final del archivo).

**Interfaces:**
- Consumes: `repository.incrementar_veces_consultado` (Task 1), columna `tramites.veces_consultado` (Task 1).
- Produces: `repository.obtener_tramites_frecuentes(conn, organismo: str, limite: int = 5) -> list[dict]`, cada dict con claves `tramite_id: str`, `nombre_oficial: str`, `veces_consultado: int`. Usada por Task 6.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `backend/tests/test_repository.py`:

```python
def test_obtener_tramites_frecuentes_ordena_por_veces_consultado(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RC-0002", organismo_id, "Actas", "Actas Especiales")
    db_conn.commit()

    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    repo.incrementar_veces_consultado(db_conn, "RC-0002")
    repo.incrementar_veces_consultado(db_conn, "RC-0002")
    db_conn.commit()

    resultado = repo.obtener_tramites_frecuentes(db_conn, "Registro Civil")

    assert resultado == [
        {"tramite_id": "RC-0002", "nombre_oficial": "Actas Especiales", "veces_consultado": 2},
        {"tramite_id": "RC-0001", "nombre_oficial": "Actas Regulares", "veces_consultado": 1},
    ]


def test_obtener_tramites_frecuentes_excluye_no_consultados(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert repo.obtener_tramites_frecuentes(db_conn, "Registro Civil") == []


def test_obtener_tramites_frecuentes_respeta_el_limite(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    for i in range(1, 8):
        tramite_id = f"RC-000{i}"
        repo.upsert_tramite(db_conn, tramite_id, organismo_id, "Actas", f"Trámite {i}")
        db_conn.commit()
        repo.incrementar_veces_consultado(db_conn, tramite_id)
        db_conn.commit()

    resultado = repo.obtener_tramites_frecuentes(db_conn, "Registro Civil")

    assert len(resultado) == 5


def test_obtener_tramites_frecuentes_no_mezcla_organismos(db_conn, clean_db):
    rc_id = repo.upsert_organismo(db_conn, "Registro Civil")
    otro_id = repo.upsert_organismo(db_conn, "Rentas")
    repo.upsert_tramite(db_conn, "RC-0001", rc_id, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RE-0001", otro_id, "Impuestos", "Pago de Rentas")
    db_conn.commit()

    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    repo.incrementar_veces_consultado(db_conn, "RE-0001")
    db_conn.commit()

    resultado = repo.obtener_tramites_frecuentes(db_conn, "Registro Civil")

    assert resultado == [
        {"tramite_id": "RC-0001", "nombre_oficial": "Actas Regulares", "veces_consultado": 1}
    ]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_repository.py -k tramites_frecuentes -v`
Expected: FAIL con `AttributeError: module 'ingest.repository' has no attribute 'obtener_tramites_frecuentes'`

- [ ] **Step 3: Implementar la función de repositorio**

Agregar al final de `backend/ingest/repository.py`:

```python
def obtener_tramites_frecuentes(conn, organismo: str, limite: int = 5) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.nombre_oficial, t.veces_consultado
            FROM tramites t
            JOIN organismos o ON o.id = t.organismo_id
            WHERE o.nombre = %s AND t.veces_consultado > 0
            ORDER BY t.veces_consultado DESC, t.id ASC
            LIMIT %s
            """,
            (organismo, limite),
        )
        return [
            {"tramite_id": row[0], "nombre_oficial": row[1], "veces_consultado": row[2]}
            for row in cur.fetchall()
        ]
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_repository.py -k tramites_frecuentes -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/ingest/repository.py backend/tests/test_repository.py
git commit -m "feat: agregar obtener_tramites_frecuentes al repositorio"
```

---

### Task 3: Campos de contacto en el snapshot del trámite

**Files:**
- Modify: `backend/ingest/snapshot_builder.py:21-39`.
- Test: `backend/tests/test_snapshot_builder.py` (agregar al final del archivo).

**Interfaces:**
- Produces: claves `telefono_contacto: str` y `email_contacto: str` en el dict que devuelve `build_snapshot`, default `""` si no vienen en `raw_tramite`. Usadas por Task 5.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `backend/tests/test_snapshot_builder.py`:

```python
def test_includes_contact_fields_with_defaults_when_missing():
    snapshot = build_snapshot(_raw_tramite(), _faq_generator_no_debe_llamarse)

    assert snapshot["telefono_contacto"] == ""
    assert snapshot["email_contacto"] == ""


def test_includes_contact_fields_when_present():
    raw = _raw_tramite(
        telefono_contacto="0387-4234567", email_contacto="registrocivil@salta.gob.ar"
    )
    snapshot = build_snapshot(raw, _faq_generator_no_debe_llamarse)

    assert snapshot["telefono_contacto"] == "0387-4234567"
    assert snapshot["email_contacto"] == "registrocivil@salta.gob.ar"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_snapshot_builder.py -k contact_fields -v`
Expected: FAIL con `KeyError: 'telefono_contacto'`

- [ ] **Step 3: Implementar el cambio**

En `backend/ingest/snapshot_builder.py`, dentro del `return` de `build_snapshot`
(líneas 21-39), agregar las dos claves nuevas después de `"duracion"`:

```python
    return {
        "id": raw_tramite["id"],
        "organismo": raw_tramite["organismo"],
        "categoria": raw_tramite["categoria"],
        "nombre_oficial": raw_tramite["tramite"],
        "sinonimos": raw_tramite.get("sinonimos", []),
        "keywords": raw_tramite.get("keywords", []),
        "descripcion": raw_tramite.get("descripcion", ""),
        "objetivo": raw_tramite.get("objetivo", ""),
        "requisitos": raw_tramite.get("requisitos", []),
        "pasos": raw_tramite.get("pasos", []),
        "costo": raw_tramite.get("costo", ""),
        "modalidad": raw_tramite.get("modalidad", ""),
        "duracion": raw_tramite.get("duracion", ""),
        "telefono_contacto": raw_tramite.get("telefono_contacto", ""),
        "email_contacto": raw_tramite.get("email_contacto", ""),
        "problemas_frecuentes": raw_tramite.get("problemas_frecuentes", []),
        "preguntas_frecuentes": preguntas_frecuentes,
        "enlaces_oficiales": enlaces_oficiales,
        "faq_generadas_automaticamente": faq_generadas_automaticamente,
    }
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_snapshot_builder.py -v`
Expected: todos PASS (incluyendo los 2 nuevos).

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/ingest/snapshot_builder.py backend/tests/test_snapshot_builder.py
git commit -m "feat: agregar telefono_contacto y email_contacto al snapshot del trámite"
```

---

### Task 4: Incrementar `veces_consultado` en `POST /chat`

**Files:**
- Modify: `backend/agent/api.py:1-76`.
- Test: `backend/tests/test_api.py`.

**Interfaces:**
- Consumes: `repository.incrementar_veces_consultado` (Task 1); evento `{"tipo": "fin", "fuentes": [...]}` que ya emite `procesar_turno` (existente, sin cambios).

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_api.py`, agregar el import que falta al principio del archivo
(junto a los otros imports):

```python
from ingest import repository as repo
```

Y agregar al final del archivo:

```python
def test_post_chat_incrementa_veces_consultado(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "telefono_contacto": "",
        "email_contacto": "",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    session_id = str(uuid.uuid4())
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[obtener_chat_client] = lambda: _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "obtener_requisitos",
                            "arguments": '{"tramite_id": "RC-0001"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Necesitás tu DNI.", "tool_calls": None},
        ]
    )
    api.app.dependency_overrides[obtener_openai_client] = lambda: _FakeOpenAIClient()

    client = TestClient(api.app)
    try:
        respuesta = client.post(
            "/chat", json={"session_id": session_id, "mensaje": "qué necesito para un acta"}
        )
        db_conn.commit()
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    with db_conn.cursor() as cur:
        cur.execute("SELECT veces_consultado FROM tramites WHERE id = %s", ("RC-0001",))
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd backend && .venv/bin/pytest tests/test_api.py::test_post_chat_incrementa_veces_consultado -v`
Expected: FAIL — `assert 0 == 1` (el contador no se incrementa todavía).

- [ ] **Step 3: Implementar el incremento**

En `backend/agent/api.py`, agregar el import (junto a los existentes, línea 16-17):

```python
from db.pool import crear_pool
from ingest.openai_client import build_real_client
from ingest.repository import incrementar_veces_consultado
```

Reemplazar la función `generar()` dentro de `chat()` (líneas 58-74 actuales, sin
tocar el `return StreamingResponse(...)` que queda después, en la línea 76):

```python
    def generar() -> Iterator[str]:
        with pool.connection() as conn:
            try:
                fuentes_del_turno: list[dict] = []
                for evento in procesar_turno(
                    conn,
                    chat_client,
                    openai_client.generate_embeddings,
                    openai_client.rerank,
                    str(request.session_id),
                    request.mensaje,
                ):
                    if evento["tipo"] == "fin":
                        fuentes_del_turno = evento["fuentes"]
                    yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                for fuente in fuentes_del_turno:
                    incrementar_veces_consultado(conn, fuente["tramite_id"])
                conn.commit()
            except Exception:
                conn.rollback()
                evento_error = {"tipo": "error", "mensaje": "Ocurrió un error al procesar tu mensaje."}
                yield f"data: {json.dumps(evento_error, ensure_ascii=False)}\n\n"
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: todos PASS, incluyendo `test_post_chat_incrementa_veces_consultado`.

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/agent/api.py backend/tests/test_api.py
git commit -m "feat: incrementar veces_consultado por cada trámite citado en un turno"
```

---

### Task 5: `GET /tramites/{tramite_id}`

**Files:**
- Modify: `backend/agent/api.py`.
- Test: `backend/tests/test_api.py`.

**Interfaces:**
- Consumes: `obtener_snapshot_vigente` (existente, en `ingest.repository`), campos `telefono_contacto`/`email_contacto` del snapshot (Task 3).
- Produces: endpoint `GET /tramites/{tramite_id}` → 200 con `{tramite_id, nombre_oficial, organismo, categoria, requisitos, telefono_contacto, email_contacto}`, o 404 si no existe. Consumido por el frontend en Task 7.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `backend/tests/test_api.py`:

```python
def test_get_tramite_devuelve_detalle(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "telefono_contacto": "0387-4234567",
        "email_contacto": "registrocivil@salta.gob.ar",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "tramite_id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "requisitos": ["DNI"],
        "telefono_contacto": "0387-4234567",
        "email_contacto": "registrocivil@salta.gob.ar",
    }


def test_get_tramite_inexistente_devuelve_404(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-9999")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -k get_tramite -v`
Expected: FAIL con 404 (ruta no existe / `Not Found` de FastAPI para ambos, ya que la
ruta `/tramites/{id}` no está definida todavía).

- [ ] **Step 3: Implementar el endpoint**

En `backend/agent/api.py`, agregar `HTTPException` al import de fastapi:

```python
from fastapi import Depends, FastAPI, HTTPException
```

Agregar el import de `obtener_snapshot_vigente` junto a los demás imports de `ingest`:

```python
from ingest.openai_client import build_real_client
from ingest.repository import incrementar_veces_consultado, obtener_snapshot_vigente
```

Agregar el endpoint al final de `backend/agent/api.py`:

```python
@app.get("/tramites/{tramite_id}")
def obtener_tramite(tramite_id: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Trámite no encontrado")
        return {
            "tramite_id": tramite_id,
            "nombre_oficial": snapshot["nombre_oficial"],
            "organismo": snapshot["organismo"],
            "categoria": snapshot["categoria"],
            "requisitos": snapshot.get("requisitos", []),
            "telefono_contacto": snapshot.get("telefono_contacto", ""),
            "email_contacto": snapshot.get("email_contacto", ""),
        }
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/agent/api.py backend/tests/test_api.py
git commit -m "feat: agregar GET /tramites/{tramite_id}"
```

---

### Task 6: `GET /organismos/{organismo}/tramites-frecuentes`

**Files:**
- Modify: `backend/agent/api.py`.
- Test: `backend/tests/test_api.py`.

**Interfaces:**
- Consumes: `repository.obtener_tramites_frecuentes` (Task 2).
- Produces: endpoint `GET /organismos/{organismo}/tramites-frecuentes` → 200 con `[{tramite_id, nombre_oficial, veces_consultado}, ...]` (posiblemente `[]`). Consumido por el frontend en Task 7.

- [ ] **Step 1: Escribir el test que falla**

Agregar al principio de `backend/tests/test_api.py` un import de `urllib.parse`:

```python
import urllib.parse
```

Y al final del archivo:

```python
def test_get_tramites_frecuentes_devuelve_ranking(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RC-0002", organismo_id, "Actas", "Actas Especiales")
    db_conn.commit()
    repo.incrementar_veces_consultado(db_conn, "RC-0002")
    repo.incrementar_veces_consultado(db_conn, "RC-0002")
    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get(
            f"/organismos/{urllib.parse.quote('Registro Civil')}/tramites-frecuentes"
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == [
        {"tramite_id": "RC-0002", "nombre_oficial": "Actas Especiales", "veces_consultado": 2},
        {"tramite_id": "RC-0001", "nombre_oficial": "Actas Regulares", "veces_consultado": 1},
    ]


def test_get_tramites_frecuentes_organismo_sin_consultas_devuelve_lista_vacia(db_conn, clean_db):
    repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get(
            f"/organismos/{urllib.parse.quote('Registro Civil')}/tramites-frecuentes"
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == []
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -k tramites_frecuentes -v`
Expected: FAIL con 404 (ruta no definida todavía).

- [ ] **Step 3: Implementar el endpoint**

Agregar el import junto al de `obtener_snapshot_vigente` en `backend/agent/api.py`:

```python
from ingest.repository import (
    incrementar_veces_consultado,
    obtener_snapshot_vigente,
    obtener_tramites_frecuentes,
)
```

Agregar el endpoint al final de `backend/agent/api.py`:

```python
@app.get("/organismos/{organismo}/tramites-frecuentes")
def tramites_frecuentes(organismo: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return obtener_tramites_frecuentes(conn, organismo)
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && .venv/bin/pytest tests/test_api.py -v`
Expected: todos PASS.

- [ ] **Step 5: Correr toda la suite de backend una última vez**

Run: `cd backend && .venv/bin/pytest -v`
Expected: todos PASS. Esto cierra el trabajo de backend del plan.

- [ ] **Step 6: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add backend/agent/api.py backend/tests/test_api.py
git commit -m "feat: agregar GET /organismos/{organismo}/tramites-frecuentes"
```

---

## Frontend

### Task 7: Cliente API para los paneles

**Files:**
- Modify: `frontend/lib/api.ts`.

**Interfaces:**
- Consumes: `GET /tramites/{tramite_id}` (Task 5), `GET /organismos/{organismo}/tramites-frecuentes` (Task 6), `BASE_URL` (existente).
- Produces: tipos `TramiteDetalle`, `TramiteFrecuente`; funciones `obtenerTramite(tramiteId: string): Promise<TramiteDetalle | null>` y `obtenerTramitesFrecuentes(organismo: string): Promise<TramiteFrecuente[]>`. Usadas por Task 8 y Task 9.

No hay tests unitarios dedicados para este archivo — sigue el mismo patrón que
`obtenerHistorial` (fetch wrapper sin lógica no trivial), verificado indirectamente
por los tests de los hooks (Task 8) y por la verificación manual (Task 13).

- [ ] **Step 1: Agregar los tipos y funciones**

Reemplazar el contenido completo de `frontend/lib/api.ts`:

```typescript
export type MensajeVisible = {
  rol: "user" | "assistant";
  contenido: string;
  creado_en: string;
};

export type TramiteDetalle = {
  tramite_id: string;
  nombre_oficial: string;
  organismo: string;
  categoria: string;
  requisitos: string[];
  telefono_contacto: string;
  email_contacto: string;
};

export type TramiteFrecuente = {
  tramite_id: string;
  nombre_oficial: string;
  veces_consultado: number;
};

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function obtenerHistorial(
  sessionId: string
): Promise<MensajeVisible[]> {
  const respuesta = await fetch(`${BASE_URL}/sesiones/${sessionId}/mensajes`);
  if (!respuesta.ok) {
    return [];
  }
  return respuesta.json();
}

export async function obtenerTramite(
  tramiteId: string
): Promise<TramiteDetalle | null> {
  const respuesta = await fetch(`${BASE_URL}/tramites/${tramiteId}`);
  if (!respuesta.ok) {
    return null;
  }
  return respuesta.json();
}

export async function obtenerTramitesFrecuentes(
  organismo: string
): Promise<TramiteFrecuente[]> {
  const respuesta = await fetch(
    `${BASE_URL}/organismos/${encodeURIComponent(organismo)}/tramites-frecuentes`
  );
  if (!respuesta.ok) {
    return [];
  }
  return respuesta.json();
}
```

- [ ] **Step 2: Verificar que el proyecto sigue compilando**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores (todavía nada consume las funciones nuevas, pero el archivo
debe tipar correctamente).

- [ ] **Step 3: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/lib/api.ts
git commit -m "feat: agregar obtenerTramite y obtenerTramitesFrecuentes a lib/api.ts"
```

---

### Task 8: Hook `useTramiteActual`

**Files:**
- Create: `frontend/hooks/useTramiteActual.ts`.
- Test: `frontend/hooks/useTramiteActual.test.ts`.

**Interfaces:**
- Consumes: `Mensaje`/`Fuente` tipos de `frontend/hooks/useChatStream.ts` (existente), `obtenerTramite`/`TramiteDetalle` de `frontend/lib/api.ts` (Task 7).
- Produces: función pura `obtenerUltimoTramiteId(mensajes: Mensaje[]): string | null` (testeada directamente); hook `useTramiteActual(mensajes: Mensaje[]): { tramite: TramiteDetalle | null; cargando: boolean }`. Usado por Task 12.

- [ ] **Step 1: Escribir el archivo de test**

Crear `frontend/hooks/useTramiteActual.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { obtenerUltimoTramiteId } from "./useTramiteActual";
import type { Mensaje } from "./useChatStream";

describe("obtenerUltimoTramiteId", () => {
  it("devuelve null si ningún mensaje tiene fuentes", () => {
    const mensajes: Mensaje[] = [
      { rol: "user", contenido: "hola" },
      { rol: "assistant", contenido: "hola, en qué te ayudo?" },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBeNull();
  });

  it("devuelve el tramite_id de la última fuente del último mensaje con fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null },
        ],
      },
      { rol: "user", contenido: "y para otro trámite?" },
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0002", nombre_oficial: "Otro trámite", fuente_url: null },
        ],
      },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBe("RC-0002");
  });

  it("dentro de un mismo mensaje, toma el último tramite_id de la lista de fuentes", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [
          { tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null },
          { tramite_id: "RC-0003", nombre_oficial: "Otro trámite más", fuente_url: null },
        ],
      },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBe("RC-0003");
  });

  it("ignora mensajes con fuentes vacías y usa el último no vacío", () => {
    const mensajes: Mensaje[] = [
      {
        rol: "assistant",
        contenido: "...",
        fuentes: [{ tramite_id: "RC-0001", nombre_oficial: "Actas Regulares", fuente_url: null }],
      },
      { rol: "assistant", contenido: "no encontré nada", fuentes: [] },
    ];
    expect(obtenerUltimoTramiteId(mensajes)).toBe("RC-0001");
  });
});
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd frontend && npm test -- useTramiteActual`
Expected: FAIL — no se puede resolver el módulo `./useTramiteActual` (el archivo
todavía no existe).

- [ ] **Step 3: Implementar el hook**

Crear `frontend/hooks/useTramiteActual.ts`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { obtenerTramite, TramiteDetalle } from "../lib/api";
import type { Mensaje } from "./useChatStream";

export function obtenerUltimoTramiteId(mensajes: Mensaje[]): string | null {
  for (let i = mensajes.length - 1; i >= 0; i--) {
    const fuentes = mensajes[i].fuentes;
    if (fuentes && fuentes.length > 0) {
      return fuentes[fuentes.length - 1].tramite_id;
    }
  }
  return null;
}

export function useTramiteActual(mensajes: Mensaje[]) {
  const [tramite, setTramite] = useState<TramiteDetalle | null>(null);
  const [cargando, setCargando] = useState(false);
  const tramiteId = obtenerUltimoTramiteId(mensajes);

  useEffect(() => {
    if (!tramiteId) {
      setTramite(null);
      return;
    }
    setCargando(true);
    obtenerTramite(tramiteId)
      .then(setTramite)
      .catch(() => setTramite(null))
      .finally(() => setCargando(false));
  }, [tramiteId]);

  return { tramite, cargando };
}
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd frontend && npm test -- useTramiteActual`
Expected: 4 PASS.

- [ ] **Step 5: Correr toda la suite de frontend para confirmar que nada se rompió**

Run: `cd frontend && npm test`
Expected: todos los tests (los de `useChatStream` + los nuevos) en PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/hooks/useTramiteActual.ts frontend/hooks/useTramiteActual.test.ts
git commit -m "feat: agregar hook useTramiteActual"
```

---

### Task 9: Hook `useTramitesFrecuentes`

**Files:**
- Create: `frontend/hooks/useTramitesFrecuentes.ts`.

**Interfaces:**
- Consumes: `obtenerTramitesFrecuentes`/`TramiteFrecuente` de `frontend/lib/api.ts` (Task 7).
- Produces: hook `useTramitesFrecuentes(organismo: string | undefined): { tramites: TramiteFrecuente[]; cargando: boolean }`. Usado por Task 12.

Sin test dedicado: la lógica es un fetch condicionado a un valor (mismo nivel de
trivialidad que `useSession`, que tampoco tiene test propio en este repo). Se
verifica junto con `TramitesFrecuentesPanel` en la verificación manual (Task 13).

- [ ] **Step 1: Implementar el hook**

Crear `frontend/hooks/useTramitesFrecuentes.ts`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { obtenerTramitesFrecuentes, TramiteFrecuente } from "../lib/api";

export function useTramitesFrecuentes(organismo: string | undefined) {
  const [tramites, setTramites] = useState<TramiteFrecuente[]>([]);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    if (!organismo) {
      setTramites([]);
      return;
    }
    setCargando(true);
    obtenerTramitesFrecuentes(organismo)
      .then(setTramites)
      .catch(() => setTramites([]))
      .finally(() => setCargando(false));
  }, [organismo]);

  return { tramites, cargando };
}
```

- [ ] **Step 2: Verificar que el proyecto sigue compilando**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/hooks/useTramitesFrecuentes.ts
git commit -m "feat: agregar hook useTramitesFrecuentes"
```

---

### Task 10: Componente `TramiteInfoPanel`

**Files:**
- Create: `frontend/components/TramiteInfoPanel.tsx`.

**Interfaces:**
- Consumes: tipo `TramiteDetalle` de `frontend/lib/api.ts` (Task 7).
- Produces: componente `TramiteInfoPanel({ tramite }: { tramite: TramiteDetalle | null })`. Usado por Task 12.

- [ ] **Step 1: Implementar el componente**

Crear `frontend/components/TramiteInfoPanel.tsx`:

```typescript
import type { TramiteDetalle } from "../lib/api";

export function TramiteInfoPanel({ tramite }: { tramite: TramiteDetalle | null }) {
  if (!tramite) {
    return (
      <p className="text-sm text-gray-400">
        La info del trámite va a aparecer acá.
      </p>
    );
  }

  return (
    <div>
      <h2 className="font-semibold">{tramite.nombre_oficial}</h2>
      <p className="text-sm text-gray-500">{tramite.organismo}</p>

      {tramite.requisitos.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium">Requisitos</h3>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {tramite.requisitos.map((requisito) => (
              <li key={requisito}>{requisito}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 text-sm">
        <h3 className="font-medium">Contacto</h3>
        {tramite.telefono_contacto && <p>Tel: {tramite.telefono_contacto}</p>}
        {tramite.email_contacto && <p>Mail: {tramite.email_contacto}</p>}
        {!tramite.telefono_contacto && !tramite.email_contacto && (
          <p className="text-gray-400">Sin datos de contacto.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verificar que el proyecto sigue compilando**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/components/TramiteInfoPanel.tsx
git commit -m "feat: agregar componente TramiteInfoPanel"
```

---

### Task 11: Componente `TramitesFrecuentesPanel`

**Files:**
- Create: `frontend/components/TramitesFrecuentesPanel.tsx`.

**Interfaces:**
- Consumes: tipo `TramiteFrecuente` de `frontend/lib/api.ts` (Task 7).
- Produces: componente `TramitesFrecuentesPanel({ tramites }: { tramites: TramiteFrecuente[] })`. Usado por Task 12.

- [ ] **Step 1: Implementar el componente**

Crear `frontend/components/TramitesFrecuentesPanel.tsx`:

```typescript
import type { TramiteFrecuente } from "../lib/api";

export function TramitesFrecuentesPanel({
  tramites,
}: {
  tramites: TramiteFrecuente[];
}) {
  if (tramites.length === 0) {
    return (
      <p className="text-sm text-gray-400">
        Los trámites más consultados van a aparecer acá.
      </p>
    );
  }

  return (
    <div>
      <h2 className="font-semibold">Más consultados</h2>
      <ol className="mt-2 space-y-2 text-sm">
        {tramites.map((tramite, indice) => (
          <li key={tramite.tramite_id} className="flex justify-between gap-2">
            <span>
              {indice + 1}. {tramite.nombre_oficial}
            </span>
            <span className="text-gray-400">{tramite.veces_consultado}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
```

- [ ] **Step 2: Verificar que el proyecto sigue compilando**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/components/TramitesFrecuentesPanel.tsx
git commit -m "feat: agregar componente TramitesFrecuentesPanel"
```

---

### Task 12: Layout de tres columnas con tabs en mobile

**Files:**
- Modify: `frontend/app/page.tsx` (reemplazo completo).

**Interfaces:**
- Consumes: `useChatStream` (existente), `useTramiteActual` (Task 8), `useTramitesFrecuentes` (Task 9), `TramiteInfoPanel` (Task 10), `TramitesFrecuentesPanel` (Task 11), `ChatMessage`/`ChatInput` (existentes).

- [ ] **Step 1: Reemplazar `app/page.tsx`**

Reemplazar el contenido completo de `frontend/app/page.tsx`:

```typescript
"use client";

import { useState } from "react";
import { ChatInput } from "../components/ChatInput";
import { ChatMessage } from "../components/ChatMessage";
import { TramiteInfoPanel } from "../components/TramiteInfoPanel";
import { TramitesFrecuentesPanel } from "../components/TramitesFrecuentesPanel";
import { useChatStream } from "../hooks/useChatStream";
import { useSession } from "../hooks/useSession";
import { useTramiteActual } from "../hooks/useTramiteActual";
import { useTramitesFrecuentes } from "../hooks/useTramitesFrecuentes";

export default function Home() {
  const { sessionId } = useSession();

  if (!sessionId) {
    return null;
  }

  return <Chat sessionId={sessionId} />;
}

type Tab = "chat" | "info" | "frecuentes";

function Chat({ sessionId }: { sessionId: string }) {
  const { mensajes, enviando, enviarMensaje } = useChatStream(sessionId);
  const { tramite } = useTramiteActual(mensajes);
  const { tramites: tramitesFrecuentes } = useTramitesFrecuentes(tramite?.organismo);
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <div className="mx-auto flex h-screen max-w-6xl flex-col md:flex-row">
      <nav className="flex border-b border-gray-200 md:hidden">
        <TabButton activo={tab === "chat"} onClick={() => setTab("chat")}>
          Chat
        </TabButton>
        <TabButton activo={tab === "info"} onClick={() => setTab("info")}>
          Info del trámite
        </TabButton>
        <TabButton activo={tab === "frecuentes"} onClick={() => setTab("frecuentes")}>
          Más consultados
        </TabButton>
      </nav>

      <aside
        className={`w-full overflow-y-auto border-gray-200 p-4 md:block md:w-64 md:border-r ${
          tab === "frecuentes" ? "block" : "hidden"
        }`}
      >
        <TramitesFrecuentesPanel tramites={tramitesFrecuentes} />
      </aside>

      <main
        className={`min-w-0 flex-1 flex-col ${tab === "chat" ? "flex" : "hidden"} md:flex`}
      >
        <header className="border-b border-gray-200 p-4">
          <h1 className="text-lg font-semibold">Macacha</h1>
          <p className="text-sm text-gray-500">
            Asistente de trámites — Provincia de Salta
          </p>
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {mensajes.map((mensaje, indice) => (
            <ChatMessage
              key={indice}
              mensaje={mensaje}
              onReintentar={
                mensaje.error && !enviando
                  ? () => {
                      const anterior = mensajes[indice - 1];
                      if (anterior) enviarMensaje(anterior.contenido);
                    }
                  : undefined
              }
            />
          ))}
          {enviando && <p className="text-sm text-gray-400">escribiendo…</p>}
        </div>
        <ChatInput disabled={enviando} onEnviar={enviarMensaje} />
      </main>

      <aside
        className={`w-full overflow-y-auto border-gray-200 p-4 md:block md:w-72 md:border-l ${
          tab === "info" ? "block" : "hidden"
        }`}
      >
        <TramiteInfoPanel tramite={tramite} />
      </aside>
    </div>
  );
}

function TabButton({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      className={`flex-1 p-3 text-sm font-medium ${
        activo ? "border-b-2 border-blue-600 text-blue-600" : "text-gray-500"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 2: Verificar que el proyecto compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 3: Correr toda la suite de tests de frontend**

Run: `cd frontend && npm test`
Expected: todos PASS (nada de esto tiene lógica testeable nueva más allá de lo ya
cubierto en Task 8, pero confirma que no rompimos nada).

- [ ] **Step 4: Commit**

```bash
cd /home/seba/Escritorio/workspace/macacha
git add frontend/app/page.tsx
git commit -m "feat: layout de tres columnas con tabs en mobile"
```

---

### Task 13: Verificación manual end-to-end

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Levantar Postgres, backend y frontend**

Run: `cd /home/seba/Escritorio/workspace/macacha && docker compose up -d postgres`
Run (en otra terminal): `cd backend && .venv/bin/uvicorn agent.api:app --host 0.0.0.0 --port 8002 --reload`
Run (en otra terminal): `cd frontend && npm run dev`

- [ ] **Step 2: Ingerir al menos un trámite con datos de contacto**

Si la base quedó vacía por el `docker compose down -v` de las Tasks anteriores,
cargar de nuevo los trámites de prueba disponibles en el repo (ver
`README.md`, sección "Ingesta de trámites") antes de probar, o insertar uno de
prueba a mano con `telefono_contacto`/`email_contacto` en el JSON de origen.

- [ ] **Step 3: Probar el flujo completo en el navegador (desktop)**

Abrir `http://localhost:3000`. Preguntar por un trámite (ej. "¿qué necesito para
sacar un acta de nacimiento?"). Confirmar:
- El panel derecho pasa del estado vacío a mostrar nombre oficial, requisitos y
  contacto del trámite.
- El panel izquierdo muestra el ranking del organismo de ese trámite, con el
  trámite recién consultado en la lista.
- Preguntar por un trámite de otro organismo actualiza ambos paneles.

- [ ] **Step 4: Probar en viewport mobile**

Con las devtools del navegador en modo mobile (viewport angosto), confirmar que
aparecen los tabs "Chat" / "Info del trámite" / "Más consultados" y que cada uno
muestra su sección a pantalla completa al tocarlo.

- [ ] **Step 5: Confirmar el caso de error existente sigue funcionando**

Detener el backend mientras el frontend sigue corriendo, enviar un mensaje, y
confirmar que se sigue viendo el mensaje de error con el botón "Reintentar" (este
comportamiento no debería haberse roto por los cambios de este plan).
