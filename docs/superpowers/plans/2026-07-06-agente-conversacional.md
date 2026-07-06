# Agente Conversacional (Macacha) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir `backend/agent/`, el subsistema de agente conversacional de Macacha: 7 herramientas de tool-calling sobre el motor de recuperación y el núcleo de datos, un loop de orquestación con historial persistente en Postgres, y un servicio FastAPI con streaming de la respuesta final.

**Architecture:** Un `ChatClient` (nuevo, separado de `OpenAIClient`) resuelve el loop de tool-calling con llamadas no-streaming a `gpt-4o-mini`; el orquestador ejecuta las tools que el modelo pida, persiste cada paso en `sesiones`/`mensajes`, y cuando el modelo ya no pide más tools, trocea esa respuesta (ya generada) por palabra y la emite como eventos SSE — sin pedir una segunda llamada en modo streaming real, para no duplicar costo de tokens. FastAPI expone esto con un pool de conexiones (`psycopg_pool`) que registra el adaptador de pgvector en cada conexión nueva.

**Tech Stack:** Python 3.11+, FastAPI, `psycopg-pool`, `uvicorn` (servidor ASGI), OpenAI SDK (`gpt-4o-mini`), reutilizando `backend/retrieval/` (motor de recuperación) y `backend/ingest/` (núcleo de datos) ya implementados.

## Global Constraints

- Modelo del agente: `gpt-4o-mini` (mismo modelo que ya se usa para FAQs y re-ranking).
- El loop de tool-calling se resuelve con llamadas **no-streaming**; la respuesta final (ya generada, sin tool_calls) se trocea por palabra y se emite como eventos SSE — **no** se vuelve a pedir en modo streaming real.
- Máximo 5 iteraciones del loop de tool-calling por turno, para evitar bucles infinitos.
- Conexiones a Postgres vía `psycopg_pool.ConnectionPool`, con `pgvector.psycopg.register_vector` aplicado en cada conexión nueva del pool (`configure=...`).
- Sesión anónima: `sesiones.id` es el UUID que manda el cliente; no hay autenticación.
- Ningún test de este subsistema hace una llamada real a la red/API de OpenAI — todos usan fakes/stubs inyectados.
- Sin ORM: SQL directo vía `psycopg3`. Todo el trabajo vive bajo `backend/` dentro del repo `macacha`.
- Sin despliegue a producción ni CI/CD en este plan.

---

## Task 1: Esquema de sesiones + pool de conexiones

**Files:**
- Modify: `backend/db/schema.sql`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_schema_smoke.py`
- Modify: `backend/requirements.txt`
- Create: `backend/db/pool.py`
- Test: `backend/tests/test_pool.py`

**Interfaces:**
- Produces: tablas `sesiones(id uuid, created_at)` y `mensajes(id uuid, session_id uuid, rol text, contenido text, tool_calls jsonb, tool_call_id text, created_at)`.
- Produces: fixture `clean_db` (en `backend/tests/conftest.py`) extendida para limpiar también `mensajes`/`sesiones` (en ese orden, antes de las tablas de trámites).
- Produces: `db.pool.crear_pool(database_url: str) -> psycopg_pool.ConnectionPool`, con `pgvector` registrado en cada conexión nueva. Esta es la función que usará `backend/agent/api.py` (Task 7).

- [ ] **Step 1: Escribir el test que falla (extender el smoke test existente)**

Reemplazar el contenido de `backend/tests/test_schema_smoke.py`:

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
        } <= tables
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_schema_smoke.py -v`
Expected: FAIL — `assert {..., "sesiones", "mensajes"} <= tables` no se cumple (las tablas todavía no existen).

- [ ] **Step 3: Agregar las tablas a `backend/db/schema.sql`**

Agregar al final del archivo:

```sql

CREATE TABLE IF NOT EXISTS sesiones (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mensajes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sesiones(id),
    rol TEXT NOT NULL,
    contenido TEXT,
    tool_calls JSONB,
    tool_call_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS mensajes_session_idx ON mensajes (session_id, created_at);
```

- [ ] **Step 4: Aplicar las tablas nuevas a las bases ya existentes**

Las bases `macacha` y `macacha_test` ya fueron creadas por Docker Compose en un subsistema anterior (con datos reales ya ingeridos en `macacha`) — los scripts de `docker-entrypoint-initdb.d` solo corren una vez, al crear el volumen, así que agregar SQL a `schema.sql` no alcanza para las bases ya existentes. Aplicar la migración directamente:

Run:
```bash
cd /home/seba/Escritorio/hackathon/macacha
docker compose up -d postgres
docker compose exec -T postgres psql -U macacha -d macacha -f /docker-entrypoint-initdb.d/10-schema.sql
docker compose exec -T postgres psql -U macacha -d macacha_test -f /docker-entrypoint-initdb.d/10-schema.sql
```
Expected: sin errores (todas las sentencias son `CREATE ... IF NOT EXISTS`, así que las tablas ya existentes no se tocan y solo se crean `sesiones`/`mensajes`).

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_schema_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Extender la fixture `clean_db` en `backend/tests/conftest.py`**

