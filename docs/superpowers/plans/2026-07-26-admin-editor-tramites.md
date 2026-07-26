# Admin — editor de trámites (alta + edición) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la segunda sección del panel de admin: alta y edición de trámites desde la UI, reutilizando el modelo de versionado existente (`tramite_versiones`) sin duplicar el pipeline de ingesta por CLI, según el spec aprobado en `docs/superpowers/specs/2026-07-25-admin-editor-tramites-design.md`.

**Architecture:** Backend: dos módulos nuevos bajo `backend/agent/admin/` (`tramites_repository.py` para lecturas, `tramite_editor.py` para la lógica de guardado) más 5 endpoints nuevos en `agent/api.py`, todos protegidos por `requiere_admin` (ya existe). Reutiliza `ingest.hashing`, `ingest.repository` y la forma del `snapshot` que ya usa el pipeline de ingesta — no hay una segunda representación de datos. Frontend: rutas nuevas bajo `frontend/app/admin/tramites/`, con un formulario compartido entre alta y edición.

**Tech Stack:** FastAPI, psycopg3, pytest (backend) — Next.js 15 / React 19, Vitest (frontend). Sin dependencias nuevas.

## Global Constraints

- Identificadores nuevos en español, consistente con el resto del repo.
- Sin comentarios en el código salvo que expliquen un WHY no obvio.
- Tests de backend usan las fixtures `db_conn`/`clean_db` de `backend/tests/conftest.py` contra la DB real de test — no mockear la DB. El `embed_fn` (llamada a OpenAI) sí se fakea en los tests, siguiendo el patrón ya usado en `test_api.py`/`test_admin_api.py`.
- Frontend: sin tests automatizados de UI (no hay `jsdom`/`@testing-library`); páginas y componentes se verifican manualmente.
- **Forma del snapshot** (exacta, en este orden de claves no importa pero estos son los nombres): `id`, `organismo`, `categoria`, `nombre_oficial`, `sinonimos`, `keywords`, `descripcion`, `objetivo`, `requisitos`, `pasos`, `costo`, `modalidad`, `duracion`, `telefono_contacto`, `email_contacto`, `problemas_frecuentes`, `preguntas_frecuentes`, `enlaces_oficiales`, `faq_generadas_automaticamente`. El editor siempre setea `faq_generadas_automaticamente: false`.
- **Chunks preservados al editar** (no se recalculan, viajan con su embedding existente): `tipo_chunk` en `requisitos`, `pasos`, `costo_modalidad`, `problemas_frecuentes`, `descripcion`. **Chunks recalculados**: `faq`, `enlaces_oficiales` — se reconstruyen siempre que el snapshot cambió, sin importar qué campo específico cambió.
- `compute_content_hash` en este editor se calcula sobre el snapshot (no sobre un `raw_tramite` como el CLI) — son hashes de formatos distintos, no comparables entre sí; esto es intencional (ver spec).
- Falla de `embed_fn` (embeddings) durante un guardado → `rollback()` completo, `502` con `{"detail": "No se pudieron generar los embeddings. Verificá la configuración de OpenAI."}`. Nada queda escrito a medias.

---

## Backend

### Task 1: `agent/admin/tramites_repository.py` — lecturas para el admin

**Files:**
- Create: `backend/agent/admin/tramites_repository.py`
- Test: `backend/tests/test_admin_tramites_repository.py`

**Interfaces:**
- Consumes: nada nuevo (usa `conn` psycopg como el resto de `ingest/repository.py`).
- Produces: `listar_tramites(conn) -> list[dict]` (`id, nombre_oficial, organismo, categoria, veces_consultado, numero_version`), `listar_organismos(conn) -> list[str]`, `obtener_chunks_por_version(conn, version_id: str) -> list[dict]` (`tipo_chunk, texto, fuente_url, embedding`). Usadas por Tasks 2, 3, 4.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_tramites_repository.py`:

```python
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


def test_listar_organismos_devuelve_nombres_ordenados(db_conn, clean_db):
    repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramites_repository.listar_organismos(db_conn) == [
        "Dirección de Rentas",
        "Registro Civil",
    ]


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

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_repository.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.admin.tramites_repository'`

- [ ] **Step 3: Implementar `tramites_repository.py`**

Crear `backend/agent/admin/tramites_repository.py`:

```python
def listar_tramites(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.nombre_oficial, o.nombre, t.categoria, t.veces_consultado, v.numero_version
            FROM tramites t
            JOIN organismos o ON o.id = t.organismo_id
            LEFT JOIN tramite_versiones v ON v.tramite_id = t.id AND v.es_vigente = true
            ORDER BY t.id
            """
        )
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


def listar_organismos(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT nombre FROM organismos ORDER BY nombre")
        return [row[0] for row in cur.fetchall()]


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

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_repository.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/tramites_repository.py backend/tests/test_admin_tramites_repository.py
git commit -m "feat: lecturas de trámites y organismos para el admin"
```

---

### Task 2: `agent/admin/tramite_editor.py` — `editar_tramite`

**Files:**
- Create: `backend/agent/admin/tramite_editor.py`
- Test: `backend/tests/test_admin_tramite_editor.py`

**Interfaces:**
- Consumes: `ingest.hashing.compute_content_hash`, `ingest.repository.close_version`, `.get_vigente_version`, `.insert_version_with_chunks`, `.upsert_organismo`, `.upsert_tramite` (ya existen); `agent.admin.tramites_repository.obtener_chunks_por_version` (Task 1).
- Produces: `editar_tramite(conn, tramite_id: str, payload: dict, embed_fn) -> dict` (`{"tramite_id", "numero_version", "cambios"}`); helpers `_construir_snapshot`, `_construir_chunks_faq_y_enlaces`, `CHUNKS_PRESERVADOS` — estos dos últimos los reutiliza Task 3 (`crear_tramite`).

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_tramite_editor.py`:

```python
from ingest import repository as repo
from ingest.hashing import compute_content_hash
from agent.admin import tramite_editor
from agent.admin import tramites_repository


def _fake_embed(texts):
    return [[0.0] * 1536 for _ in texts]


