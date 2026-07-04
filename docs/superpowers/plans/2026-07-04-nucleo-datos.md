# Núcleo de Datos (Macacha) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el esquema Postgres+pgvector con versionado de trámites y el pipeline de ingesta que transforma el JSON fuente de trámites en objetos enriquecidos con embeddings, listos para ser consultados por el motor de recuperación (subsistema siguiente).

**Architecture:** Postgres (imagen `pgvector/pgvector:pg16` vía Docker Compose) con 4 tablas (`organismos`, `tramites`, `tramite_versiones`, `tramite_chunks`) siguiendo un patrón de versionado tipo slowly-changing-dimension: cada cambio de contenido cierra la versión vigente anterior y crea una nueva, sin tocar el historial. Un pipeline de ingesta en Python (sin ORM, SQL directo vía `psycopg3`) parsea el JSON, arma el "snapshot" enriquecido, detecta cambios por hash de contenido, genera embeddings vía OpenAI y persiste todo en una transacción por trámite.

**Tech Stack:** Python 3.11+, `psycopg[binary]` 3.x, `pgvector` (adaptador Python), OpenAI SDK (`text-embedding-3-small` para embeddings, `gpt-4o-mini` para generación de FAQs faltantes), `python-dotenv`, `pytest`, Docker Compose con `pgvector/pgvector:pg16`.

## Global Constraints

- Postgres 16 con extensión `vector` (imagen `pgvector/pgvector:pg16`).
- Sin ORM: acceso a datos vía SQL directo con `psycopg3`.
- Embeddings con `text-embedding-3-small` (1536 dimensiones). FAQs auto-generadas con `gpt-4o-mini`.
- `OPENAI_API_KEY`, `DATABASE_URL` y `TEST_DATABASE_URL` se leen de variables de entorno (`.env`, nunca hardcodeadas ni commiteadas). Se provee `.env.example` como referencia.
- Solo entorno local/dev por ahora (Docker Compose). Sin configuración de despliegue a producción, sin CI/CD, sin autenticación de usuarios.
- Nombres de dominio (trámite, requisitos, vigente, organismo, etc.) en español, siguiendo el vocabulario del spec; nombres técnicos genéricos (get, build, fake, etc.) en inglés cuando corresponda al idioma habitual del código Python.
- Todo el trabajo vive bajo `backend/` dentro del repo `macacha`.

---

## Task 1: Scaffolding del proyecto (Docker Compose, esquema SQL, conexión)

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `backend/db/__init__.py`
- Create: `backend/db/schema.sql`
- Create: `backend/db/init_test_db.sql`
- Create: `backend/db/connection.py`
- Create: `backend/ingest/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_schema_smoke.py`

**Interfaces:**
- Produces: `db.connection.get_connection() -> psycopg.Connection` (usa `DATABASE_URL`, registra el tipo `vector`).
- Produces: fixtures de pytest `db_conn` (conexión abierta contra `TEST_DATABASE_URL`) y `clean_db` (limpia las tablas de trámites antes/después de cada test), disponibles para todas las tareas siguientes.

- [ ] **Step 1: Crear `docker-compose.yml`**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: macacha
      POSTGRES_PASSWORD: macacha
      POSTGRES_DB: macacha
    ports:
      - "5432:5432"
    volumes:
      - macacha_pgdata:/var/lib/postgresql/data
      - ./backend/db/schema.sql:/docker-entrypoint-initdb.d/10-schema.sql
      - ./backend/db/init_test_db.sql:/docker-entrypoint-initdb.d/20-test-db.sql

volumes:
  macacha_pgdata:
```

- [ ] **Step 2: Crear `.env.example`**

```
DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha
TEST_DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha_test
OPENAI_API_KEY=sk-your-key-here
```

- [ ] **Step 3: Crear `backend/db/schema.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS organismos (
    id SERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS tramites (
    id TEXT PRIMARY KEY,
    organismo_id INTEGER NOT NULL REFERENCES organismos(id),
    categoria TEXT NOT NULL,
    nombre_oficial TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tramite_versiones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tramite_id TEXT NOT NULL REFERENCES tramites(id),
    numero_version INTEGER NOT NULL,
    es_vigente BOOLEAN NOT NULL DEFAULT true,
    vigente_desde TIMESTAMPTZ NOT NULL DEFAULT now(),
    vigente_hasta TIMESTAMPTZ,
    content_hash TEXT NOT NULL,
    snapshot JSONB NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS tramite_versiones_vigente_unica
    ON tramite_versiones (tramite_id)
    WHERE es_vigente = true;

CREATE TABLE IF NOT EXISTS tramite_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES tramite_versiones(id),
    tipo_chunk TEXT NOT NULL,
    texto TEXT NOT NULL,
    fuente_url TEXT,
    embedding vector(1536),
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED
);

CREATE INDEX IF NOT EXISTS tramite_chunks_version_idx ON tramite_chunks (version_id);
CREATE INDEX IF NOT EXISTS tramite_chunks_tsv_idx ON tramite_chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS tramite_chunks_embedding_idx ON tramite_chunks
    USING hnsw (embedding vector_cosine_ops);
```

- [ ] **Step 4: Crear `backend/db/init_test_db.sql`**

```sql
CREATE DATABASE macacha_test;
\connect macacha_test
\i /docker-entrypoint-initdb.d/10-schema.sql
```

- [ ] **Step 5: Crear `backend/requirements.txt`**

```
psycopg[binary]>=3.2,<4
pgvector>=0.3,<0.4
openai>=1.50,<2
python-dotenv>=1.0,<2
pytest>=8.0,<9
```

- [ ] **Step 6: Crear `backend/pyproject.toml`**

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 7: Crear `backend/db/__init__.py` y `backend/ingest/__init__.py` y `backend/tests/__init__.py` (vacíos)**

```python
```

- [ ] **Step 8: Crear `backend/db/connection.py`**

```python
import os

import psycopg
from pgvector.psycopg import register_vector


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn
```

- [ ] **Step 9: Crear `backend/tests/conftest.py`**

```python
import os

import psycopg
import pytest
from pgvector.psycopg import register_vector


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://macacha:macacha@localhost:5432/macacha_test",
    )