Reemplazar la función `_clean` dentro de la fixture `clean_db`:

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

    _clean()
    yield
    _clean()
    conn.close()
```

- [ ] **Step 7: Correr toda la suite para confirmar que la fixture extendida no rompe nada**

Run: `cd backend && pytest -v`
Expected: todos los tests existentes siguen pasando (34 passed).

- [ ] **Step 8: Agregar `psycopg-pool` a `backend/requirements.txt`**

Agregar esta línea al archivo (después de `pgvector`):

```
psycopg-pool>=3.2,<4
```

Contenido final de `backend/requirements.txt`:

```
psycopg[binary]>=3.2,<4
pgvector>=0.3,<0.4
psycopg-pool>=3.2,<4
openai>=1.50,<2
python-dotenv>=1.0,<2
pytest>=8.0,<9
```

Run: `cd backend && pip install -r requirements.txt`

- [ ] **Step 9: Escribir el test que falla para el pool**

Crear `backend/tests/test_pool.py`:

```python
import os

from db.pool import crear_pool
from ingest import repository as repo
from retrieval.vector_search import buscar_por_similitud


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://macacha:macacha@localhost:5432/macacha_test",
    )


def test_pool_connections_support_vector_queries(clean_db):
    pool = crear_pool(_test_database_url())
    try:
        with pool.connection() as conn:
            organismo_id = repo.upsert_organismo(conn, "Registro Civil")
            repo.upsert_tramite(conn, "RC-TEST", organismo_id, "Actas", "Prueba")
            repo.insert_version_with_chunks(
                conn,
                "RC-TEST",
                1,
                "hash-test",
                {"id": "RC-TEST"},
                [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}],
                [[0.0] * 1536],
            )
            conn.commit()

            resultados = buscar_por_similitud(conn, [0.0] * 1536, top_n=5)

        assert len(resultados) == 1
    finally:
        pool.close()
```

- [ ] **Step 10: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_pool.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'db.pool'`

- [ ] **Step 11: Implementar `backend/db/pool.py`**

```python
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector


def _configurar_conexion(conn):
    register_vector(conn)


def crear_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(database_url, configure=_configurar_conexion, open=True)
```

- [ ] **Step 12: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_pool.py -v`
Expected: PASS (1 passed) — sin este pool aplicando `register_vector`, la consulta hubiera fallado al no poder serializar la lista de floats como `vector`.

- [ ] **Step 13: Commit**

```bash
git add backend/db/schema.sql backend/db/pool.py backend/tests/conftest.py \
  backend/tests/test_schema_smoke.py backend/tests/test_pool.py backend/requirements.txt
