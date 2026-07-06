# Motor de Recuperación (Macacha) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir `backend/retrieval/`, un módulo Python puro (sin FastAPI, sin servicio HTTP) que expone `buscar_chunks`: búsqueda híbrida (vectorial + full-text search) fusionada por Reciprocal Rank Fusion (RRF) y re-ordenada por un re-ranking vía LLM, contra los `tramite_chunks` vigentes del núcleo de datos.

**Architecture:** Dos búsquedas independientes contra Postgres (similitud coseno vía pgvector, full-text search vía `tsvector`/`websearch_to_tsquery`) se fusionan con RRF (por posición ordinal, no por score normalizado) y el resultado fusionado se reordena con un método nuevo (`rerank`) en el `OpenAIClient` ya existente del núcleo de datos, reutilizando el mismo patrón de inyección de dependencias (`embed_fn`/`rerank_fn` inyectados, nunca instanciados internamente salvo en el cliente real).

**Tech Stack:** Python 3.11+, `psycopg[binary]` 3.x (ya en `backend/requirements.txt`), pgvector, OpenAI SDK (`gpt-4o-mini` para el re-ranking, reutilizando `OpenAIClient`), `pytest`, Postgres real vía Docker Compose (ya levantado por el núcleo de datos).

## Global Constraints

- Este subsistema es una librería Python pura invocada en proceso — **no** se agrega FastAPI ni ningún servicio HTTP en este plan.
- Reutilizar (no reimplementar) `ingest.repository` para armar datos de prueba en los tests de integración, y `ingest.openai_client.OpenAIClient` como base para el nuevo método `rerank`.
- Todas las consultas SQL filtran siempre por `tramite_versiones.es_vigente = true` (vía `JOIN`).
- `top_n` de cada búsqueda individual (vectorial y textual) es 20; la fusión RRF usa `k=60`; `top_k` final de `buscar_chunks` es 5 por defecto.
- El modelo de re-ranking es `gpt-4o-mini` (mismo modelo que `generate_faqs`, reutilizando la constante `OpenAIClient.FAQ_MODEL` ya existente).
- Ningún test de este subsistema hace una llamada real a la red/API de OpenAI — todos usan fakes/stubs inyectados, igual que en el núcleo de datos.
- Todo el trabajo vive bajo `backend/` dentro del repo `macacha`. Sin ORM: SQL directo vía `psycopg3`.
- `OPENAI_API_KEY`/`DATABASE_URL` solo vía variables de entorno, nunca hardcodeadas.

---

## Task 1: Mapeo de filas SQL a chunks (`chunk_result`)

**Files:**
- Create: `backend/retrieval/__init__.py`
- Create: `backend/retrieval/chunk_result.py`
- Test: `backend/tests/test_chunk_result.py`

**Interfaces:**
- Produces: `chunk_result.chunk_desde_fila(row: tuple) -> dict`, donde `row` es una tupla de 8 columnas `(chunk_id, tramite_id, nombre_oficial, categoria, organismo, tipo_chunk, texto, fuente_url)` (en ese orden, tal como las devuelve el `SELECT` compartido por `vector_search` y `fulltext_search` en las Tareas 4 y 5), y el dict resultante tiene la forma `{"chunk_id": str, "tramite_id": str, "nombre_oficial": str, "categoria": str, "organismo": str, "tipo_chunk": str, "texto": str, "fuente_url": str | None}`.

- [ ] **Step 1: Crear el paquete `backend/retrieval/__init__.py` (vacío)**

```python
```

- [ ] **Step 2: Escribir el test que falla**

Crear `backend/tests/test_chunk_result.py`:

```python
import uuid

from retrieval.chunk_result import chunk_desde_fila


def test_mapea_fila_a_dict_con_chunk_id_como_string():
    chunk_uuid = uuid.uuid4()
    fila = (
        chunk_uuid,
        "RC-0001",
        "Actas Regulares",
        "Actas",
        "Registro Civil",
        "descripcion",
        "texto del chunk",
        "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    )

    resultado = chunk_desde_fila(fila)

    assert resultado == {
        "chunk_id": str(chunk_uuid),
        "tramite_id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "categoria": "Actas",
        "organismo": "Registro Civil",
        "tipo_chunk": "descripcion",
        "texto": "texto del chunk",
        "fuente_url": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    }


def test_permite_fuente_url_nula():
    chunk_uuid = uuid.uuid4()
    fila = (chunk_uuid, "RC-0002", "Actas Exprés", "Actas", "Registro Civil", "faq", "pregunta respuesta", None)

    resultado = chunk_desde_fila(fila)

    assert resultado["fuente_url"] is None
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_chunk_result.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'retrieval.chunk_result'`

- [ ] **Step 4: Implementar `backend/retrieval/chunk_result.py`**

```python
def chunk_desde_fila(row: tuple) -> dict:
    chunk_id, tramite_id, nombre_oficial, categoria, organismo, tipo_chunk, texto, fuente_url = row
    return {
        "chunk_id": str(chunk_id),
        "tramite_id": tramite_id,
        "nombre_oficial": nombre_oficial,
        "categoria": categoria,
        "organismo": organismo,
        "tipo_chunk": tipo_chunk,
        "texto": texto,
        "fuente_url": fuente_url,
    }
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_chunk_result.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/retrieval/__init__.py backend/retrieval/chunk_result.py backend/tests/test_chunk_result.py
git commit -m "feat: mapeo de filas SQL a chunks para el motor de recuperación"
```

---

## Task 2: Fusión Reciprocal Rank Fusion (RRF)

**Files:**
- Create: `backend/retrieval/fusion.py`
- Test: `backend/tests/test_fusion.py`

**Interfaces:**
- Produces: `fusion.fusionar_rrf(ranking_vectorial: list[dict], ranking_textual: list[dict], k: int = 60) -> list[dict]`. Cada dict de entrada debe tener al menos la clave `"chunk_id"` (misma forma que produce `chunk_result.chunk_desde_fila`, Task 1). Devuelve la lista de chunks (deduplicados por `chunk_id`) ordenada por score RRF descendente.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_fusion.py`:

```python
from retrieval.fusion import fusionar_rrf


def test_fusiona_por_posicion_ordinal_no_por_score_absoluto():
    chunk_a = {"chunk_id": "a", "texto": "chunk a"}
    chunk_b = {"chunk_id": "b", "texto": "chunk b"}
    chunk_c = {"chunk_id": "c", "texto": "chunk c"}

    # "a" está 1° en vectorial y 3° en textual (aparece en ambos)
    # "b" está 2° solo en vectorial
    # "c" está 1° solo en textual
    ranking_vectorial = [chunk_a, chunk_b]
    ranking_textual = [chunk_c, {"chunk_id": "x", "texto": "otro"}, chunk_a]

    resultado = fusionar_rrf(ranking_vectorial, ranking_textual, k=60)

    # score(a) = 1/61 + 1/63 ≈ 0.032266 (aparece en ambos rankings)
    # score(c) = 1/61 ≈ 0.016393 (1° en textual)
    # score(b) = 1/62 ≈ 0.016129 (2° en vectorial)
    assert [c["chunk_id"] for c in resultado] == ["a", "c", "b", "x"]


def test_dedupe_por_chunk_id():
    chunk_a = {"chunk_id": "a", "texto": "chunk a"}

    resultado = fusionar_rrf([chunk_a], [chunk_a])

    assert len(resultado) == 1
    assert resultado[0]["chunk_id"] == "a"