def _snapshot_base(tramite_id="RC-0001", **overrides):
    snapshot = {
        "id": tramite_id,
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "sinonimos": [],
        "keywords": [],
        "descripcion": "desc",
        "objetivo": "obj",
        "requisitos": ["DNI"],
        "pasos": ["paso 1"],
        "costo": "Gratuito",
        "modalidad": "Presencial",
        "duracion": "10 min",
        "telefono_contacto": "0387-1111111",
        "email_contacto": "rc@salta.gob.ar",
        "problemas_frecuentes": [],
        "preguntas_frecuentes": [{"pregunta": "p1", "respuesta": "r1"}],
        "enlaces_oficiales": ["https://salta.gob.ar/rc"],
        "faq_generadas_automaticamente": False,
    }
    snapshot.update(overrides)
    return snapshot


def _crear_tramite_base(conn, tramite_id="RC-0001"):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, tramite_id, organismo_id, "Actas", "Actas Regulares")
    snapshot = _snapshot_base(tramite_id)
    content_hash = compute_content_hash(snapshot)
    chunks = [
        {
            "tipo_chunk": "requisitos",
            "texto": "Requisitos para Actas Regulares: DNI",
            "fuente_url": "https://fuente.gob.ar",
        },
        {"tipo_chunk": "faq", "texto": "p1 r1", "fuente_url": None},
        {
            "tipo_chunk": "enlaces_oficiales",
            "texto": "Enlaces oficiales: https://salta.gob.ar/rc",
            "fuente_url": "https://salta.gob.ar/rc",
        },
    ]
    embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
    repo.insert_version_with_chunks(conn, tramite_id, 1, content_hash, snapshot, chunks, embeddings)
    conn.commit()
    return snapshot


def _payload_desde_snapshot(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if k not in ("id", "faq_generadas_automaticamente")}


def test_editar_tramite_sin_cambios_no_crea_version_nueva(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)

    resultado = tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)

    assert resultado == {"tramite_id": "RC-0001", "numero_version": 1, "cambios": False}