@pytest.fixture
def db_conn():
    conn = psycopg.connect(_test_database_url())
    register_vector(conn)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def clean_db():
    conn = psycopg.connect(_test_database_url(), autocommit=True)

    def _clean() -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tramite_chunks")
            cur.execute("DELETE FROM tramite_versiones")
            cur.execute("DELETE FROM tramites")
            cur.execute("DELETE FROM organismos")

    _clean()
    yield
    _clean()
    conn.close()
```

- [ ] **Step 10: Escribir el test de humo (falla porque todavía no levantamos la base)**

Crear `backend/tests/test_schema_smoke.py`:

```python
import os

import psycopg


def test_extension_and_tables_exist():
    conn = psycopg.connect(
        os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://macacha:macacha@localhost:5432/macacha_test",
        )
    )
    with conn.cursor() as cur:
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
        assert {"organismos", "tramites", "tramite_versiones", "tramite_chunks"} <= tables
    conn.close()
```

- [ ] **Step 11: Correr el test y verificar que falla**

Run: `cd backend && pip install -r requirements.txt && pytest tests/test_schema_smoke.py -v`
Expected: FAIL con error de conexión (`could not connect to server` / `Connection refused`), porque Postgres todavía no está levantado.

- [ ] **Step 12: Levantar Docker Compose**

Run: `docker compose up -d postgres`
Run: `until docker compose exec -T postgres pg_isready -U macacha; do sleep 1; done`
Expected: `postgres:5432 - accepting connections`

- [ ] **Step 13: Correr el test de nuevo y verificar que pasa**

Run: `cd backend && pytest tests/test_schema_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 14: Commit**

```bash
git add docker-compose.yml .env.example backend/requirements.txt backend/pyproject.toml \
  backend/db backend/ingest/__init__.py backend/tests
git commit -m "feat: scaffolding de Docker Compose, esquema Postgres+pgvector y conexión"
```

---

## Task 2: Hash de contenido para detectar cambios

**Files:**
- Create: `backend/ingest/hashing.py`
- Test: `backend/tests/test_hashing.py`

**Interfaces:**
- Produces: `hashing.compute_content_hash(snapshot: dict) -> str`

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_hashing.py`:

```python
from ingest.hashing import compute_content_hash


def test_same_content_different_key_order_produces_same_hash():
    snapshot_a = {"id": "RC-0001", "costo": "$6000"}
    snapshot_b = {"costo": "$6000", "id": "RC-0001"}

    assert compute_content_hash(snapshot_a) == compute_content_hash(snapshot_b)


def test_different_content_produces_different_hash():
    snapshot_a = {"id": "RC-0001", "costo": "$6000"}
    snapshot_b = {"id": "RC-0001", "costo": "$7000"}

    assert compute_content_hash(snapshot_a) != compute_content_hash(snapshot_b)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_hashing.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.hashing'`

- [ ] **Step 3: Implementar `backend/ingest/hashing.py`**

```python
import hashlib
import json


def compute_content_hash(snapshot: dict) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_hashing.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/hashing.py backend/tests/test_hashing.py
git commit -m "feat: hash de contenido determinístico para detectar cambios de versión"
```

---

## Task 3: Extracción de enlaces oficiales

**Files:**
- Create: `backend/ingest/link_extractor.py`
- Test: `backend/tests/test_link_extractor.py`

**Interfaces:**
- Produces: `link_extractor.extract_official_links(pasos: list[str], chunks: list[dict]) -> list[str]`

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_link_extractor.py`:

```python
from ingest.link_extractor import extract_official_links