def test_listas_vacias_devuelve_lista_vacia():
    assert fusionar_rrf([], []) == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_fusion.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'retrieval.fusion'`

- [ ] **Step 3: Implementar `backend/retrieval/fusion.py`**

```python
def fusionar_rrf(ranking_vectorial: list[dict], ranking_textual: list[dict], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    chunks_por_id: dict[str, dict] = {}

    for ranking in (ranking_vectorial, ranking_textual):
        for posicion, chunk in enumerate(ranking, start=1):
            chunk_id = chunk["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (k + posicion)
            chunks_por_id[chunk_id] = chunk

    orden = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [chunks_por_id[chunk_id] for chunk_id in orden]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_fusion.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/retrieval/fusion.py backend/tests/test_fusion.py
git commit -m "feat: fusión de rankings por Reciprocal Rank Fusion (RRF)"
```

---

## Task 3: Re-ranking vía LLM en `OpenAIClient`

**Files:**
- Modify: `backend/ingest/openai_client.py`
- Modify: `backend/tests/test_openai_client.py`

**Interfaces:**
- Consumes: la clase `OpenAIClient` y las clases fake `_FakeOpenAISDK`/`_FakeEmbeddings`/`_FakeChat`/`_FakeCompletions`/`_FakeChoice`/`_FakeMessage`/`_FakeEmbeddingResponse`/`_FakeEmbeddingItem` ya definidas en `backend/tests/test_openai_client.py` (de la Tarea 4 del núcleo de datos) — reutilizarlas tal cual, no duplicarlas.
- Produces: `OpenAIClient.rerank(self, query: str, candidatos: list[dict]) -> list[int]`. Cada dict de `candidatos` tiene al menos la clave `"texto"` (misma forma que `chunk_result.chunk_desde_fila`, Task 1). Devuelve una lista de índices 0-based sobre `candidatos`, en el orden de relevancia que decide el LLM (índice más relevante primero). Esta es la firma que va a inyectarse como `rerank_fn` en `hybrid_search.buscar_chunks` (Task 6).

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `backend/tests/test_openai_client.py` (reutilizando `_FakeOpenAISDK` y `OpenAIClient`, ya importados en ese archivo):

```python
def test_rerank_parses_json_response_as_order():
    orden_json = json.dumps({"orden": [2, 0, 1]})
    fake_sdk = _FakeOpenAISDK(vectors=[], faq_json_content=orden_json)
    client = OpenAIClient(fake_sdk)

    candidatos = [
        {"texto": "fragmento A"},
        {"texto": "fragmento B"},
        {"texto": "fragmento C"},
    ]

    resultado = client.rerank("una pregunta cualquiera", candidatos)

    assert resultado == [2, 0, 1]
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_openai_client.py -v -k rerank`
Expected: FAIL con `AttributeError: 'OpenAIClient' object has no attribute 'rerank'`

- [ ] **Step 3: Agregar el método `rerank` a `OpenAIClient` en `backend/ingest/openai_client.py`**

Agregar este método dentro de la clase `OpenAIClient` (después de `generate_faqs`, antes del cierre de la clase — `json` ya está importado al inicio del archivo):

```python
    def rerank(self, query: str, candidatos: list[dict]) -> list[int]:
        candidatos_numerados = "\n".join(
            f"{i}. {candidato['texto']}" for i, candidato in enumerate(candidatos)
        )
        prompt = (
            "Ordená los siguientes fragmentos por relevancia real a la pregunta del "
            "usuario, del más relevante al menos relevante.\n\n"
            f"Pregunta: {query}\n\n"
            f"Fragmentos:\n{candidatos_numerados}\n\n"
            'Respondé únicamente con JSON con esta forma: '
            '{"orden": [<índices originales, del más al menos relevante>]}'
        )
        response = self._sdk_client.chat.completions.create(
            model=self.FAQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return data["orden"]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_openai_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: agregar rerank() a OpenAIClient para re-ranking vía LLM"
```

---

## Task 4: Búsqueda vectorial (`vector_search`)

**Files:**
- Create: `backend/retrieval/vector_search.py`
- Test: `backend/tests/test_vector_search.py`

**Interfaces:**
- Consumes: `chunk_result.chunk_desde_fila` (Task 1); `ingest.repository.upsert_organismo`, `upsert_tramite`, `insert_version_with_chunks` (ya existentes, del núcleo de datos) para armar los datos de prueba; fixtures `db_conn`/`clean_db` de `backend/tests/conftest.py` (ya existentes).
- Produces: `vector_search.buscar_por_similitud(conn, query_embedding: list[float], top_n: int = 20) -> list[dict]`, ordenado por distancia coseno ascendente (más similar primero). Esta es la función que `hybrid_search.buscar_chunks` (Task 6) usa para el ranking vectorial.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_vector_search.py`:

```python
from ingest import repository as repo
from retrieval.vector_search import buscar_por_similitud


def _vector_con_uno_en(posicion: int, dimension: int = 1536) -> list[float]:
    vector = [0.0] * dimension
    vector[posicion] = 1.0
    return vector


def test_buscar_por_similitud_ordena_por_cercania_coseno(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": "chunk cercano", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk lejano", "fuente_url": None},
    ]
    embeddings = [_vector_con_uno_en(0), _vector_con_uno_en(1)]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    query_embedding = _vector_con_uno_en(0)

    resultados = buscar_por_similitud(db_conn, query_embedding, top_n=10)

    assert len(resultados) == 2
    assert resultados[0]["texto"] == "chunk cercano"
    assert resultados[1]["texto"] == "chunk lejano"
    assert resultados[0]["tramite_id"] == "RC-0001"
    assert resultados[0]["organismo"] == "Registro Civil"
    assert resultados[0]["categoria"] == "Actas"
    assert resultados[0]["nombre_oficial"] == "Actas Regulares"
    assert resultados[0]["tipo_chunk"] == "descripcion"


def test_respeta_top_n(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": f"chunk {i}", "fuente_url": None} for i in range(5)
    ]
    embeddings = [_vector_con_uno_en(i % 1536) for i in range(5)]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    resultados = buscar_por_similitud(db_conn, _vector_con_uno_en(0), top_n=2)

    assert len(resultados) == 2
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_vector_search.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'retrieval.vector_search'`

- [ ] **Step 3: Implementar `backend/retrieval/vector_search.py`**

```python
from retrieval.chunk_result import chunk_desde_fila


def buscar_por_similitud(conn, query_embedding: list[float], top_n: int = 20) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tc.id, t.id, t.nombre_oficial, t.categoria, o.nombre,
                   tc.tipo_chunk, tc.texto, tc.fuente_url
            FROM tramite_chunks tc
            JOIN tramite_versiones tv ON tv.id = tc.version_id AND tv.es_vigente = true
            JOIN tramites t ON t.id = tv.tramite_id
            JOIN organismos o ON o.id = t.organismo_id
            ORDER BY tc.embedding <=> %s
            LIMIT %s
            """,
            (query_embedding, top_n),
        )
        return [chunk_desde_fila(row) for row in cur.fetchall()]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_vector_search.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/retrieval/vector_search.py backend/tests/test_vector_search.py
git commit -m "feat: búsqueda vectorial por similitud coseno contra tramite_chunks vigentes"
```

---

## Task 5: Búsqueda de texto completo (`fulltext_search`)

**Files:**
- Create: `backend/retrieval/fulltext_search.py`
- Test: `backend/tests/test_fulltext_search.py`

**Interfaces:**
- Consumes: `chunk_result.chunk_desde_fila` (Task 1); `ingest.repository.*` (para datos de prueba); fixtures `db_conn`/`clean_db`.
- Produces: `fulltext_search.buscar_por_texto(conn, query: str, top_n: int = 20) -> list[dict]`, ordenado por `ts_rank` descendente. Esta es la función que `hybrid_search.buscar_chunks` (Task 6) usa para el ranking textual.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_fulltext_search.py`:

```python
from ingest import repository as repo
from retrieval.fulltext_search import buscar_por_texto


def test_buscar_por_texto_encuentra_por_relevancia(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {
            "tipo_chunk": "descripcion",
            "texto": "Trámite para solicitar un acta de nacimiento en Salta.",
            "fuente_url": None,
        },
        {
            "tipo_chunk": "descripcion",
            "texto": "Trámite para renovar el pasaporte argentino.",
            "fuente_url": None,
        },
    ]
    embeddings = [[0.0] * 1536, [0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    resultados = buscar_por_texto(db_conn, "acta de nacimiento", top_n=10)

    assert len(resultados) == 1
    assert resultados[0]["texto"] == "Trámite para solicitar un acta de nacimiento en Salta."


def test_sin_coincidencias_devuelve_lista_vacia(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [{"tipo_chunk": "descripcion", "texto": "Trámite para renovar el pasaporte.", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    resultados = buscar_por_texto(db_conn, "matrimonio civil", top_n=10)

    assert resultados == []
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_fulltext_search.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'retrieval.fulltext_search'`

- [ ] **Step 3: Implementar `backend/retrieval/fulltext_search.py`**

```python
from retrieval.chunk_result import chunk_desde_fila


def buscar_por_texto(conn, query: str, top_n: int = 20) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT tc.id, t.id, t.nombre_oficial, t.categoria, o.nombre,
                   tc.tipo_chunk, tc.texto, tc.fuente_url
            FROM tramite_chunks tc
            JOIN tramite_versiones tv ON tv.id = tc.version_id AND tv.es_vigente = true
            JOIN tramites t ON t.id = tv.tramite_id
            JOIN organismos o ON o.id = t.organismo_id
            WHERE tc.tsv @@ websearch_to_tsquery('spanish', %s)
            ORDER BY ts_rank(tc.tsv, websearch_to_tsquery('spanish', %s)) DESC
            LIMIT %s
            """,
            (query, query, top_n),
        )
        return [chunk_desde_fila(row) for row in cur.fetchall()]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_fulltext_search.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/retrieval/fulltext_search.py backend/tests/test_fulltext_search.py
git commit -m "feat: búsqueda de texto completo en español contra tramite_chunks vigentes"
```

---

## Task 6: Orquestación de la búsqueda híbrida (`hybrid_search`)

**Files:**
- Create: `backend/retrieval/hybrid_search.py`
- Test: `backend/tests/test_hybrid_search.py`

**Interfaces:**
- Consumes: `vector_search.buscar_por_similitud` (Task 4), `fulltext_search.buscar_por_texto` (Task 5), `fusion.fusionar_rrf` (Task 2); `ingest.repository.*` para datos de prueba.
- Produces: `hybrid_search.buscar_chunks(query: str, conn, embed_fn, rerank_fn, top_k: int = 5) -> list[dict]`. `embed_fn` tiene la firma de `OpenAIClient.generate_embeddings` (`texts: list[str] -> list[list[float]]`); `rerank_fn` tiene la firma de `OpenAIClient.rerank` (Task 3: `(query: str, candidatos: list[dict]) -> list[int]`). Esta es la función pública final que el agente (subsistema 3, futuro) va a invocar desde sus herramientas.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_hybrid_search.py`:

```python
from ingest import repository as repo
from retrieval.hybrid_search import buscar_chunks


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def test_buscar_chunks_aplica_el_orden_de_rerank_fn_y_recorta_a_top_k(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas uno", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas dos", "fuente_url": None},
        {"tipo_chunk": "descripcion", "texto": "chunk sobre actas tres", "fuente_url": None},
    ]
    embeddings = [[0.0] * 1536, [0.0] * 1536, [0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    candidatos_recibidos = []

    def rerank_fn_invierte_orden(query, candidatos):
        candidatos_recibidos.extend(candidatos)
        return list(reversed(range(len(candidatos))))

    resultados = buscar_chunks(
        "actas", db_conn, _fake_embed_fn, rerank_fn_invierte_orden, top_k=2
    )

    esperado = list(reversed(candidatos_recibidos))[:2]
    assert resultados == esperado
    assert len(resultados) == 2


def test_buscar_chunks_usa_embed_fn_para_la_query(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    chunks = [{"tipo_chunk": "descripcion", "texto": "chunk sobre actas", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, "hash-1", {"id": "RC-0001"}, chunks, embeddings
    )
    db_conn.commit()

    llamadas_embed = []

    def embed_fn_espia(texts):
        llamadas_embed.append(texts)
        return [[0.0] * 1536 for _ in texts]

    def rerank_fn_identidad(query, candidatos):
        return list(range(len(candidatos)))

    buscar_chunks("actas", db_conn, embed_fn_espia, rerank_fn_identidad, top_k=5)

    assert llamadas_embed == [["actas"]]
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && pytest tests/test_hybrid_search.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'retrieval.hybrid_search'`

- [ ] **Step 3: Implementar `backend/retrieval/hybrid_search.py`**

```python
from retrieval.fulltext_search import buscar_por_texto
from retrieval.fusion import fusionar_rrf
from retrieval.vector_search import buscar_por_similitud


def buscar_chunks(query: str, conn, embed_fn, rerank_fn, top_k: int = 5) -> list[dict]:
    query_embedding = embed_fn([query])[0]

    ranking_vectorial = buscar_por_similitud(conn, query_embedding, top_n=20)
    ranking_textual = buscar_por_texto(conn, query, top_n=20)
    fusionados = fusionar_rrf(ranking_vectorial, ranking_textual)

    orden = rerank_fn(query, fusionados)
    reordenados = [fusionados[i] for i in orden]

    return reordenados[:top_k]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `cd backend && pytest tests/test_hybrid_search.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Correr toda la suite del backend para confirmar que no hay regresiones**

Run: `cd backend && pytest -v`
Expected: todos los tests pasan (los del núcleo de datos + los 6 nuevos de este subsistema), salida sin warnings.

- [ ] **Step 6: Commit**

```bash
git add backend/retrieval/hybrid_search.py backend/tests/test_hybrid_search.py
git commit -m "feat: orquestación de la búsqueda híbrida con fusión RRF y re-ranking"
```

---

## Self-Review

**Cobertura del spec:**
- Búsqueda vectorial filtrando por versión vigente → Task 4.
- Búsqueda de texto completo en español filtrando por versión vigente → Task 5.
- Fusión RRF sin normalizar scores incompatibles → Task 2.
- Re-ranking vía LLM reutilizando `OpenAIClient` → Task 3.
- Orquestación final `buscar_chunks` con la firma exacta del spec → Task 6.
- Forma de resultado uniforme (`chunk_id`, `tramite_id`, `nombre_oficial`, `categoria`, `organismo`, `tipo_chunk`, `texto`, `fuente_url`) en las tres capas → Task 1, reutilizada en Tasks 4, 5, 6.
- Ningún test hace red real a OpenAI → verificado en Tasks 3 y 6 (fakes/spies inyectados).
- Sin FastAPI ni CLI de prueba manual (decisión explícita del usuario) → no se agrega ninguno en este plan.

**Placeholders:** ninguno — todos los pasos incluyen código completo y comandos exactos.

**Consistencia de tipos:** `chunk_desde_fila` (Task 1) define la forma de dict que consumen `vector_search`/`fulltext_search` (Tasks 4, 5) y que fluye sin cambios a través de `fusionar_rrf` (Task 2) y `buscar_chunks` (Task 6). `rerank_fn`/`OpenAIClient.rerank` (Task 3) recibe `candidatos: list[dict]` con clave `"texto"` — presente en todo dict producido por `chunk_desde_fila` — y devuelve `list[int]`, consumido igual en Task 6 (`orden = rerank_fn(...)`, `[fusionados[i] for i in orden]`).