def test_editar_tramite_con_cambios_crea_version_nueva(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["costo"] = "Con costo"

    resultado = tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    assert resultado == {"tramite_id": "RC-0001", "numero_version": 2, "cambios": True}
    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    assert vigente["numero_version"] == 2


def test_editar_tramite_preserva_chunks_narrativos_con_su_embedding(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["costo"] = "Con costo"

    tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    requisitos_chunk = next(c for c in chunks if c["tipo_chunk"] == "requisitos")
    assert requisitos_chunk["texto"] == "Requisitos para Actas Regulares: DNI"
    assert list(requisitos_chunk["embedding"][:3]) == [0.1, 0.1, 0.1]


def test_editar_tramite_regenera_chunks_de_faq_y_enlaces(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["preguntas_frecuentes"] = [{"pregunta": "nueva", "respuesta": "resp nueva"}]

    tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    faq_chunks = [c for c in chunks if c["tipo_chunk"] == "faq"]
    assert len(faq_chunks) == 1
    assert faq_chunks[0]["texto"] == "nueva resp nueva"


def test_editar_tramite_actualiza_organismo_categoria_y_nombre(db_conn, clean_db):
    snapshot = _crear_tramite_base(db_conn)
    payload = _payload_desde_snapshot(snapshot)
    payload["organismo"] = "Dirección de Rentas"
    payload["categoria"] = "Impuestos"
    payload["nombre_oficial"] = "Nuevo Nombre"

    tramite_editor.editar_tramite(db_conn, "RC-0001", payload, _fake_embed)
    db_conn.commit()

    tramites = tramites_repository.listar_tramites(db_conn)
    assert tramites[0]["organismo"] == "Dirección de Rentas"
    assert tramites[0]["categoria"] == "Impuestos"
    assert tramites[0]["nombre_oficial"] == "Nuevo Nombre"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramite_editor.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agent.admin.tramite_editor'`

- [ ] **Step 3: Implementar `tramite_editor.py`**

Crear `backend/agent/admin/tramite_editor.py`:

```python
from ingest.hashing import compute_content_hash
from ingest.repository import (
    close_version,
    get_vigente_version,
    insert_version_with_chunks,
    upsert_organismo,
    upsert_tramite,
)
from agent.admin.tramites_repository import obtener_chunks_por_version

CHUNKS_PRESERVADOS = {"requisitos", "pasos", "costo_modalidad", "problemas_frecuentes", "descripcion"}


def _construir_snapshot(tramite_id: str, payload: dict) -> dict:
    return {
        "id": tramite_id,
        "organismo": payload["organismo"],
        "categoria": payload.get("categoria", ""),
        "nombre_oficial": payload["nombre_oficial"],
        "sinonimos": payload.get("sinonimos", []),
        "keywords": payload.get("keywords", []),
        "descripcion": payload.get("descripcion", ""),
        "objetivo": payload.get("objetivo", ""),
        "requisitos": payload.get("requisitos", []),
        "pasos": payload.get("pasos", []),
        "costo": payload.get("costo", ""),
        "modalidad": payload.get("modalidad", ""),
        "duracion": payload.get("duracion", ""),
        "telefono_contacto": payload.get("telefono_contacto", ""),
        "email_contacto": payload.get("email_contacto", ""),
        "problemas_frecuentes": payload.get("problemas_frecuentes", []),
        "preguntas_frecuentes": payload.get("preguntas_frecuentes", []),
        "enlaces_oficiales": payload.get("enlaces_oficiales", []),
        "faq_generadas_automaticamente": False,
    }


def _construir_chunks_faq_y_enlaces(snapshot: dict) -> list[dict]:
    chunks = []
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


def editar_tramite(conn, tramite_id: str, payload: dict, embed_fn) -> dict:
    snapshot = _construir_snapshot(tramite_id, payload)
    content_hash = compute_content_hash(snapshot)

    vigente = get_vigente_version(conn, tramite_id)

    if vigente["content_hash"] == content_hash:
        return {"tramite_id": tramite_id, "numero_version": vigente["numero_version"], "cambios": False}

    chunks_existentes = obtener_chunks_por_version(conn, vigente["id"])
    preservados = [c for c in chunks_existentes if c["tipo_chunk"] in CHUNKS_PRESERVADOS]
    chunks_nuevos = _construir_chunks_faq_y_enlaces(snapshot)

    embeddings_nuevos = embed_fn([c["texto"] for c in chunks_nuevos]) if chunks_nuevos else []

    chunks_finales = preservados + chunks_nuevos
    embeddings_finales = [c["embedding"] for c in preservados] + embeddings_nuevos

    close_version(conn, vigente["id"])
    numero_version = vigente["numero_version"] + 1
    insert_version_with_chunks(
        conn, tramite_id, numero_version, content_hash, snapshot, chunks_finales, embeddings_finales
    )

    organismo_id = upsert_organismo(conn, snapshot["organismo"])
    upsert_tramite(conn, tramite_id, organismo_id, snapshot["categoria"], snapshot["nombre_oficial"])

    return {"tramite_id": tramite_id, "numero_version": numero_version, "cambios": True}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramite_editor.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/tramite_editor.py backend/tests/test_admin_tramite_editor.py
git commit -m "feat: editar_tramite con preservación de chunks narrativos"
```

---

### Task 3: `agent/admin/tramite_editor.py` — `crear_tramite` + generación de ID

**Files:**
- Modify: `backend/agent/admin/tramite_editor.py`
- Modify: `backend/tests/test_admin_tramite_editor.py`

**Interfaces:**
- Consumes: `_construir_snapshot`, `_construir_chunks_faq_y_enlaces` (Task 2, mismo archivo); `ingest.repository.upsert_organismo`, `.upsert_tramite`, `.insert_version_with_chunks`, `ingest.hashing.compute_content_hash`.
- Produces: `crear_tramite(conn, payload: dict, embed_fn) -> dict` (`{"tramite_id", "numero_version", "cambios"}`), `generar_id_tramite(conn, organismo: str) -> str`. Usadas por Task 6 (endpoint `POST /admin/tramites`).

- [ ] **Step 1: Agregar los tests que fallan**

Agregar al final de `backend/tests/test_admin_tramite_editor.py`:

```python
def _payload_minimo(organismo="Registro Civil", categoria="Actas", nombre="Nuevo Trámite"):
    return {
        "organismo": organismo,
        "categoria": categoria,
        "nombre_oficial": nombre,
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


def test_generar_id_tramite_reutiliza_prefijo_de_organismo_existente(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0032", organismo_id, "Actas", "Trámite existente")
    db_conn.commit()

    assert tramite_editor.generar_id_tramite(db_conn, "Registro Civil") == "RC-0033"


def test_generar_id_tramite_deriva_prefijo_de_iniciales_para_organismo_nuevo(db_conn, clean_db):
    repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramite_editor.generar_id_tramite(db_conn, "Dirección de Rentas") == "DR-0001"


def test_generar_id_tramite_resuelve_colision_de_prefijo(db_conn, clean_db):
    organismo_dr_id = repo.upsert_organismo(db_conn, "Departamento de Recursos")
    repo.upsert_tramite(db_conn, "DR-0001", organismo_dr_id, "Cat", "Trámite del primero")
    repo.upsert_organismo(db_conn, "Dirección de Rentas")
    db_conn.commit()

    assert tramite_editor.generar_id_tramite(db_conn, "Dirección de Rentas") == "DR2-0001"


def test_crear_tramite_inserta_version_uno_con_chunk_de_descripcion(db_conn, clean_db):
    payload = _payload_minimo()
    payload["descripcion"] = "Descripción del trámite"

    resultado = tramite_editor.crear_tramite(db_conn, payload, _fake_embed)
    db_conn.commit()

    assert resultado == {"tramite_id": resultado["tramite_id"], "numero_version": 1, "cambios": True}
    assert resultado["tramite_id"].startswith("RC-")

    vigente = repo.get_vigente_version(db_conn, resultado["tramite_id"])
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    assert chunks[0]["tipo_chunk"] == "descripcion"
    assert chunks[0]["texto"] == "Nuevo Trámite. Descripción del trámite"


def test_crear_tramite_sin_descripcion_usa_solo_el_nombre(db_conn, clean_db):
    payload = _payload_minimo()

    resultado = tramite_editor.crear_tramite(db_conn, payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, resultado["tramite_id"])
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    assert chunks[0]["texto"] == "Nuevo Trámite"


def test_crear_tramite_incluye_chunks_de_faq_si_hay(db_conn, clean_db):
    payload = _payload_minimo()
    payload["preguntas_frecuentes"] = [{"pregunta": "p", "respuesta": "r"}]

    resultado = tramite_editor.crear_tramite(db_conn, payload, _fake_embed)
    db_conn.commit()

    vigente = repo.get_vigente_version(db_conn, resultado["tramite_id"])
    chunks = tramites_repository.obtener_chunks_por_version(db_conn, vigente["id"])
    tipos = {c["tipo_chunk"] for c in chunks}
    assert "faq" in tipos
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramite_editor.py -v -k "generar_id or crear_tramite"`
Expected: FAIL con `AttributeError: module 'agent.admin.tramite_editor' has no attribute 'generar_id_tramite'`

- [ ] **Step 3: Agregar `generar_id_tramite` y `crear_tramite`**

Agregar al final de `backend/agent/admin/tramite_editor.py`:

```python
def generar_id_tramite(conn, organismo: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id
            FROM tramites t
            JOIN organismos o ON o.id = t.organismo_id
            WHERE o.nombre = %s
            ORDER BY t.id
            LIMIT 1
            """,
            (organismo,),
        )
        fila = cur.fetchone()

    if fila is not None:
        prefijo = fila[0].split("-")[0]
    else:
        prefijo = _resolver_colision_prefijo(conn, _iniciales(organismo))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM tramites WHERE id LIKE %s ORDER BY id DESC LIMIT 1",
            (f"{prefijo}-%",),
        )
        ultimo = cur.fetchone()

    siguiente_numero = 1 if ultimo is None else int(ultimo[0].split("-")[1]) + 1
    return f"{prefijo}-{siguiente_numero:04d}"


def _iniciales(organismo: str) -> str:
    conectores = {"de", "del", "la", "los", "las", "y"}
    palabras = [p for p in organismo.split() if p.lower() not in conectores]
    if not palabras:
        return organismo[:2].upper()
    return "".join(p[0].upper() for p in palabras)


def _resolver_colision_prefijo(conn, prefijo: str) -> str:
    with conn.cursor() as cur:
        for sufijo in [""] + [str(n) for n in range(2, 10)]:
            candidato = f"{prefijo}{sufijo}"
            cur.execute("SELECT 1 FROM tramites WHERE id LIKE %s LIMIT 1", (f"{candidato}-%",))
            if cur.fetchone() is None:
                return candidato
    raise RuntimeError(f"No se pudo generar un prefijo único a partir de '{prefijo}'")


def crear_tramite(conn, payload: dict, embed_fn) -> dict:
    organismo_id = upsert_organismo(conn, payload["organismo"])
    tramite_id = generar_id_tramite(conn, payload["organismo"])
    upsert_tramite(conn, tramite_id, organismo_id, payload.get("categoria", ""), payload["nombre_oficial"])

    snapshot = _construir_snapshot(tramite_id, payload)
    content_hash = compute_content_hash(snapshot)

    descripcion_texto = snapshot["nombre_oficial"]
    if snapshot["descripcion"]:
        descripcion_texto = f"{snapshot['nombre_oficial']}. {snapshot['descripcion']}"

    chunks = [{"tipo_chunk": "descripcion", "texto": descripcion_texto, "fuente_url": None}]
    chunks.extend(_construir_chunks_faq_y_enlaces(snapshot))

    embeddings = embed_fn([c["texto"] for c in chunks])

    insert_version_with_chunks(conn, tramite_id, 1, content_hash, snapshot, chunks, embeddings)

    return {"tramite_id": tramite_id, "numero_version": 1, "cambios": True}
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramite_editor.py -v`
Expected: PASS (11 tests: 5 de `editar_tramite` + 6 nuevos)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/admin/tramite_editor.py backend/tests/test_admin_tramite_editor.py
git commit -m "feat: crear_tramite con generación de ID por organismo"
```

---

### Task 4: Endpoints de lectura (`GET /admin/tramites`, `GET /admin/organismos`, `GET /admin/tramites/{id}`)

**Files:**
- Modify: `backend/agent/api.py`
- Create: `backend/tests/test_admin_tramites_api.py`

**Interfaces:**
- Consumes: `admin_tramites_repository.listar_tramites`, `.listar_organismos` (Task 1); `ingest.repository.obtener_snapshot_vigente` (ya existe, ya importado en `api.py`); `requiere_admin` (ya existe).
- Produces: `GET /admin/tramites` → `list[dict]`; `GET /admin/organismos` → `list[str]`; `GET /admin/tramites/{tramite_id}` → snapshot con los campos editables (sin `id` ni `faq_generadas_automaticamente`) o `404`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `backend/tests/test_admin_tramites_api.py`:

```python
from fastapi.testclient import TestClient

from agent import api
from agent.admin import repository as admin_repository
from agent.admin import security as admin_security
from agent.api import obtener_pool
from ingest import repository as repo
from ingest.hashing import compute_content_hash


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


class _FakeOpenAIClient:
    def generate_embeddings(self, texts):
        return [[0.0] * 1536 for _ in texts]


def _crear_admin_y_loguear(client, conn):
    email, password = "admin@macacha.gob.ar", "secreta123"
    admin_repository.crear_admin(conn, email, admin_security.hash_password(password))
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": password})


def test_listar_tramites_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.get("/admin/tramites")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_listar_tramites_devuelve_lista(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
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
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, [[0.0] * 1536])
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/tramites")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()[0]["id"] == "RC-0001"


def test_listar_organismos_devuelve_nombres(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/organismos")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == ["Registro Civil"]


def test_obtener_tramite_admin_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/tramites/RC-9999")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_obtener_tramite_admin_devuelve_snapshot_completo(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "desc",
        "objetivo": "obj",
        "requisitos": ["DNI"],
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

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.get("/admin/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre_oficial"] == "Actas Regulares"
    assert cuerpo["requisitos"] == ["DNI"]
    assert "id" not in cuerpo
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_api.py -v`
Expected: FAIL con `404 Not Found` (las rutas todavía no existen)

- [ ] **Step 3: Agregar los endpoints**

En `backend/agent/api.py`, agregar el import junto a los demás de `agent.admin`:

```python
from agent.admin import tramites_repository as admin_tramites_repository
```

Agregar al final del archivo:

```python
@app.get("/admin/tramites")
def admin_listar_tramites(admin_id: str = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return admin_tramites_repository.listar_tramites(conn)


@app.get("/admin/organismos")
def admin_listar_organismos(admin_id: str = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        return admin_tramites_repository.listar_organismos(conn)


@app.get("/admin/tramites/{tramite_id}")
def admin_obtener_tramite(
    tramite_id: str, admin_id: str = Depends(requiere_admin), pool=Depends(obtener_pool)
):
    with pool.connection() as conn:
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
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_api.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_tramites_api.py
git commit -m "feat: endpoints de lectura de trámites y organismos para el admin"
```

---

### Task 5: Endpoint `PUT /admin/tramites/{id}` (editar)

**Files:**
- Modify: `backend/agent/api.py`
- Modify: `backend/tests/test_admin_tramites_api.py`

**Interfaces:**
- Consumes: `admin_tramite_editor.editar_tramite` (Task 2); `obtener_openai_client` (ya existe en `api.py`, usado por `/chat`).
- Produces: modelos Pydantic `FaqPayload`, `TramitePayload`; `PUT /admin/tramites/{tramite_id}` → `{"tramite_id", "numero_version", "cambios"}`, `404` si no existe, `422` si `organismo`/`nombre_oficial` vacíos, `502` si falla `embed_fn`.

- [ ] **Step 1: Agregar los tests que fallan**

Agregar al final de `backend/tests/test_admin_tramites_api.py`:

```python
def test_editar_tramite_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.put(
            "/admin/tramites/RC-0001", json={"organismo": "x", "nombre_oficial": "y"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_editar_tramite_inexistente_devuelve_404(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put(
            "/admin/tramites/RC-9999", json={"organismo": "Registro Civil", "nombre_oficial": "x"}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_editar_tramite_payload_invalido_devuelve_422(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/tramites/RC-0001", json={"organismo": "", "nombre_oficial": "x"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422


def _payload_edicion(**overrides):
    payload = {
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
        "objetivo": "",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "Gratis",
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
    payload.update(overrides)
    return payload


def test_editar_tramite_exitoso_crea_version_nueva(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
        "objetivo": "",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "Gratis",
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
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, compute_content_hash(snapshot), snapshot, chunks, [[0.0] * 1536]
    )
    db_conn.commit()

    payload = _payload_edicion(costo="Con costo")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClient()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/tramites/RC-0001", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {"tramite_id": "RC-0001", "numero_version": 2, "cambios": True}


def test_editar_tramite_falla_de_embeddings_no_escribe_nada(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "descripcion": "",
        "objetivo": "",
        "requisitos": ["DNI"],
        "pasos": [],
        "costo": "Gratis",
        "modalidad": "",
        "duracion": "",
        "telefono_contacto": "",
        "email_contacto": "",
        "problemas_frecuentes": [],
        "sinonimos": [],
        "keywords": [],
        "enlaces_oficiales": [],
        "preguntas_frecuentes": [{"pregunta": "p", "respuesta": "r"}],
        "faq_generadas_automaticamente": False,
    }

    chunks = [{"tipo_chunk": "faq", "texto": "p r", "fuente_url": None}]
    repo.insert_version_with_chunks(
        db_conn, "RC-0001", 1, compute_content_hash(snapshot), snapshot, chunks, [[0.0] * 1536]
    )
    db_conn.commit()

    payload = _payload_edicion(
        costo="Con costo cambiado",
        preguntas_frecuentes=[{"pregunta": "nueva", "respuesta": "resp"}],
    )

    class _FakeOpenAIClientRoto:
        def generate_embeddings(self, texts):
            raise RuntimeError("401 de OpenAI")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[api.obtener_openai_client] = lambda: _FakeOpenAIClientRoto()
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.put("/admin/tramites/RC-0001", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 502
    vigente = repo.get_vigente_version(db_conn, "RC-0001")
    assert vigente["numero_version"] == 1
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_api.py -v -k "editar_tramite"`
Expected: FAIL con `404 Not Found` (la ruta `PUT` todavía no existe)

- [ ] **Step 3: Agregar el modelo Pydantic y el endpoint**

En `backend/agent/api.py`, modificar el import de `pydantic`:

```python
from pydantic import BaseModel, Field
```

Agregar el import de `tramite_editor` junto a los demás de `agent.admin`:

```python
from agent.admin import tramite_editor as admin_tramite_editor
```

Agregar antes de los endpoints de trámites (o al final del archivo, junto a `admin_obtener_tramite`):

```python
class FaqPayload(BaseModel):
    pregunta: str
    respuesta: str


class TramitePayload(BaseModel):
    organismo: str = Field(min_length=1)
    categoria: str = ""
    nombre_oficial: str = Field(min_length=1)
    descripcion: str = ""
    objetivo: str = ""
    requisitos: list[str] = []
    pasos: list[str] = []
    costo: str = ""
    modalidad: str = ""
    duracion: str = ""
    telefono_contacto: str = ""
    email_contacto: str = ""
    problemas_frecuentes: list[str] = []
    sinonimos: list[str] = []
    keywords: list[str] = []
    enlaces_oficiales: list[str] = []
    preguntas_frecuentes: list[FaqPayload] = []


@app.put("/admin/tramites/{tramite_id}")
def admin_editar_tramite(
    tramite_id: str,
    request: TramitePayload,
    admin_id: str = Depends(requiere_admin),
    pool=Depends(obtener_pool),
    openai_client=Depends(obtener_openai_client),
):
    with pool.connection() as conn:
        if obtener_snapshot_vigente(conn, tramite_id) is None:
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
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_api.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_tramites_api.py
git commit -m "feat: endpoint de edición de trámites para el admin"
```

---

### Task 6: Endpoint `POST /admin/tramites` (crear)

**Files:**
- Modify: `backend/agent/api.py`
- Modify: `backend/tests/test_admin_tramites_api.py`

**Interfaces:**
- Consumes: `admin_tramite_editor.crear_tramite` (Task 3); `TramitePayload` (Task 5).
- Produces: `POST /admin/tramites` → `{"tramite_id", "numero_version", "cambios"}`, `422` si payload inválido, `502` si falla `embed_fn`.

- [ ] **Step 1: Agregar los tests que fallan**

Agregar al final de `backend/tests/test_admin_tramites_api.py`:

```python
def test_crear_tramite_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        respuesta = client.post("/admin/tramites", json={"organismo": "x", "nombre_oficial": "y"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_crear_tramite_payload_invalido_devuelve_422(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post(
            "/admin/tramites", json={"organismo": "Registro Civil", "nombre_oficial": ""}
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422


def test_crear_tramite_exitoso_genera_id_y_version_uno(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    payload = {
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Trámite Nuevo",
        "descripcion": "Descripción",
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
        _crear_admin_y_loguear(client, db_conn)
        respuesta = client.post("/admin/tramites", json=payload)
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tramite_id"].startswith("RC-")
    assert cuerpo["numero_version"] == 1
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_tramites_api.py -v -k "crear_tramite"`
Expected: FAIL con `404 Not Found` (la ruta `POST` todavía no existe)

- [ ] **Step 3: Agregar el endpoint**

Agregar al final de `backend/agent/api.py`:

```python
@app.post("/admin/tramites")
def admin_crear_tramite(
    request: TramitePayload,
    admin_id: str = Depends(requiere_admin),
    pool=Depends(obtener_pool),
    openai_client=Depends(obtener_openai_client),
):
    with pool.connection() as conn:
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

- [ ] **Step 4: Correr todos los tests del backend y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Expected: PASS (toda la suite, sin regresiones)

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_admin_tramites_api.py
git commit -m "feat: endpoint de alta de trámites para el admin"
```

---

## Frontend

### Task 7: `lib/admin-tramites-api.ts` — tipos y cliente fetch

**Files:**
- Create: `frontend/lib/admin-tramites-api.ts`

**Interfaces:**
- Produces: tipos `Faq`, `TramiteResumen`, `TramiteDetalleAdmin`, `GuardarTramiteResultado`; funciones `listarTramites()`, `listarOrganismos()`, `obtenerTramiteAdmin(id)`, `crearTramite(datos)`, `editarTramite(id, datos)`. Consumidas por Tasks 9, 10, 11, 12.

No hay test automatizado (mismo criterio que `lib/admin-api.ts`).

- [ ] **Step 1: Crear `admin-tramites-api.ts`**

Crear `frontend/lib/admin-tramites-api.ts`:

```typescript
export type Faq = { pregunta: string; respuesta: string };

export type TramiteResumen = {
  id: string;
  nombre_oficial: string;
  organismo: string;
  categoria: string;
  veces_consultado: number;
  numero_version: number | null;
};

export type TramiteDetalleAdmin = {
  organismo: string;
  categoria: string;
  nombre_oficial: string;
  descripcion: string;
  objetivo: string;
  requisitos: string[];
  pasos: string[];
  costo: string;
  modalidad: string;
  duracion: string;
  telefono_contacto: string;
  email_contacto: string;
  problemas_frecuentes: string[];
  sinonimos: string[];
  keywords: string[];
  enlaces_oficiales: string[];
  preguntas_frecuentes: Faq[];
};

export type GuardarTramiteResultado = {
  tramite_id: string;
  numero_version: number;
  cambios: boolean;
};

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listarTramites(): Promise<TramiteResumen[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/tramites`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar la lista de trámites");
  }
  return respuesta.json();
}

export async function listarOrganismos(): Promise<string[]> {
  const respuesta = await fetch(`${BASE_URL}/admin/organismos`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    throw new Error("No se pudieron cargar los organismos");
  }
  return respuesta.json();
}

export async function obtenerTramiteAdmin(id: string): Promise<TramiteDetalleAdmin | null> {
  const respuesta = await fetch(`${BASE_URL}/admin/tramites/${id}`, {
    credentials: "include",
  });
  if (respuesta.status === 404) {
    return null;
  }
  if (!respuesta.ok) {
    throw new Error("No se pudo cargar el trámite");
  }
  return respuesta.json();
}

async function guardarTramite(
  url: string,
  method: "POST" | "PUT",
  datos: TramiteDetalleAdmin
): Promise<GuardarTramiteResultado> {
  const respuesta = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(datos),
  });
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => null);
    throw new Error(cuerpo?.detail ?? "No se pudo guardar el trámite");
  }
  return respuesta.json();
}

export async function crearTramite(datos: TramiteDetalleAdmin): Promise<GuardarTramiteResultado> {
  return guardarTramite(`${BASE_URL}/admin/tramites`, "POST", datos);
}

export async function editarTramite(
  id: string,
  datos: TramiteDetalleAdmin
): Promise<GuardarTramiteResultado> {
  return guardarTramite(`${BASE_URL}/admin/tramites/${id}`, "PUT", datos);
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/admin-tramites-api.ts
git commit -m "feat: cliente HTTP de trámites para el admin"
```

---

### Task 8: `components/ListaTextos.tsx` + `components/ListaFAQ.tsx`

**Files:**
- Create: `frontend/components/ListaTextos.tsx`
- Create: `frontend/components/ListaFAQ.tsx`

**Interfaces:**
- Consumes: tipo `Faq` de `lib/admin-tramites-api.ts` (Task 7).
- Produces: `<ListaTextos etiqueta valores onChange>`, `<ListaFAQ valores onChange>`. Usados por Task 9.

No hay test automatizado (componentes con DOM, mismo criterio que el resto del panel).

- [ ] **Step 1: Crear `ListaTextos.tsx`**

Crear `frontend/components/ListaTextos.tsx`:

```tsx
"use client";

export function ListaTextos({
  etiqueta,
  valores,
  onChange,
}: {
  etiqueta: string;
  valores: string[];
  onChange: (valores: string[]) => void;
}) {
  function actualizar(indice: number, valor: string) {
    const nuevos = [...valores];
    nuevos[indice] = valor;
    onChange(nuevos);
  }

  function agregar() {
    onChange([...valores, ""]);
  }

  function quitar(indice: number) {
    onChange(valores.filter((_, i) => i !== indice));
  }

  return (
    <div>
      <label className="mb-1 block text-sm font-medium">{etiqueta}</label>
      <div className="space-y-2">
        {valores.map((valor, indice) => (
          <div key={indice} className="flex gap-2">
            <input
              type="text"
              value={valor}
              onChange={(e) => actualizar(indice, e.target.value)}
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button type="button" onClick={() => quitar(indice)} className="text-sm text-red-600">
              Quitar
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={agregar} className="mt-2 text-sm text-blue-700 underline">
        + Agregar
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Crear `ListaFAQ.tsx`**

Crear `frontend/components/ListaFAQ.tsx`:

```tsx
"use client";

import type { Faq } from "../lib/admin-tramites-api";

export function ListaFAQ({
  valores,
  onChange,
}: {
  valores: Faq[];
  onChange: (valores: Faq[]) => void;
}) {
  function actualizar(indice: number, campo: keyof Faq, valor: string) {
    const nuevos = [...valores];
    nuevos[indice] = { ...nuevos[indice], [campo]: valor };
    onChange(nuevos);
  }

  function agregar() {
    onChange([...valores, { pregunta: "", respuesta: "" }]);
  }

  function quitar(indice: number) {
    onChange(valores.filter((_, i) => i !== indice));
  }

  return (
    <div>
      <label className="mb-1 block text-sm font-medium">Preguntas frecuentes</label>
      <div className="space-y-3">
        {valores.map((faq, indice) => (
          <div key={indice} className="space-y-1 rounded border border-gray-200 p-2">
            <input
              type="text"
              placeholder="Pregunta"
              value={faq.pregunta}
              onChange={(e) => actualizar(indice, "pregunta", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <input
              type="text"
              placeholder="Respuesta"
              value={faq.respuesta}
              onChange={(e) => actualizar(indice, "respuesta", e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
            />
            <button type="button" onClick={() => quitar(indice)} className="text-sm text-red-600">
              Quitar
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={agregar} className="mt-2 text-sm text-blue-700 underline">
        + Agregar pregunta
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 4: Commit**

```bash
git add frontend/components/ListaTextos.tsx frontend/components/ListaFAQ.tsx
git commit -m "feat: editores de listas de texto y FAQ para el form de trámites"
```

---

### Task 9: `components/TramiteForm.tsx` — formulario compartido

**Files:**
- Create: `frontend/components/TramiteForm.tsx`

**Interfaces:**
- Consumes: `ListaTextos` (Task 8), `ListaFAQ` (Task 8), tipo `TramiteDetalleAdmin` de `lib/admin-tramites-api.ts` (Task 7).
- Produces: `<TramiteForm valoresIniciales organismosExistentes guardando error onGuardar>`. Usado por Tasks 11 y 12.

No hay test automatizado.

- [ ] **Step 1: Crear `TramiteForm.tsx`**

Crear `frontend/components/TramiteForm.tsx`:

```tsx
"use client";

import { useState, type FormEvent } from "react";
import { ListaFAQ } from "./ListaFAQ";
import { ListaTextos } from "./ListaTextos";
import type { TramiteDetalleAdmin } from "../lib/admin-tramites-api";

export function TramiteForm({
  valoresIniciales,
  organismosExistentes,
  guardando,
  error,
  onGuardar,
}: {
  valoresIniciales: TramiteDetalleAdmin;
  organismosExistentes: string[];
  guardando: boolean;
  error: string | null;
  onGuardar: (datos: TramiteDetalleAdmin) => void;
}) {
  const [datos, setDatos] = useState<TramiteDetalleAdmin>(valoresIniciales);
  const [organismoEsNuevo, setOrganismoEsNuevo] = useState(
    !organismosExistentes.includes(valoresIniciales.organismo)
  );

  function actualizar<K extends keyof TramiteDetalleAdmin>(campo: K, valor: TramiteDetalleAdmin[K]) {
    setDatos((anterior) => ({ ...anterior, [campo]: valor }));
  }

  function handleSubmit(evento: FormEvent) {
    evento.preventDefault();
    onGuardar(datos);
  }

  const puedeGuardar = datos.organismo.trim() !== "" && datos.nombre_oficial.trim() !== "";

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl space-y-4 p-4">
      <div>
        <label className="mb-1 block text-sm font-medium">Organismo</label>
        {organismoEsNuevo ? (
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
              <option key={organismo} value={organismo}>
                {organismo}
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() => setOrganismoEsNuevo(!organismoEsNuevo)}
          className="mt-1 text-sm text-blue-700 underline"
        >
          {organismoEsNuevo ? "Elegir uno existente" : "Otro… (crear nuevo)"}
        </button>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Categoría</label>
        <input
          type="text"
          value={datos.categoria}
          onChange={(e) => actualizar("categoria", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Nombre oficial</label>
        <input
          type="text"
          value={datos.nombre_oficial}
          onChange={(e) => actualizar("nombre_oficial", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Descripción</label>
        <textarea
          value={datos.descripcion}
          onChange={(e) => actualizar("descripcion", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">Objetivo</label>
        <textarea
          value={datos.objetivo}
          onChange={(e) => actualizar("objetivo", e.target.value)}
          className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </div>

      <ListaTextos
        etiqueta="Requisitos"
        valores={datos.requisitos}
        onChange={(v) => actualizar("requisitos", v)}
      />
      <ListaTextos etiqueta="Pasos" valores={datos.pasos} onChange={(v) => actualizar("pasos", v)} />

      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="mb-1 block text-sm font-medium">Costo</label>
          <input
            type="text"
            value={datos.costo}
            onChange={(e) => actualizar("costo", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Modalidad</label>
          <input
            type="text"
            value={datos.modalidad}
            onChange={(e) => actualizar("modalidad", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Duración</label>
          <input
            type="text"
            value={datos.duracion}
            onChange={(e) => actualizar("duracion", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-sm font-medium">Teléfono de contacto</label>
          <input
            type="text"
            value={datos.telefono_contacto}
            onChange={(e) => actualizar("telefono_contacto", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">Email de contacto</label>
          <input
            type="text"
            value={datos.email_contacto}
            onChange={(e) => actualizar("email_contacto", e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
          />
        </div>
      </div>

      <ListaTextos
        etiqueta="Problemas frecuentes"
        valores={datos.problemas_frecuentes}
        onChange={(v) => actualizar("problemas_frecuentes", v)}
      />
      <ListaTextos
        etiqueta="Sinónimos"
        valores={datos.sinonimos}
        onChange={(v) => actualizar("sinonimos", v)}
      />
      <ListaTextos
        etiqueta="Keywords"
        valores={datos.keywords}
        onChange={(v) => actualizar("keywords", v)}
      />
      <ListaTextos
        etiqueta="Enlaces oficiales"
        valores={datos.enlaces_oficiales}
        onChange={(v) => actualizar("enlaces_oficiales", v)}
      />
      <ListaFAQ
        valores={datos.preguntas_frecuentes}
        onChange={(v) => actualizar("preguntas_frecuentes", v)}
      />

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={!puedeGuardar || guardando}
        className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50"
      >
        {guardando ? "Guardando…" : "Guardar"}
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 3: Commit**

```bash
git add frontend/components/TramiteForm.tsx
git commit -m "feat: formulario compartido de alta/edición de trámites"
```

---

### Task 10: Lista de trámites + link de navegación

**Files:**
- Create: `frontend/app/admin/tramites/page.tsx`
- Modify: `frontend/app/admin/layout.tsx`

**Interfaces:**
- Consumes: `listarTramites`, tipo `TramiteResumen` de `lib/admin-tramites-api.ts` (Task 7).

- [ ] **Step 1: Crear la página de lista**

Crear `frontend/app/admin/tramites/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listarTramites, type TramiteResumen } from "../../../lib/admin-tramites-api";

export default function TramitesPage() {
  const [tramites, setTramites] = useState<TramiteResumen[] | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      const resultado = await listarTramites();
      setTramites(resultado);
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
        <p className="text-sm text-red-600">No se pudo cargar la lista de trámites</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Trámites</h1>
        <Link href="/admin/tramites/nuevo" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
          Nuevo trámite
        </Link>
      </div>
      {tramites && tramites.length === 0 ? (
        <p className="text-sm text-gray-500">Todavía no hay trámites cargados</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="p-2">ID</th>
              <th className="p-2">Nombre</th>
              <th className="p-2">Organismo</th>
              <th className="p-2">Categoría</th>
              <th className="p-2">Consultas</th>
              <th className="p-2">Versión</th>
            </tr>
          </thead>
          <tbody>
            {tramites!.map((tramite) => (
              <tr key={tramite.id} className="border-b border-gray-100">
                <td className="p-2">
                  <Link href={`/admin/tramites/${tramite.id}`} className="text-blue-700 hover:underline">
                    {tramite.id}
                  </Link>
                </td>
                <td className="p-2">{tramite.nombre_oficial}</td>
                <td className="p-2">{tramite.organismo}</td>
                <td className="p-2">{tramite.categoria}</td>
                <td className="p-2">{tramite.veces_consultado}</td>
                <td className="p-2">{tramite.numero_version ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Agregar el link de navegación**

En `frontend/app/admin/layout.tsx`, agregar un `<li>` nuevo dentro del `<ul>` de navegación, justo después del de "Chats":

```tsx
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
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/tramites/page.tsx frontend/app/admin/layout.tsx
git commit -m "feat: lista de trámites y link de navegación en el admin"
```

---

### Task 11: Alta de trámite

**Files:**
- Create: `frontend/app/admin/tramites/nuevo/page.tsx`

**Interfaces:**
- Consumes: `TramiteForm` (Task 9); `crearTramite`, `listarOrganismos`, tipo `TramiteDetalleAdmin` de `lib/admin-tramites-api.ts` (Task 7).

- [ ] **Step 1: Crear la página de alta**

Crear `frontend/app/admin/tramites/nuevo/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TramiteForm } from "../../../../components/TramiteForm";
import {
  crearTramite,
  listarOrganismos,
  type TramiteDetalleAdmin,
} from "../../../../lib/admin-tramites-api";

const VALORES_VACIOS: TramiteDetalleAdmin = {
  organismo: "",
  categoria: "",
  nombre_oficial: "",
  descripcion: "",
  objetivo: "",
  requisitos: [],
  pasos: [],
  costo: "",
  modalidad: "",
  duracion: "",
  telefono_contacto: "",
  email_contacto: "",
  problemas_frecuentes: [],
  sinonimos: [],
  keywords: [],
  enlaces_oficiales: [],
  preguntas_frecuentes: [],
};

export default function NuevoTramitePage() {
  const router = useRouter();
  const [organismos, setOrganismos] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarOrganismos()
      .then(setOrganismos)
      .catch(() => setOrganismos([]));
  }, []);

  async function handleGuardar(datos: TramiteDetalleAdmin) {
    setGuardando(true);
    setError(null);
    try {
      const resultado = await crearTramite(datos);
      router.push(`/admin/tramites/${resultado.tramite_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el trámite");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <TramiteForm
      valoresIniciales={VALORES_VACIOS}
      organismosExistentes={organismos}
      guardando={guardando}
      error={error}
      onGuardar={handleGuardar}
    />
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/tramites/nuevo/page.tsx
git commit -m "feat: página de alta de trámites"
```

---

### Task 12: Edición de trámite

**Files:**
- Create: `frontend/app/admin/tramites/[id]/page.tsx`

**Interfaces:**
- Consumes: `TramiteForm` (Task 9); `editarTramite`, `listarOrganismos`, `obtenerTramiteAdmin`, tipo `TramiteDetalleAdmin` de `lib/admin-tramites-api.ts` (Task 7).

- [ ] **Step 1: Crear la página de edición**

Crear `frontend/app/admin/tramites/[id]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { TramiteForm } from "../../../../components/TramiteForm";
import {
  editarTramite,
  listarOrganismos,
  obtenerTramiteAdmin,
  type TramiteDetalleAdmin,
} from "../../../../lib/admin-tramites-api";

export default function EditarTramitePage() {
  const params = useParams<{ id: string }>();
  const [organismos, setOrganismos] = useState<string[]>([]);
  const [tramite, setTramite] = useState<TramiteDetalleAdmin | null | undefined>(undefined);
  const [cargandoError, setCargandoError] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [errorGuardado, setErrorGuardado] = useState<string | null>(null);
  const [confirmacion, setConfirmacion] = useState<string | null>(null);

  useEffect(() => {
    cargar();
  }, [params.id]);

  async function cargar() {
    setCargandoError(false);
    setTramite(undefined);
    try {
      const [detalle, listaOrganismos] = await Promise.all([
        obtenerTramiteAdmin(params.id),
        listarOrganismos(),
      ]);
      setTramite(detalle);
      setOrganismos(listaOrganismos);
    } catch {
      setCargandoError(true);
    }
  }

  async function handleGuardar(datos: TramiteDetalleAdmin) {
    setGuardando(true);
    setErrorGuardado(null);
    setConfirmacion(null);
    try {
      const resultado = await editarTramite(params.id, datos);
      setConfirmacion(
        resultado.cambios
          ? `Guardado como versión ${resultado.numero_version}.`
          : "No había cambios para guardar."
      );
    } catch (err) {
      setErrorGuardado(err instanceof Error ? err.message : "No se pudo guardar el trámite");
    } finally {
      setGuardando(false);
    }
  }

  if (cargandoError) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">No se pudo cargar el trámite</p>
        <button onClick={cargar} className="mt-2 text-sm text-blue-700 underline">
          Reintentar
        </button>
      </div>
    );
  }

  if (tramite === undefined) {
    return <p className="p-4 text-sm text-gray-500">Cargando…</p>;
  }

  if (tramite === null) {
    return <p className="p-4 text-sm text-gray-600">Trámite no encontrado</p>;
  }

  return (
    <div>
      {confirmacion && <p className="p-4 pb-0 text-sm text-green-700">{confirmacion}</p>}
      <TramiteForm
        valoresIniciales={tramite}
        organismosExistentes={organismos}
        guardando={guardando}
        error={errorGuardado}
        onGuardar={handleGuardar}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/admin/tramites/[id]/page.tsx"
git commit -m "feat: página de edición de trámites"
```

---

### Task 13: Verificación manual end-to-end

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Levantar backend y frontend**

Confirmar que Postgres, `uvicorn agent.api:app --reload --port 8000` y `npm run dev` (frontend) están corriendo, y que hay una sesión de admin válida (login en `/admin/login`).

- [ ] **Step 2: Verificar la lista de trámites**

Navegar a `/admin/tramites`.
Expected: si la DB está vacía o casi vacía (ver nota del spec sobre el volumen recreado en la sección anterior), se ve el estado "Todavía no hay trámites cargados"; si hay datos, se ve la tabla con ID/nombre/organismo/categoría/consultas/versión.

- [ ] **Step 3: Crear un trámite nuevo**

Click en "Nuevo trámite", completar organismo (existente o "Otro…"), categoría, nombre oficial, y al menos un requisito. Guardar.
Expected (con una `OPENAI_API_KEY` válida): redirige a `/admin/tramites/{id-generado}` con el ID nuevo (prefijo derivado del organismo). Si la API key es inválida (como puede estar en este entorno): se muestra el mensaje de error de embeddings sin perder lo tipeado.

- [ ] **Step 4: Editar el trámite creado**

Cambiar el campo "Costo" y guardar.
Expected: mensaje de confirmación "Guardado como versión 2."; volver a la lista muestra la versión actualizada.

- [ ] **Step 5: Editar sin cambios**

Entrar de nuevo al mismo trámite y guardar sin modificar nada.
Expected: mensaje "No había cambios para guardar."; la versión sigue siendo 2.

- [ ] **Step 6: Verificar el impacto en el chat público (si hay `OPENAI_API_KEY` válida)**

En el chat público (`/`), preguntar por el trámite editado.
Expected: la respuesta de `obtener_requisitos`/`obtener_costos_modalidad` refleja los valores editados.

- [ ] **Step 7: Correr toda la suite de tests una última vez**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Run: `cd frontend && npx tsc --noEmit`
Expected: PASS en ambos.