def test_extracts_and_dedupes_urls_from_pasos_and_chunks():
    pasos = [
        "Ingresar a https://registrocivilsalta.gob.ar/",
        "Crear cuenta en https://registrocivilsalta.gob.ar/intro/login.php",
        "Pagar con Macroclick (QR, crédito o débito) o Mercado Pago.",
    ]
    chunks = [
        {
            "chunk_id": "RC-0001-CH-01",
            "texto": "texto",
            "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
        },
        {
            "chunk_id": "RC-0001-CH-02",
            "texto": "texto",
            "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
        },
    ]

    resultado = extract_official_links(pasos, chunks)

    assert resultado == [
        "https://registrocivilsalta.gob.ar/",
        "https://registrocivilsalta.gob.ar/intro/login.php",
        "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    ]


def test_returns_empty_list_when_no_urls():
    assert extract_official_links(["Sin URLs acá."], []) == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_link_extractor.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.link_extractor'`

- [ ] **Step 3: Implementar `backend/ingest/link_extractor.py`**

```python
import re

URL_PATTERN = re.compile(r"https?://[^\s)'\"]+")


def extract_official_links(pasos: list[str], chunks: list[dict]) -> list[str]:
    encontradas: list[str] = []

    for texto in pasos:
        encontradas.extend(URL_PATTERN.findall(texto))

    for chunk in chunks:
        fuente = chunk.get("fuente")
        if fuente:
            encontradas.append(fuente)

    vistas: set[str] = set()
    deduplicadas: list[str] = []
    for url in encontradas:
        url = url.rstrip(".,;")
        if url not in vistas:
            vistas.add(url)
            deduplicadas.append(url)

    return deduplicadas
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_link_extractor.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/link_extractor.py backend/tests/test_link_extractor.py
git commit -m "feat: extracción y deduplicación de enlaces oficiales"
```

---

## Task 4: Cliente OpenAI (embeddings + generación de FAQs)

**Files:**
- Create: `backend/ingest/openai_client.py`
- Test: `backend/tests/test_openai_client.py`

**Interfaces:**
- Produces: `openai_client.OpenAIClient` con métodos `generate_embeddings(self, texts: list[str]) -> list[list[float]]` y `generate_faqs(self, nombre_oficial: str, descripcion: str, requisitos: list[str], pasos: list[str]) -> list[dict]`
- Produces: `openai_client.build_real_client() -> OpenAIClient` (crea el cliente real de OpenAI; usado únicamente en `ingest/load.py`)

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_openai_client.py`:

```python
import json

from ingest.openai_client import OpenAIClient


class _FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [_FakeEmbeddingItem(v) for v in vectors]


class _FakeEmbeddings:
    def __init__(self, vectors):
        self._vectors = vectors
        self.last_call = None

    def create(self, model, input):
        self.last_call = {"model": model, "input": input}
        return _FakeEmbeddingResponse(self._vectors)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeChatCompletionResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content):
        self._content = content
        self.last_call = None

    def create(self, model, messages, response_format):
        self.last_call = {"model": model, "messages": messages, "response_format": response_format}
        return _FakeChatCompletionResponse(self._content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, vectors, faq_json_content):
        self.embeddings = _FakeEmbeddings(vectors)
        self.chat = _FakeChat(_FakeCompletions(faq_json_content))


def test_generate_embeddings_calls_api_and_returns_vectors():
    fake_sdk = _FakeOpenAISDK(vectors=[[0.1, 0.2], [0.3, 0.4]], faq_json_content="{}")
    client = OpenAIClient(fake_sdk)

    resultado = client.generate_embeddings(["texto 1", "texto 2"])

    assert resultado == [[0.1, 0.2], [0.3, 0.4]]
    assert fake_sdk.embeddings.last_call == {
        "model": "text-embedding-3-small",
        "input": ["texto 1", "texto 2"],
    }


def test_generate_faqs_parses_json_response():
    faq_json = json.dumps(
        {
            "faqs": [
                {"pregunta": "¿Cómo hago el trámite?", "respuesta": "Online."},
                {"pregunta": "¿Cuánto cuesta?", "respuesta": "$6000."},
            ]
        }
    )
    fake_sdk = _FakeOpenAISDK(vectors=[], faq_json_content=faq_json)
    client = OpenAIClient(fake_sdk)

    resultado = client.generate_faqs(
        nombre_oficial="Actas Regulares",
        descripcion="Descripción de prueba",
        requisitos=["DNI"],
        pasos=["Paso 1"],
    )

    assert resultado == [
        {"pregunta": "¿Cómo hago el trámite?", "respuesta": "Online."},
        {"pregunta": "¿Cuánto cuesta?", "respuesta": "$6000."},
    ]
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_openai_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.openai_client'`

- [ ] **Step 3: Implementar `backend/ingest/openai_client.py`**

```python
import json


class OpenAIClient:
    EMBEDDING_MODEL = "text-embedding-3-small"
    FAQ_MODEL = "gpt-4o-mini"

    def __init__(self, sdk_client):
        self._sdk_client = sdk_client

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        response = self._sdk_client.embeddings.create(
            model=self.EMBEDDING_MODEL, input=texts
        )
        return [item.embedding for item in response.data]

    def generate_faqs(
        self,
        nombre_oficial: str,
        descripcion: str,
        requisitos: list[str],
        pasos: list[str],
    ) -> list[dict]:
        prompt = (
            "Generá entre 2 y 3 preguntas frecuentes con sus respuestas para el "
            "siguiente trámite de la administración pública de Salta.\n\n"
            f"Nombre: {nombre_oficial}\n"
            f"Descripción: {descripcion}\n"
            f"Requisitos: {'; '.join(requisitos)}\n"
            f"Pasos: {'; '.join(pasos)}\n\n"
            'Respondé únicamente con JSON con esta forma: '
            '{"faqs": [{"pregunta": "...", "respuesta": "..."}]}'
        )
        response = self._sdk_client.chat.completions.create(
            model=self.FAQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return data["faqs"]


def build_real_client() -> OpenAIClient:
    from openai import OpenAI

    return OpenAIClient(OpenAI())
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_openai_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: cliente OpenAI para embeddings y generación de FAQs"
```