git commit -m "feat: esquema de sesiones/mensajes y pool de conexiones con pgvector"
```

---

## Task 2: `obtener_snapshot_vigente` en el repository

**Files:**
- Modify: `backend/ingest/repository.py`
- Modify: `backend/tests/test_repository.py`

**Interfaces:**
- Produces: `repository.obtener_snapshot_vigente(conn, tramite_id: str) -> dict | None`. Devuelve el snapshot JSONB completo de la versión vigente, o `None` si el trámite no existe o no tiene versión vigente. Esta es la función que van a usar todas las tools de `backend/agent/tools.py` (Task 4) excepto `buscar_tramite`.

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `backend/tests/test_repository.py`:

```python
def test_obtener_snapshot_vigente_devuelve_none_si_no_hay_version(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert repo.obtener_snapshot_vigente(db_conn, "RC-0001") is None


def test_obtener_snapshot_vigente_devuelve_el_snapshot(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {"id": "RC-0001", "requisitos": ["DNI"], "costo": "$6000"}
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    resultado = repo.obtener_snapshot_vigente(db_conn, "RC-0001")

    assert resultado == snapshot
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_repository.py -v -k obtener_snapshot_vigente`
Expected: FAIL con `AttributeError: module 'ingest.repository' has no attribute 'obtener_snapshot_vigente'`

- [ ] **Step 3: Implementar `obtener_snapshot_vigente` en `backend/ingest/repository.py`**

Agregar al final del archivo:

```python
def obtener_snapshot_vigente(conn, tramite_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT snapshot
            FROM tramite_versiones
            WHERE tramite_id = %s AND es_vigente = true
            """,
            (tramite_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return row[0]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_repository.py -v -k obtener_snapshot_vigente`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/repository.py backend/tests/test_repository.py
git commit -m "feat: obtener_snapshot_vigente para leer el snapshot de un trámite por id"
```

---

## Task 3: Sesiones y mensajes (`backend/agent/sessions.py`)

**Files:**
- Create: `backend/agent/__init__.py`
- Create: `backend/agent/sessions.py`
- Test: `backend/tests/test_sessions.py`

**Interfaces:**
- Produces:
  - `sessions.crear_sesion_si_no_existe(conn, session_id: str) -> None`
  - `sessions.guardar_mensaje(conn, session_id: str, rol: str, contenido: str | None = None, tool_calls: list[dict] | None = None, tool_call_id: str | None = None) -> None`
  - `sessions.obtener_historial(conn, session_id: str) -> list[dict]` — devuelve mensajes en formato de mensaje de OpenAI (`{"role", "content", "tool_calls"?, "tool_call_id"?}`), en orden cronológico. Esta es la forma exacta que va a consumir el orquestador (Task 6) para armar el historial que se manda al modelo.
  - `sessions.obtener_mensajes_visibles(conn, session_id: str) -> list[dict]` — devuelve solo mensajes `rol` en `user`/`assistant` con `contenido` no nulo, con forma `{"rol", "contenido", "creado_en"}`. Esta es la forma que expone `GET /sesiones/{id}/mensajes` (Task 7).

- [ ] **Step 1: Crear `backend/agent/__init__.py` (vacío)**

```python
```

- [ ] **Step 2: Escribir el test que falla**

Crear `backend/tests/test_sessions.py`:

```python
import uuid

from agent import sessions


def test_crear_sesion_si_no_existe_es_idempotente(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM sesiones WHERE id = %s", (session_id,))
        assert cur.fetchone()[0] == 1


def test_guardar_mensaje_y_obtener_historial_en_orden(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

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
                "function": {"name": "buscar_tramite", "arguments": "{}"},
            }
        ],
    )
    sessions.guardar_mensaje(db_conn, session_id, rol="tool", contenido="[]", tool_call_id="call_1")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta final")
    db_conn.commit()

    historial = sessions.obtener_historial(db_conn, session_id)

    assert [m["role"] for m in historial] == ["user", "assistant", "tool", "assistant"]
    assert historial[0]["content"] == "hola"
    assert historial[1]["tool_calls"][0]["function"]["name"] == "buscar_tramite"
    assert historial[2]["tool_call_id"] == "call_1"
    assert historial[3]["content"] == "respuesta final"


def test_obtener_mensajes_visibles_excluye_tool_calling_interno(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

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
                "function": {"name": "buscar_tramite", "arguments": "{}"},
            }
        ],
    )
    sessions.guardar_mensaje(db_conn, session_id, rol="tool", contenido="[]", tool_call_id="call_1")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta final")
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert [m["rol"] for m in visibles] == ["user", "assistant"]
    assert [m["contenido"] for m in visibles] == ["hola", "respuesta final"]
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_sessions.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.sessions'`

- [ ] **Step 4: Implementar `backend/agent/sessions.py`**

```python
import json


def crear_sesion_si_no_existe(conn, session_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sesiones (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (session_id,),
        )


def guardar_mensaje(
    conn,
    session_id: str,
    rol: str,
    contenido: str | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mensajes (session_id, rol, contenido, tool_calls, tool_call_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                session_id,
                rol,
                contenido,
                json.dumps(tool_calls) if tool_calls is not None else None,
                tool_call_id,
            ),
        )


def obtener_historial(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, tool_calls, tool_call_id
            FROM mensajes
            WHERE session_id = %s
            ORDER BY created_at
            """,
            (session_id,),
        )
        historial = []
        for rol, contenido, tool_calls, tool_call_id in cur.fetchall():
            mensaje: dict = {"role": rol, "content": contenido}
            if tool_calls is not None:
                mensaje["tool_calls"] = tool_calls
            if tool_call_id is not None:
                mensaje["tool_call_id"] = tool_call_id
            historial.append(mensaje)
        return historial


def obtener_mensajes_visibles(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, created_at
            FROM mensajes
            WHERE session_id = %s AND rol IN ('user', 'assistant') AND contenido IS NOT NULL
            ORDER BY created_at
            """,
            (session_id,),
        )
        return [
            {"rol": rol, "contenido": contenido, "creado_en": creado_en.isoformat()}
            for rol, contenido, creado_en in cur.fetchall()
        ]
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_sessions.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/__init__.py backend/agent/sessions.py backend/tests/test_sessions.py
git commit -m "feat: persistencia de sesiones y mensajes del agente"
```

---

## Task 4: Las 7 herramientas (`backend/agent/tools.py`)

**Files:**
- Create: `backend/agent/tools.py`
- Test: `backend/tests/test_tools.py`

**Interfaces:**
- Consumes: `retrieval.hybrid_search.buscar_chunks` (ya existente), `ingest.repository.obtener_snapshot_vigente` (Task 2).
- Produces:
  - `tools.TOOL_SCHEMAS: list[dict]` — 7 esquemas de function-calling de OpenAI.
  - `tools.buscar_tramite(conn, embed_fn, rerank_fn, query: str) -> list[dict]`
  - `tools.obtener_requisitos(conn, tramite_id: str) -> list[str]`
  - `tools.obtener_costos_modalidad(conn, tramite_id: str) -> dict`
  - `tools.obtener_pasos(conn, tramite_id: str) -> list[str]`
  - `tools.obtener_normativa(conn, tramite_id: str) -> dict`
  - `tools.obtener_formularios_enlaces(conn, tramite_id: str) -> list[str]`
  - `tools.obtener_problemas_frecuentes(conn, tramite_id: str) -> list[str]`
  - `tools.ejecutar_tool(nombre: str, argumentos: dict, conn, embed_fn, rerank_fn) -> Any` — despacha por nombre a la función correspondiente; esta es la única función que va a llamar el orquestador (Task 6), que no necesita conocer las firmas individuales de cada tool.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_tools.py`:

```python
from ingest import repository as repo
from agent import tools


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_rerank_fn(query, candidatos):
    return list(range(len(candidatos)))


def _armar_tramite_de_prueba(conn):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1"],
        "objetivo": "Objetivo de prueba",
        "descripcion": "Descripción de prueba",
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "problemas_frecuentes": ["Problema 1"],
    }
    chunks = [
        {"tipo_chunk": "descripcion", "texto": "Actas Regulares de Salta", "fuente_url": "https://x"}
    ]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    conn.commit()


def test_buscar_tramite_dedupe_por_tramite_id(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)

    resultados = tools.buscar_tramite(db_conn, _fake_embed_fn, _fake_rerank_fn, "actas")

    assert resultados == [
        {
            "tramite_id": "RC-0001",
            "nombre_oficial": "Actas Regulares",
            "categoria": "Actas",
            "organismo": "Registro Civil",
        }
    ]


def test_obtener_requisitos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_requisitos(db_conn, "RC-0001") == ["DNI"]


def test_obtener_requisitos_tramite_inexistente(db_conn, clean_db):
    assert tools.obtener_requisitos(db_conn, "NO-EXISTE") == []


def test_obtener_costos_modalidad(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_costos_modalidad(db_conn, "RC-0001") == {
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días",
    }


def test_obtener_pasos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_pasos(db_conn, "RC-0001") == ["Paso 1"]


def test_obtener_normativa(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_normativa(db_conn, "RC-0001") == {
        "objetivo": "Objetivo de prueba",
        "descripcion": "Descripción de prueba",
    }


def test_obtener_formularios_enlaces(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_formularios_enlaces(db_conn, "RC-0001") == [
        "https://registrocivilsalta.gob.ar/"
    ]


def test_obtener_problemas_frecuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    assert tools.obtener_problemas_frecuentes(db_conn, "RC-0001") == ["Problema 1"]


def test_ejecutar_tool_despacha_buscar_tramite(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)

    resultado = tools.ejecutar_tool(
        "buscar_tramite", {"query": "actas"}, db_conn, _fake_embed_fn, _fake_rerank_fn
    )

    assert resultado[0]["tramite_id"] == "RC-0001"


def test_ejecutar_tool_despacha_obtener_requisitos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)

    resultado = tools.ejecutar_tool(
        "obtener_requisitos", {"tramite_id": "RC-0001"}, db_conn, _fake_embed_fn, _fake_rerank_fn
    )

    assert resultado == ["DNI"]


def test_tool_schemas_tiene_los_7_nombres_esperados():
    nombres = {schema["function"]["name"] for schema in tools.TOOL_SCHEMAS}
    assert nombres == {
        "buscar_tramite",
        "obtener_requisitos",
        "obtener_costos_modalidad",
        "obtener_pasos",
        "obtener_normativa",
        "obtener_formularios_enlaces",
        "obtener_problemas_frecuentes",
    }
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_tools.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.tools'`

- [ ] **Step 3: Implementar `backend/agent/tools.py`**

```python
from ingest.repository import obtener_snapshot_vigente
from retrieval.hybrid_search import buscar_chunks

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_tramite",
            "description": (
                "Busca trámites relevantes a la pregunta del usuario cuando "
                "todavía no se conoce el ID del trámite específico."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "La consulta o pregunta del usuario en lenguaje natural.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_requisitos",
            "description": "Devuelve los requisitos de un trámite ya identificado por su tramite_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_costos_modalidad",
            "description": "Devuelve el costo, la modalidad y la duración estimada de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_pasos",
            "description": "Devuelve la lista de pasos a seguir para completar un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_normativa",
            "description": "Devuelve el objetivo y la descripción normativa de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_formularios_enlaces",
            "description": "Devuelve los enlaces oficiales (formularios, sitios de gestión) de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_problemas_frecuentes",
            "description": "Devuelve los problemas o advertencias frecuentes de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
]


def buscar_tramite(conn, embed_fn, rerank_fn, query: str) -> list[dict]:
    chunks = buscar_chunks(query, conn, embed_fn, rerank_fn, top_k=5)
    vistos: set[str] = set()
    resultados: list[dict] = []
    for chunk in chunks:
        if chunk["tramite_id"] not in vistos:
            vistos.add(chunk["tramite_id"])
            resultados.append(
                {
                    "tramite_id": chunk["tramite_id"],
                    "nombre_oficial": chunk["nombre_oficial"],
                    "categoria": chunk["categoria"],
                    "organismo": chunk["organismo"],
                }
            )
    return resultados


def obtener_requisitos(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["requisitos"] if snapshot else []


def obtener_costos_modalidad(conn, tramite_id: str) -> dict:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    if snapshot is None:
        return {}
    return {
        "costo": snapshot["costo"],
        "modalidad": snapshot["modalidad"],
        "duracion": snapshot["duracion"],
    }


def obtener_pasos(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["pasos"] if snapshot else []


def obtener_normativa(conn, tramite_id: str) -> dict:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    if snapshot is None:
        return {}
    return {"objetivo": snapshot["objetivo"], "descripcion": snapshot["descripcion"]}


def obtener_formularios_enlaces(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["enlaces_oficiales"] if snapshot else []


def obtener_problemas_frecuentes(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["problemas_frecuentes"] if snapshot else []


def ejecutar_tool(nombre: str, argumentos: dict, conn, embed_fn, rerank_fn):
    if nombre == "buscar_tramite":
        return buscar_tramite(conn, embed_fn, rerank_fn, argumentos["query"])
    if nombre == "obtener_requisitos":
        return obtener_requisitos(conn, argumentos["tramite_id"])
    if nombre == "obtener_costos_modalidad":
        return obtener_costos_modalidad(conn, argumentos["tramite_id"])
    if nombre == "obtener_pasos":
        return obtener_pasos(conn, argumentos["tramite_id"])
    if nombre == "obtener_normativa":
        return obtener_normativa(conn, argumentos["tramite_id"])
    if nombre == "obtener_formularios_enlaces":
        return obtener_formularios_enlaces(conn, argumentos["tramite_id"])
    if nombre == "obtener_problemas_frecuentes":
        return obtener_problemas_frecuentes(conn, argumentos["tramite_id"])
    raise ValueError(f"Tool desconocida: {nombre}")
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_tools.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/tools.py backend/tests/test_tools.py
git commit -m "feat: las 7 herramientas del agente y su despacho por nombre"
```

---

## Task 5: Cliente de chat (`backend/agent/chat_client.py`)

**Files:**
- Create: `backend/agent/chat_client.py`
- Test: `backend/tests/test_chat_client.py`

**Interfaces:**
- Produces: `ChatClient.completar(self, messages: list[dict], tools: list[dict]) -> dict`, que devuelve `{"role": "assistant", "content": str | None, "tool_calls": list[dict] | None}`. Cada elemento de `tool_calls` (cuando no es `None`) tiene la forma exacta de OpenAI: `{"id": str, "type": "function", "function": {"name": str, "arguments": str}}` (con `arguments` como string JSON, sin parsear) — esta es la forma que persiste `sessions.guardar_mensaje` y que va a parsear el orquestador (Task 6) al ejecutar cada tool.
- Produces: `build_real_chat_client() -> ChatClient` (única función que instancia el SDK real de OpenAI para el chat).

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_chat_client.py`:

```python
import json

from agent.chat_client import ChatClient


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, id_, name, arguments):
        self.id = id_
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeChatCompletionResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeCompletions:
    def __init__(self, message):
        self._message = message
        self.last_call = None

    def create(self, model, messages, tools):
        self.last_call = {"model": model, "messages": messages, "tools": tools}
        return _FakeChatCompletionResponse(self._message)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, message):
        self.chat = _FakeChat(_FakeCompletions(message))


def test_completar_devuelve_respuesta_sin_tool_calls():
    fake_sdk = _FakeOpenAISDK(_FakeMessage(content="Hola, ¿en qué te ayudo?"))
    client = ChatClient(fake_sdk)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado == {"role": "assistant", "content": "Hola, ¿en qué te ayudo?", "tool_calls": None}
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_completar_devuelve_tool_calls_normalizados():
    argumentos = json.dumps({"query": "acta"})
    tool_call = _FakeToolCall("call_1", "buscar_tramite", argumentos)
    fake_sdk = _FakeOpenAISDK(_FakeMessage(content=None, tool_calls=[tool_call]))
    client = ChatClient(fake_sdk)

    resultado = client.completar(messages=[{"role": "user", "content": "quiero un acta"}], tools=[])

    assert resultado == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "buscar_tramite", "arguments": argumentos},
            }
        ],
    }
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_chat_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.chat_client'`

- [ ] **Step 3: Implementar `backend/agent/chat_client.py`**

```python
class ChatClient:
    MODEL = "gpt-4o-mini"

    def __init__(self, sdk_client):
        self._sdk_client = sdk_client

    def completar(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._sdk_client.chat.completions.create(
            model=self.MODEL,
            messages=messages,
            tools=tools,
        )
        mensaje = response.choices[0].message

        tool_calls = None
        if mensaje.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in mensaje.tool_calls
            ]

        return {"role": "assistant", "content": mensaje.content, "tool_calls": tool_calls}


def build_real_chat_client() -> ChatClient:
    from openai import OpenAI

    return ChatClient(OpenAI())
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_chat_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/chat_client.py backend/tests/test_chat_client.py
git commit -m "feat: ChatClient para el loop de tool-calling no-streaming"
```

---

## Task 6: Orquestación (`backend/agent/orchestrator.py`)

**Files:**
- Create: `backend/agent/orchestrator.py`
- Test: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `agent.sessions.*` (Task 3), `agent.tools.TOOL_SCHEMAS`/`agent.tools.ejecutar_tool` (Task 4), `ingest.repository.obtener_snapshot_vigente` (Task 2).
- Produces: `orchestrator.procesar_turno(conn, chat_client, embed_fn, rerank_fn, session_id: str, mensaje_usuario: str) -> Iterator[dict]`. `chat_client` tiene la firma de `ChatClient.completar` (Task 5): `.completar(messages, tools) -> dict`. Genera eventos `{"tipo": "texto", "delta": str}` seguidos de un único evento final `{"tipo": "fin", "fuentes": list[dict]}`, donde cada fuente tiene `{"tramite_id", "nombre_oficial", "fuente_url"}`. Esta es la función que va a consumir `backend/agent/api.py` (Task 7) para el endpoint de chat.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_orchestrator.py`:

```python
import uuid

from ingest import repository as repo
from agent import sessions
from agent.orchestrator import procesar_turno


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_rerank_fn(query, candidatos):
    return list(range(len(candidatos)))


class _FakeChatClient:
    def __init__(self, respuestas):
        self._respuestas = respuestas
        self._indice = 0

    def completar(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        return respuesta


def _armar_tramite_de_prueba(conn):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1"],
        "objetivo": "Objetivo",
        "descripcion": "Descripción",
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "problemas_frecuentes": [],
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "Actas Regulares", "fuente_url": "https://x"}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    conn.commit()


def test_procesar_turno_sin_tool_calls(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": "Hola, en qué te ayudo?", "tool_calls": None}]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    texto = "".join(e["delta"] for e in eventos if e["tipo"] == "texto")
    assert texto.strip() == "Hola, en qué te ayudo?"
    assert eventos[-1] == {"tipo": "fin", "fuentes": []}


def test_procesar_turno_con_tool_call_arma_fuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
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
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
                    }
                ],
            },
            {"role": "assistant", "content": "Necesitás tu DNI.", "tool_calls": None},
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    texto = "".join(e["delta"] for e in eventos if e["tipo"] == "texto")
    assert texto.strip() == "Necesitás tu DNI."
    assert eventos[-1] == {
        "tipo": "fin",
        "fuentes": [
            {
                "tramite_id": "RC-0001",
                "nombre_oficial": "Actas Regulares",
                "fuente_url": "https://registrocivilsalta.gob.ar/",
            }
        ],
    }


def test_procesar_turno_persiste_los_mensajes_visibles(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient([{"role": "assistant", "content": "Hola", "tool_calls": None}])

    list(procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola"))
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)
    assert [m["rol"] for m in visibles] == ["user", "assistant"]
    assert [m["contenido"] for m in visibles] == ["hola", "Hola"]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_orchestrator.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.orchestrator'`

- [ ] **Step 3: Implementar `backend/agent/orchestrator.py`**

```python
import json

from agent import sessions
from agent.tools import TOOL_SCHEMAS, ejecutar_tool
from ingest.repository import obtener_snapshot_vigente

SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Hoy tenés información sobre trámites del Registro "
    "Civil. Respondé siempre basándote únicamente en la información que te "
    "devuelven las herramientas disponibles: nunca inventes requisitos, costos, "
    "pasos ni plazos. Si la herramienta buscar_tramite devuelve varios trámites "
    "candidatos y no está claro cuál necesita el usuario, preguntá para "
    "desambiguar antes de usar las demás herramientas. Cuando menciones un "
    "trámite, usá su nombre oficial y, si corresponde, su enlace oficial."
)

MAX_ITERACIONES_TOOLS = 5


def procesar_turno(conn, chat_client, embed_fn, rerank_fn, session_id: str, mensaje_usuario: str):
    sessions.crear_sesion_si_no_existe(conn, session_id)
    historial = sessions.obtener_historial(conn, session_id)

    sessions.guardar_mensaje(conn, session_id, rol="user", contenido=mensaje_usuario)

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + historial
        + [{"role": "user", "content": mensaje_usuario}]
    )

    tramites_citados: set[str] = set()

    for _ in range(MAX_ITERACIONES_TOOLS):
        respuesta = chat_client.completar(messages=messages, tools=TOOL_SCHEMAS)

        if not respuesta["tool_calls"]:
            sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=respuesta["content"])
            yield from _emitir_respuesta_trozeada(respuesta["content"])
            yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
            return

        sessions.guardar_mensaje(
            conn,
            session_id,
            rol="assistant",
            contenido=respuesta["content"],
            tool_calls=respuesta["tool_calls"],
        )
        messages.append(
            {
                "role": "assistant",
                "content": respuesta["content"],
                "tool_calls": respuesta["tool_calls"],
            }
        )

        for tool_call in respuesta["tool_calls"]:
            nombre = tool_call["function"]["name"]
            argumentos = json.loads(tool_call["function"]["arguments"])
            resultado = ejecutar_tool(nombre, argumentos, conn, embed_fn, rerank_fn)

            if nombre == "buscar_tramite":
                tramites_citados.update(candidato["tramite_id"] for candidato in resultado)
            elif "tramite_id" in argumentos:
                tramites_citados.add(argumentos["tramite_id"])

            resultado_json = json.dumps(resultado, ensure_ascii=False)
            sessions.guardar_mensaje(
                conn, session_id, rol="tool", contenido=resultado_json, tool_call_id=tool_call["id"]
            )
            messages.append(
                {"role": "tool", "content": resultado_json, "tool_call_id": tool_call["id"]}
            )

    mensaje_agotado = "No pude resolver tu consulta en este momento. ¿Podés reformularla?"
    sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield from _emitir_respuesta_trozeada(mensaje_agotado)
    yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}


def _emitir_respuesta_trozeada(texto: str):
    for palabra in texto.split(" "):
        yield {"tipo": "texto", "delta": palabra + " "}


def _armar_fuentes(conn, tramites_citados: set[str]) -> list[dict]:
    fuentes = []
    for tramite_id in sorted(tramites_citados):
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            continue
        enlaces = snapshot.get("enlaces_oficiales") or []
        fuentes.append(
            {
                "tramite_id": tramite_id,
                "nombre_oficial": snapshot["nombre_oficial"],
                "fuente_url": enlaces[0] if enlaces else None,
            }
        )
    return fuentes
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_orchestrator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: loop de orquestación con streaming trozeado y fuentes citadas"
```

---

## Task 7: FastAPI (`backend/agent/api.py`)

**Files:**
- Create: `backend/agent/api.py`
- Test: `backend/tests/test_api.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: `db.pool.crear_pool` (Task 1), `agent.chat_client.build_real_chat_client`/`ChatClient` (Task 5), `agent.orchestrator.procesar_turno` (Task 6), `agent.sessions.obtener_mensajes_visibles` (Task 3), `ingest.openai_client.build_real_client` (ya existente, para `generate_embeddings`/`rerank`).
- Produces: `app` (instancia de `FastAPI`), con `POST /chat` (SSE) y `GET /sesiones/{session_id}/mensajes`. Dependencias `obtener_pool`, `obtener_chat_client`, `obtener_openai_client` (decoradas con `@lru_cache`, para poder sobreescribirlas en tests vía `app.dependency_overrides`).

- [ ] **Step 1: Agregar `fastapi`, `uvicorn` y `httpx` a `backend/requirements.txt`**

Contenido final de `backend/requirements.txt`:

```
psycopg[binary]>=3.2,<4
pgvector>=0.3,<0.4
psycopg-pool>=3.2,<4
openai>=1.50,<2
python-dotenv>=1.0,<2
pytest>=8.0,<9
fastapi>=0.115,<1
uvicorn[standard]>=0.32,<1
httpx>=0.27,<1
```

Run: `cd backend && pip install -r requirements.txt`

- [ ] **Step 2: Escribir el test que falla**

Crear `backend/tests/test_api.py`:

```python
import json
import uuid

from fastapi.testclient import TestClient

from agent import api, sessions
from agent.api import obtener_chat_client, obtener_openai_client, obtener_pool


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


class _FakeChatClient:
    def __init__(self, respuestas):
        self._respuestas = respuestas
        self._indice = 0

    def completar(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        return respuesta


class _FakeOpenAIClient:
    def generate_embeddings(self, texts):
        return [[0.0] * 1536 for _ in texts]

    def rerank(self, query, candidatos):
        return list(range(len(candidatos)))


def test_post_chat_devuelve_eventos_sse(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[obtener_chat_client] = lambda: _FakeChatClient(
        [{"role": "assistant", "content": "Hola", "tool_calls": None}]
    )
    api.app.dependency_overrides[obtener_openai_client] = lambda: _FakeOpenAIClient()

    client = TestClient(api.app)
    try:
        respuesta = client.post("/chat", json={"session_id": session_id, "mensaje": "hola"})
        db_conn.commit()
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    lineas = [linea for linea in respuesta.text.split("\n\n") if linea.startswith("data: ")]
    eventos = [json.loads(linea[len("data: ") :]) for linea in lineas]
    assert eventos[-1]["tipo"] == "fin"
    assert "".join(e["delta"] for e in eventos if e["tipo"] == "texto").strip() == "Hola"


def test_get_mensajes_devuelve_historial_visible(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="hola, en qué te ayudo?")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)

    client = TestClient(api.app)
    try:
        respuesta = client.get(f"/sesiones/{session_id}/mensajes")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert [m["rol"] for m in cuerpo] == ["user", "assistant"]
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_api.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.api'`

- [ ] **Step 4: Implementar `backend/agent/api.py`**

```python
import json
import os
from functools import lru_cache
from typing import Iterator

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import sessions
from agent.chat_client import build_real_chat_client
from agent.orchestrator import procesar_turno
from db.pool import crear_pool
from ingest.openai_client import build_real_client

app = FastAPI()


@lru_cache
def obtener_pool():
    return crear_pool(os.environ["DATABASE_URL"])


@lru_cache
def obtener_chat_client():
    return build_real_chat_client()


@lru_cache
def obtener_openai_client():
    return build_real_client()


class ChatRequest(BaseModel):
    session_id: str
    mensaje: str


@app.post("/chat")
def chat(
    request: ChatRequest,
    pool=Depends(obtener_pool),
    chat_client=Depends(obtener_chat_client),
    openai_client=Depends(obtener_openai_client),
):
    def generar() -> Iterator[str]:
        with pool.connection() as conn:
            for evento in procesar_turno(
                conn,
                chat_client,
                openai_client.generate_embeddings,
                openai_client.rerank,
                request.session_id,
                request.mensaje,
            ):
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
            conn.commit()

    return StreamingResponse(generar(), media_type="text/event-stream")


@app.get("/sesiones/{session_id}/mensajes")
def obtener_mensajes(session_id: str, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return sessions.obtener_mensajes_visibles(conn, session_id)
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_api.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Correr toda la suite del backend para confirmar que no hay regresiones**

Run: `cd backend && pytest -v`
Expected: todos los tests pasan (núcleo de datos + motor de recuperación + agente conversacional), salida sin warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/agent/api.py backend/tests/test_api.py backend/requirements.txt
git commit -m "feat: FastAPI con endpoint de chat (SSE) y endpoint de historial"
```

---

## Self-Review

**Cobertura del spec:**
- Tablas `sesiones`/`mensajes` con `sesiones.id` como UUID del cliente → Task 1.
- Pool de conexiones con `register_vector` resolviendo la precondición implícita heredada del motor de recuperación → Task 1.
- `obtener_snapshot_vigente` para leer datos estructurados de un trámite ya identificado → Task 2.
- Las 7 herramientas con sus esquemas de function-calling → Task 4.
- `ChatClient` con `gpt-4o-mini`, no-streaming → Task 5.
- Loop de tool-calling con máximo 5 iteraciones, persistencia completa del historial, respuesta final trozeada (no streaming real, sin duplicar costo) → Task 6.
- Fuentes citadas (`tramite_id`, `nombre_oficial`, `fuente_url`) al final de cada turno → Task 6.
- `POST /chat` (SSE) y `GET /sesiones/{id}/mensajes` → Task 7.
- Ningún test hace red real a OpenAI → verificado en Tasks 4 (fakes de embed/rerank), 5 (fake SDK), 6 y 7 (fake `ChatClient`/`OpenAIClient`).
- Criterio de aceptación de continuidad conversacional (una sesión recuerda el trámite identificado en el turno anterior) → cubierto por el diseño de `obtener_historial`/`procesar_turno` (Task 3 + Task 6); la verificación con datos y modelo reales queda como paso manual, igual que en los subsistemas anteriores.

**Placeholders:** ninguno — todos los pasos incluyen código completo y comandos exactos.

**Consistencia de tipos:** la forma de `tool_calls` (`{"id", "type", "function": {"name", "arguments"}}`, con `arguments` como string JSON) es idéntica en `ChatClient.completar` (Task 5), `sessions.guardar_mensaje`/`obtener_historial` (Task 3) y el loop de `orchestrator.procesar_turno` (Task 6) — se persiste y se relee sin transformación, y solo se parsea puntualmente con `json.loads` en el momento de ejecutar cada tool. `chat_client` se pasa como parámetro con la misma firma (`.completar(messages, tools) -> dict`) desde `orchestrator.procesar_turno` (Task 6) hasta `agent.api` (Task 7), donde la dependencia real es `ChatClient` (Task 5) y el fake de test replica exactamente esa interfaz.