---

## Task 5: Construcción del snapshot enriquecido

**Files:**
- Create: `backend/ingest/snapshot_builder.py`
- Test: `backend/tests/test_snapshot_builder.py`

**Interfaces:**
- Consumes: `link_extractor.extract_official_links(pasos, chunks)` (Task 3)
- Produces: `snapshot_builder.build_snapshot(raw_tramite: dict, faq_generator) -> dict`, donde `faq_generator` es un callable con la firma `faq_generator(nombre_oficial, descripcion, requisitos, pasos) -> list[dict]` (coincide con `OpenAIClient.generate_faqs`).

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_snapshot_builder.py`:

```python
from ingest.snapshot_builder import build_snapshot


def _raw_tramite(**overrides):
    base = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "tramite": "Actas Regulares",
        "descripcion": "Descripción de prueba",
        "objetivo": "Objetivo de prueba",
        "sinonimos": ["partida"],
        "keywords": ["actas"],
        "requisitos": ["DNI"],
        "pasos": ["Ingresar a https://registrocivilsalta.gob.ar/"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días hábiles",
        "problemas_frecuentes": ["Datos incompletos"],
        "preguntas_frecuentes": [{"pregunta": "¿Cómo?", "respuesta": "Online"}],
        "chunks": [
            {
                "chunk_id": "RC-0001-CH-01",
                "texto": "Descripción de prueba",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            }
        ],
    }
    base.update(overrides)
    return base


def _faq_generator_no_debe_llamarse(**kwargs):
    raise AssertionError("no debería generarse FAQs si el trámite ya trae")


def test_keeps_existing_faqs_and_marks_not_auto_generated():
    snapshot = build_snapshot(_raw_tramite(), _faq_generator_no_debe_llamarse)

    assert snapshot["id"] == "RC-0001"
    assert snapshot["nombre_oficial"] == "Actas Regulares"
    assert snapshot["preguntas_frecuentes"] == [{"pregunta": "¿Cómo?", "respuesta": "Online"}]
    assert snapshot["faq_generadas_automaticamente"] is False
    assert snapshot["enlaces_oficiales"] == [
        "https://registrocivilsalta.gob.ar/",
        "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    ]


def test_generates_faqs_when_missing():
    llamadas = []

    def faq_generator(**kwargs):
        llamadas.append(kwargs)
        return [{"pregunta": "¿Qué es?", "respuesta": "Un trámite"}]

    raw = _raw_tramite(preguntas_frecuentes=[])
    snapshot = build_snapshot(raw, faq_generator)

    assert snapshot["preguntas_frecuentes"] == [{"pregunta": "¿Qué es?", "respuesta": "Un trámite"}]
    assert snapshot["faq_generadas_automaticamente"] is True
    assert llamadas == [
        {
            "nombre_oficial": "Actas Regulares",
            "descripcion": "Descripción de prueba",
            "requisitos": ["DNI"],
            "pasos": ["Ingresar a https://registrocivilsalta.gob.ar/"],
        }
    ]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_snapshot_builder.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.snapshot_builder'`

- [ ] **Step 3: Implementar `backend/ingest/snapshot_builder.py`**

```python
from ingest.link_extractor import extract_official_links


def build_snapshot(raw_tramite: dict, faq_generator) -> dict:
    preguntas_frecuentes = raw_tramite.get("preguntas_frecuentes") or []
    faq_generadas_automaticamente = False

    if not preguntas_frecuentes:
        preguntas_frecuentes = faq_generator(
            nombre_oficial=raw_tramite["tramite"],
            descripcion=raw_tramite.get("descripcion", ""),
            requisitos=raw_tramite.get("requisitos", []),
            pasos=raw_tramite.get("pasos", []),
        )
        faq_generadas_automaticamente = True

    enlaces_oficiales = extract_official_links(
        raw_tramite.get("pasos", []), raw_tramite.get("chunks", [])
    )

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
        "problemas_frecuentes": raw_tramite.get("problemas_frecuentes", []),
        "preguntas_frecuentes": preguntas_frecuentes,
        "enlaces_oficiales": enlaces_oficiales,
        "faq_generadas_automaticamente": faq_generadas_automaticamente,
    }
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_snapshot_builder.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/snapshot_builder.py backend/tests/test_snapshot_builder.py
git commit -m "feat: construcción del snapshot enriquecido con FAQs y enlaces oficiales"
```

---

## Task 6: Construcción de chunks para embeddings

**Files:**
- Create: `backend/ingest/chunk_builder.py`
- Test: `backend/tests/test_chunk_builder.py`

**Interfaces:**
- Consumes: el `snapshot` producido por `snapshot_builder.build_snapshot` (Task 5), específicamente `snapshot["preguntas_frecuentes"]` y `snapshot["enlaces_oficiales"]`.
- Produces: `chunk_builder.build_chunks(raw_tramite: dict, snapshot: dict) -> list[dict]`, donde cada chunk es `{"tipo_chunk": str, "texto": str, "fuente_url": str | None}`.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_chunk_builder.py`:

```python
from ingest.chunk_builder import build_chunks


def test_infers_tipo_chunk_from_source_chunks_and_appends_faq_and_links():
    raw_tramite = {
        "chunks": [
            {
                "chunk_id": "RC-0001-CH-01",
                "texto": "Actas Regulares. Trámite del Registro Civil de Salta.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-02",
                "texto": "Requisitos para Actas Regulares: Nombre, apellido, DNI.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-03",
                "texto": "Pasos para Actas Regulares: Ingresar al sitio.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-04",
                "texto": "Costo, duración y modalidad de Actas Regulares: costo $6000.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
            {
                "chunk_id": "RC-0001-CH-05",
                "texto": "Problemas frecuentes de Actas Regulares: datos incompletos.",
                "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
            },
        ]
    }
    snapshot = {
        "preguntas_frecuentes": [{"pregunta": "¿Cómo hago el trámite?", "respuesta": "Online."}],
        "enlaces_oficiales": [
            "https://registrocivilsalta.gob.ar/",
            "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
        ],
    }

    chunks = build_chunks(raw_tramite, snapshot)

    tipos = [c["tipo_chunk"] for c in chunks]
    assert tipos == [
        "descripcion",
        "requisitos",
        "pasos",
        "costo_modalidad",
        "problemas_frecuentes",
        "faq",
        "enlaces_oficiales",
    ]
    assert chunks[-2] == {
        "tipo_chunk": "faq",
        "texto": "¿Cómo hago el trámite? Online.",
        "fuente_url": None,
    }
    assert chunks[-1]["tipo_chunk"] == "enlaces_oficiales"
    assert "https://registrocivilsalta.gob.ar/" in chunks[-1]["texto"]


def test_omits_enlaces_chunk_when_no_links():
    raw_tramite = {"chunks": []}
    snapshot = {"preguntas_frecuentes": [], "enlaces_oficiales": []}

    chunks = build_chunks(raw_tramite, snapshot)

    assert chunks == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_chunk_builder.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.chunk_builder'`

- [ ] **Step 3: Implementar `backend/ingest/chunk_builder.py`**

```python
_PREFIJOS_TIPO = [
    ("Requisitos para", "requisitos"),
    ("Pasos para", "pasos"),
    ("Costo, duración y modalidad de", "costo_modalidad"),
    ("Problemas frecuentes de", "problemas_frecuentes"),
]


def _inferir_tipo_chunk(texto: str) -> str:
    for prefijo, tipo in _PREFIJOS_TIPO:
        if texto.startswith(prefijo):
            return tipo
    return "descripcion"


def build_chunks(raw_tramite: dict, snapshot: dict) -> list[dict]:
    chunks: list[dict] = []

    for chunk_original in raw_tramite.get("chunks", []):
        chunks.append(
            {
                "tipo_chunk": _inferir_tipo_chunk(chunk_original["texto"]),
                "texto": chunk_original["texto"],
                "fuente_url": chunk_original.get("fuente"),
            }
        )

    for faq in snapshot["preguntas_frecuentes"]:
        chunks.append(
            {
                "tipo_chunk": "faq",
                "texto": f"{faq['pregunta']} {faq['respuesta']}",
                "fuente_url": None,
            }
        )

    if snapshot["enlaces_oficiales"]:
        chunks.append(
            {
                "tipo_chunk": "enlaces_oficiales",
                "texto": "Enlaces oficiales: " + ", ".join(snapshot["enlaces_oficiales"]),
                "fuente_url": snapshot["enlaces_oficiales"][0],
            }
        )

    return chunks
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_chunk_builder.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/chunk_builder.py backend/tests/test_chunk_builder.py
git commit -m "feat: construcción de chunks tipados a partir del trámite y su snapshot"
```

---

## Task 7: Capa de acceso a datos (repository)

**Files:**
- Create: `backend/ingest/repository.py`
- Test: `backend/tests/test_repository.py`

**Interfaces:**
- Consumes: fixtures `db_conn` y `clean_db` de `backend/tests/conftest.py` (Task 1).
- Produces:
  - `repository.upsert_organismo(conn, nombre: str) -> int`
  - `repository.upsert_tramite(conn, tramite_id: str, organismo_id: int, categoria: str, nombre_oficial: str) -> None`
  - `repository.get_vigente_version(conn, tramite_id: str) -> dict | None` (con claves `id: uuid.UUID`, `numero_version: int`, `content_hash: str`)
  - `repository.close_version(conn, version_id) -> None`
  - `repository.insert_version_with_chunks(conn, tramite_id: str, numero_version: int, content_hash: str, snapshot: dict, chunks: list[dict], embeddings: list[list[float]]) -> str` (devuelve el `version_id` como string)

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_repository.py`:

```python
import uuid

from ingest import repository as repo


def test_upsert_organismo_returns_same_id_on_conflict(db_conn, clean_db):
    id1 = repo.upsert_organismo(db_conn, "Registro Civil")
    id2 = repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    assert id1 == id2


def test_get_vigente_version_is_none_without_versions(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    db_conn.commit()

    assert repo.get_vigente_version(db_conn, "RC-0001") is None


def test_insert_version_with_chunks_and_read_it_back(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [{"tipo_chunk": "descripcion", "texto": "texto de prueba", "fuente_url": None}]
    embeddings = [[0.1] * 1536]

    version_id = repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    assert vigente == {"id": uuid.UUID(version_id), "numero_version": 1, "content_hash": "hash-1"}


def test_close_version_marks_it_as_no_longer_vigente(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.1] * 1536]
    version_id = repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    repo.close_version(db_conn, version_id)
    db_conn.commit()

    assert repo.get_vigente_version(db_conn, "RC-0001") is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_repository.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.repository'`

- [ ] **Step 3: Implementar `backend/ingest/repository.py`**

```python
import json
import uuid


def upsert_organismo(conn, nombre: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO organismos (nombre) VALUES (%s)
            ON CONFLICT (nombre) DO UPDATE SET nombre = EXCLUDED.nombre
            RETURNING id
            """,
            (nombre,),
        )
        return cur.fetchone()[0]


def upsert_tramite(
    conn, tramite_id: str, organismo_id: int, categoria: str, nombre_oficial: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET organismo_id = EXCLUDED.organismo_id,
                    categoria = EXCLUDED.categoria,
                    nombre_oficial = EXCLUDED.nombre_oficial
            """,
            (tramite_id, organismo_id, categoria, nombre_oficial),
        )


def get_vigente_version(conn, tramite_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, numero_version, content_hash
            FROM tramite_versiones
            WHERE tramite_id = %s AND es_vigente = true
            """,
            (tramite_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"id": row[0], "numero_version": row[1], "content_hash": row[2]}


def close_version(conn, version_id) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tramite_versiones
            SET es_vigente = false, vigente_hasta = now()
            WHERE id = %s
            """,
            (version_id,),
        )


def insert_version_with_chunks(
    conn,
    tramite_id: str,
    numero_version: int,
    content_hash: str,
    snapshot: dict,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> str:
    version_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tramite_versiones
                (id, tramite_id, numero_version, es_vigente, content_hash, snapshot)
            VALUES (%s, %s, %s, true, %s, %s)
            """,
            (
                version_id,
                tramite_id,
                numero_version,
                content_hash,
                json.dumps(snapshot, ensure_ascii=False),
            ),
        )
        for chunk, embedding in zip(chunks, embeddings):
            cur.execute(
                """
                INSERT INTO tramite_chunks (version_id, tipo_chunk, texto, fuente_url, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (version_id, chunk["tipo_chunk"], chunk["texto"], chunk["fuente_url"], embedding),
            )
    return str(version_id)
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_repository.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/repository.py backend/tests/test_repository.py
git commit -m "feat: capa de acceso a datos para trámites, versiones y chunks"
```

---

## Task 8: Orquestación de la ingesta (loader)

**Files:**
- Create: `backend/ingest/loader.py`
- Test: `backend/tests/test_loader.py`

**Interfaces:**
- Consumes: `hashing.compute_content_hash` (Task 2), `snapshot_builder.build_snapshot` (Task 5), `chunk_builder.build_chunks` (Task 6), `repository.*` (Task 7).
- Produces:
  - `loader.ingest_tramite(raw_tramite: dict, conn, embed_fn, faq_fn) -> str` — devuelve `"nuevo"`, `"sin_cambios"` o `"nueva_version"`. **No** commitea la transacción (queda a cargo del llamador).
  - `loader.ingest_file(path: str, conn, embed_fn, faq_fn) -> dict` — devuelve `{"nuevos": int, "sin_cambios": int, "nueva_version": int}`. Commitea después de cada trámite.
  - `embed_fn` tiene la firma de `OpenAIClient.generate_embeddings` (Task 4); `faq_fn` tiene la firma de `OpenAIClient.generate_faqs` (Task 4).

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_loader.py`:

```python
import json

from ingest.loader import ingest_file, ingest_tramite


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_faq_fn(nombre_oficial, descripcion, requisitos, pasos):
    return [{"pregunta": f"¿Qué es {nombre_oficial}?", "respuesta": descripcion}]


def _raw_tramite(**overrides):
    base = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "tramite": "Actas Regulares",
        "descripcion": "Descripción de prueba",
        "objetivo": "Objetivo de prueba",
        "sinonimos": [],
        "keywords": [],
        "requisitos": ["DNI"],
        "pasos": ["Paso 1"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días hábiles",
        "problemas_frecuentes": [],
        "preguntas_frecuentes": [{"pregunta": "p", "respuesta": "r"}],
        "chunks": [{"chunk_id": "CH-01", "texto": "Descripción de prueba", "fuente": "https://x"}],
    }
    base.update(overrides)
    return base


def test_ingest_tramite_creates_first_version(db_conn, clean_db):
    estado = ingest_tramite(_raw_tramite(), db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    assert estado == "nuevo"


def test_ingest_tramite_skips_when_unchanged(db_conn, clean_db):
    raw = _raw_tramite()

    primero = ingest_tramite(raw, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()
    segundo = ingest_tramite(raw, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    assert primero == "nuevo"
    assert segundo == "sin_cambios"


def test_ingest_tramite_creates_new_version_when_content_changes(db_conn, clean_db):
    raw = _raw_tramite()
    ingest_tramite(raw, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    raw_modificado = _raw_tramite(costo="$7000")
    estado = ingest_tramite(raw_modificado, db_conn, _fake_embed_fn, _fake_faq_fn)
    db_conn.commit()

    assert estado == "nueva_version"


def test_ingest_tramite_generates_faqs_when_missing(db_conn, clean_db):
    llamadas = []

    def faq_fn_espia(**kwargs):
        llamadas.append(kwargs)
        return _fake_faq_fn(**kwargs)

    raw = _raw_tramite(id="RC-0002", preguntas_frecuentes=[])
    ingest_tramite(raw, db_conn, _fake_embed_fn, faq_fn_espia)
    db_conn.commit()

    assert len(llamadas) == 1


def test_ingest_file_returns_summary_counts(tmp_path, db_conn, clean_db):
    raw_tramites = [
        _raw_tramite(),
        _raw_tramite(id="RC-0002", tramite="Actas Exprés", preguntas_frecuentes=[]),
    ]
    archivo = tmp_path / "sample.json"
    archivo.write_text(json.dumps(raw_tramites), encoding="utf-8")

    resumen = ingest_file(str(archivo), db_conn, _fake_embed_fn, _fake_faq_fn)

    assert resumen == {"nuevos": 2, "sin_cambios": 0, "nueva_version": 0}
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_loader.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.loader'`

- [ ] **Step 3: Implementar `backend/ingest/loader.py`**

```python
import json

from ingest import repository as repo
from ingest.chunk_builder import build_chunks
from ingest.hashing import compute_content_hash
from ingest.snapshot_builder import build_snapshot


def ingest_tramite(raw_tramite: dict, conn, embed_fn, faq_fn) -> str:
    snapshot = build_snapshot(raw_tramite, faq_fn)
    content_hash = compute_content_hash(snapshot)

    organismo_id = repo.upsert_organismo(conn, snapshot["organismo"])
    repo.upsert_tramite(
        conn, snapshot["id"], organismo_id, snapshot["categoria"], snapshot["nombre_oficial"]
    )

    vigente = repo.get_vigente_version(conn, snapshot["id"])

    if vigente is not None and vigente["content_hash"] == content_hash:
        return "sin_cambios"

    numero_version = 1 if vigente is None else vigente["numero_version"] + 1
    if vigente is not None:
        repo.close_version(conn, vigente["id"])

    chunks = build_chunks(raw_tramite, snapshot)
    embeddings = embed_fn([c["texto"] for c in chunks])
    repo.insert_version_with_chunks(
        conn, snapshot["id"], numero_version, content_hash, snapshot, chunks, embeddings
    )

    return "nuevo" if vigente is None else "nueva_version"


def ingest_file(path: str, conn, embed_fn, faq_fn) -> dict:
    with open(path, encoding="utf-8") as f:
        raw_tramites = json.load(f)

    resumen = {"nuevos": 0, "sin_cambios": 0, "nueva_version": 0}
    for raw_tramite in raw_tramites:
        estado = ingest_tramite(raw_tramite, conn, embed_fn, faq_fn)
        conn.commit()
        if estado == "nuevo":
            resumen["nuevos"] += 1
        elif estado == "nueva_version":
            resumen["nueva_version"] += 1
        else:
            resumen["sin_cambios"] += 1
    return resumen
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_loader.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/loader.py backend/tests/test_loader.py
git commit -m "feat: orquestación de la ingesta con detección de cambios y versionado"
```

---

## Task 9: CLI de ingesta y documentación de uso

**Files:**
- Create: `backend/ingest/load.py`
- Test: `backend/tests/test_load_cli.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `db.connection.get_connection` (Task 1), `ingest.openai_client.build_real_client` (Task 4), `ingest.loader.ingest_file` (Task 8).
- Produces: `ingest.load.main(argv: list[str]) -> None`, ejecutable como `python -m ingest.load <archivo.json>`.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_load_cli.py`:

```python
import json

from ingest import load


class _FakeClient:
    def generate_embeddings(self, texts):
        return [[0.0] * 1536 for _ in texts]

    def generate_faqs(self, **kwargs):
        return [{"pregunta": "p", "respuesta": "r"}]


def test_main_prints_summary(tmp_path, monkeypatch, capsys):
    archivo = tmp_path / "sample.json"
    archivo.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr(load, "get_connection", lambda: object())
    monkeypatch.setattr(load, "build_real_client", lambda: _FakeClient())
    monkeypatch.setattr(
        load,
        "ingest_file",
        lambda path, conn, embed_fn, faq_fn: {"nuevos": 0, "sin_cambios": 0, "nueva_version": 0},
    )

    load.main([str(archivo)])

    salida = capsys.readouterr().out
    assert "Trámites nuevos: 0" in salida
    assert "Trámites sin cambios: 0" in salida
    assert "Trámites con nueva versión: 0" in salida
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_load_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'ingest.load'`

- [ ] **Step 3: Implementar `backend/ingest/load.py`**

```python
import sys

from dotenv import load_dotenv

from db.connection import get_connection
from ingest.loader import ingest_file
from ingest.openai_client import build_real_client


def main(argv: list[str]) -> None:
    load_dotenv()
    if len(argv) != 1:
        print("Uso: python -m ingest.load <archivo.json>")
        sys.exit(1)

    path = argv[0]
    conn = get_connection()
    client = build_real_client()

    resumen = ingest_file(path, conn, client.generate_embeddings, client.generate_faqs)

    print(f"Trámites nuevos: {resumen['nuevos']}")
    print(f"Trámites sin cambios: {resumen['sin_cambios']}")
    print(f"Trámites con nueva versión: {resumen['nueva_version']}")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_load_cli.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Crear `README.md` con instrucciones de uso**

```markdown
# Macacha — Núcleo de datos

Asistente virtual de trámites de la administración pública de la Provincia de Salta.
Este repositorio contiene, por ahora, el núcleo de datos: esquema Postgres+pgvector
con versionado de trámites y el pipeline de ingesta.

## Requisitos

- Docker y Docker Compose
- Python 3.11+
- Una API key de OpenAI

## Puesta en marcha

1. Copiar `.env.example` a `.env` y completar `OPENAI_API_KEY`.
2. Levantar Postgres: `docker compose up -d postgres`
3. Instalar dependencias: `cd backend && pip install -r requirements.txt`
4. Correr los tests: `pytest`

## Ingesta de trámites

```bash
cd backend
export $(cat ../.env | xargs)
python -m ingest.load /ruta/al/archivo_de_tramites.json
```

El comando es idempotente: si se vuelve a correr con el mismo contenido, no genera
nuevas versiones ni vuelve a llamar a la API de embeddings. Si algún campo de un
trámite cambió, cierra la versión vigente anterior y crea una nueva.
```

- [ ] **Step 6: Commit**

```bash
git add backend/ingest/load.py backend/tests/test_load_cli.py README.md
git commit -m "feat: CLI de ingesta (python -m ingest.load) y documentación de uso"
```

---

## Task 10: Verificación end-to-end con datos reales

Este paso valida los criterios de aceptación del spec contra el dataset real. No agrega
tests automatizados nuevos (requiere una API key de OpenAI real y genera costo), por lo
que se ejecuta manualmente.

**Files:** ninguno (solo verificación)

- [ ] **Step 1: Confirmar que Postgres está arriba**

Run: `docker compose up -d postgres && docker compose exec -T postgres pg_isready -U macacha`
Expected: `accepting connections`

- [ ] **Step 2: Cargar el dataset real por primera vez**

Run:
```bash
cd backend
export $(cat ../.env | xargs)
python -m ingest.load /home/seba/Descargas/entidades_tramites_registro_civil.json
```
Expected:
```
Trámites nuevos: 32
Trámites sin cambios: 0
Trámites con nueva versión: 0
```

- [ ] **Step 3: Volver a correr sin cambios en el archivo**

Run: `python -m ingest.load /home/seba/Descargas/entidades_tramites_registro_civil.json`
Expected:
```
Trámites nuevos: 0
Trámites sin cambios: 32
Trámites con nueva versión: 0
```

- [ ] **Step 4: Modificar un campo y volver a correr**

Editar manualmente el `costo` del trámite `RC-0001` en una copia del archivo (o con `jq`), y correr:

Run:
```bash
jq '(.[] | select(.id == "RC-0001") | .costo) = "$9999"' \
  /home/seba/Descargas/entidades_tramites_registro_civil.json > /tmp/tramites_modificado.json
python -m ingest.load /tmp/tramites_modificado.json
```
Expected:
```
Trámites nuevos: 0
Trámites sin cambios: 31
Trámites con nueva versión: 1
```

- [ ] **Step 5: Verificar que la versión anterior quedó conservada con su vigencia cerrada**

Run:
```bash
docker compose exec -T postgres psql -U macacha -d macacha -c \
  "SELECT numero_version, es_vigente, vigente_hasta FROM tramite_versiones WHERE tramite_id = 'RC-0001' ORDER BY numero_version;"
```
Expected: dos filas — versión 1 con `es_vigente = f` y `vigente_hasta` seteado, versión 2 con `es_vigente = t` y `vigente_hasta` nulo.

---

## Self-Review

**Cobertura del spec:**
- Esquema `organismos`/`tramites`/`tramite_versiones`/`tramite_chunks` con versionado → Task 1.
- Objeto enriquecido (snapshot) con todos los campos pedidos → Task 5.
- Chunks optimizados para embeddings, incluyendo FAQ y enlaces oficiales → Task 6.
- Enlaces oficiales extraídos de `pasos`/`chunks.fuente` → Task 3.
- FAQs generadas automáticamente cuando faltan → Task 5, Task 8 (test dedicado).
- Detección de cambios por hash y no regeneración de embeddings si no cambió → Task 2, Task 8.
- Pipeline de ingesta idempotente vía CLI → Task 9.
- Criterios de aceptación del spec (32 nuevos, reingesta sin cambios, nueva versión ante cambio) → Task 10.

**Placeholders:** ninguno — todos los pasos incluyen código completo y comandos exactos.

**Consistencia de tipos:** `embed_fn`/`faq_fn` mantienen la misma firma desde `OpenAIClient` (Task 4) hasta `snapshot_builder` (Task 5) y `loader` (Task 8); `repository.get_vigente_version` devuelve siempre `{"id", "numero_version", "content_hash"}`, consumido igual en Task 7 y Task 8.
