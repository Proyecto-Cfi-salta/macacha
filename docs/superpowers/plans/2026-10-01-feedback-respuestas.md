# Feedback de respuestas (pulgar arriba / abajo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada respuesta del asistente pueda calificarse con 👍/👎 (con motivo y comentario opcional si es 👎) y que ese feedback se vea en el panel admin, con una pantalla de métricas.

**Architecture:** Tabla nueva `feedback_respuestas` (una fila por mensaje del asistente, upsert). Módulo `agent/feedback.py` con la lógica de voto, `POST /feedback` público, y `agent/admin/feedback_repository.py` con las métricas. El `id` del mensaje viaja en el evento `fin` y en el historial. En el frontend, un componente `FeedbackRespuesta` bajo cada respuesta y una pantalla `/admin/feedback`.

**Tech Stack:** FastAPI + psycopg + pytest (backend, Python 3.12, `backend/.venv`); Next.js + React + vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-10-01-feedback-respuestas-design.md`

## Global Constraints

- Motivos (valor → texto), en este orden: `no_respondio` → "No respondió mi pregunta"; `info_incorrecta` → "La información era incorrecta"; `faltaba_info` → "Faltaba información"; `otro_tramite` → "Me mostró otro trámite"; `desactualizada` → "La información estaba desactualizada"; `poco_clara` → "La respuesta no fue clara"; `otro` → "Otro".
- Comentario: máximo 500 caracteres, solo con `util = false`.
- `motivo` y `comentario` solo se aceptan con `util = false`; con `util = true` el endpoint responde 422 y el upsert los pone en `NULL`.
- Un voto posterior sin `motivo`/`comentario` no borra los ya guardados mientras `util` siga en `false`.
- Solo se puede votar un mensaje del asistente, de esa sesión, sin `tool_calls` y con contenido; si no, 404.
- `POST /feedback` es público (sin cookie de admin), igual que `/contacto`.
- El widget del chat se muestra solo cuando el stream terminó (`enviando === false`), el mensaje tiene `id`, `votable`, contenido y no es un error.
- `admin_organismo` solo ve feedback de sesiones que citan trámites de su organismo; `super_admin` ve todo.
- Textos de la interfaz en español rioplatense (voseo), igual que el resto de la app.
- Los comentarios de la interfaz y del código siguen la densidad del código existente (pocos comentarios).
- Backend: ejecutar siempre desde `backend/` con `.venv/bin/pytest`. Los tests usan la base `macacha_test` del `docker compose` (`docker compose up -d postgres`).
- No hacer push ni tocar `frontend/package.json` / `frontend/package-lock.json`.

## Review Focus

Entradas o condiciones que el spec implica pero que ninguna tarea ejercitaría por defecto. Cada línea tiene su test en la tarea indicada.

1. Doble clic rápido en 👍/👎 (dos votos seguidos sobre el mismo mensaje) → queda una sola fila (Task 2).
2. Comentario con solo espacios o saltos de línea → se guarda como `NULL`, no como texto vacío (Task 4).
3. `mensaje_id` que no es un UUID, o comentario de más de 500 caracteres → 422 sin escribir nada (Task 4).
4. Una respuesta que terminó en error (sin evento `fin`) no recibe `id` ni `votable`, por lo tanto no muestra widget (Task 8).
5. Un `admin_organismo` no ve en las métricas votos de sesiones de otros organismos (Task 6).
6. Métricas sin ningún voto → `porcentaje_util` es `null` y la pantalla muestra "—", nunca "NaN%" (Tasks 6 y 11).
7. Historial recargado de una respuesta con 👎 pero sin motivo ni comentario → el widget reabre el selector, no el agradecimiento (Task 7).

---

## File Structure

**Backend — crear**
- `backend/agent/feedback.py` — lista de motivos y operaciones de voto (`mensaje_votable`, `guardar_voto`).
- `backend/agent/admin/feedback_repository.py` — métricas para el panel admin.
- `backend/tests/test_feedback.py` — tests de `agent/feedback.py` y de `POST /feedback`.
- `backend/tests/test_admin_feedback.py` — tests de métricas, detalle y listado admin.

**Backend — modificar**
- `backend/db/schema.sql` — tabla `feedback_respuestas`.
- `backend/tests/conftest.py` — limpiar la tabla nueva.
- `backend/tests/test_schema_smoke.py` — la tabla existe.
- `backend/agent/sessions.py` — `guardar_mensaje` devuelve el `id`; historial con `id`/`votable`/`feedback`.
- `backend/agent/orchestrator.py` — `mensaje_id` en el evento `fin`.
- `backend/tests/test_sessions.py`, `backend/tests/test_orchestrator.py` — tests nuevos y asserts de `fin` actualizados.
- `backend/agent/admin/chats_repository.py` — detalle con `id`/`feedback`, listado con votos, wrappers públicos.
- `backend/agent/api.py` — `POST /feedback`, `GET /admin/feedback/metricas`.

**Frontend — crear**
- `frontend/lib/feedback.ts` — motivos, tipos, estado inicial, `enviarFeedback`.
- `frontend/lib/feedback.test.ts`
- `frontend/lib/feedback-metricas.ts` + `frontend/lib/feedback-metricas.test.ts` — helpers de presentación de métricas.
- `frontend/components/FeedbackRespuesta.tsx`
- `frontend/app/admin/feedback/page.tsx`

**Frontend — modificar**
- `frontend/lib/api.ts` — tipo `MensajeVisible`.
- `frontend/hooks/useChatStream.ts` — `Mensaje`, evento `fin`, reducer exportado, historial.
- `frontend/hooks/useChatStream.test.ts`
- `frontend/components/ChatMessage.tsx`, `frontend/app/page.tsx` — montar el widget.
- `frontend/lib/admin-api.ts`, `frontend/components/ConversacionChat.tsx`, `frontend/app/admin/chats/page.tsx`, `frontend/app/admin/layout.tsx`.

---

### Task 1: `guardar_mensaje` devuelve el id del mensaje

**Files:**
- Modify: `backend/agent/sessions.py:12-34`
- Test: `backend/tests/test_sessions.py`

**Interfaces:**
- Produces: `sessions.guardar_mensaje(conn, session_id, rol, contenido=None, tool_calls=None, tool_call_id=None, proveedor=None) -> str` (el UUID del mensaje como `str`).

- [ ] **Step 1: Write the failing test**

Agregar al final de `backend/tests/test_sessions.py`:

```python
def test_guardar_mensaje_devuelve_el_id_del_mensaje_insertado(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

    mensaje_id = sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="hola")
    db_conn.commit()

    assert isinstance(mensaje_id, str)
    with db_conn.cursor() as cur:
        cur.execute("SELECT contenido FROM mensajes WHERE id = %s", (mensaje_id,))
        assert cur.fetchone()[0] == "hola"
```

- [ ] **Step 2: Run test to verify it fails**

Run (desde `backend/`): `.venv/bin/pytest tests/test_sessions.py::test_guardar_mensaje_devuelve_el_id_del_mensaje_insertado -v`
Expected: FAIL (`mensaje_id` es `None`, `isinstance(None, str)` falla).

- [ ] **Step 3: Write minimal implementation**

En `backend/agent/sessions.py`, reemplazar la función `guardar_mensaje` completa por:

```python
def guardar_mensaje(
    conn,
    session_id: str,
    rol: str,
    contenido: str | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    proveedor: str | None = None,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mensajes (session_id, rol, contenido, tool_calls, tool_call_id, proveedor)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                session_id,
                rol,
                contenido,
                json.dumps(tool_calls) if tool_calls is not None else None,
                tool_call_id,
                proveedor,
            ),
        )
        return str(cur.fetchone()[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sessions.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/sessions.py backend/tests/test_sessions.py
git commit -m "feat: guardar_mensaje devuelve el id del mensaje insertado"
```

---

### Task 2: Tabla `feedback_respuestas` y módulo `agent/feedback.py`

**Files:**
- Modify: `backend/db/schema.sql` (al final)
- Modify: `backend/tests/conftest.py:25-35`
- Modify: `backend/tests/test_schema_smoke.py:14-23`
- Create: `backend/agent/feedback.py`
- Test: `backend/tests/test_feedback.py`

**Interfaces:**
- Consumes: `sessions.guardar_mensaje(...) -> str` (Task 1).
- Produces:
  - `feedback.MOTIVOS: tuple[str, ...]` y `feedback.MotivoFeedback` (un `Literal` de esos valores).
  - `feedback.mensaje_votable(conn, session_id: str, mensaje_id: str) -> bool`
  - `feedback.guardar_voto(conn, session_id: str, mensaje_id: str, util: bool, motivo: str | None = None, comentario: str | None = None) -> None`
  - `feedback.obtener_voto(conn, mensaje_id: str) -> dict | None` con claves `util`, `motivo`, `comentario`.

- [ ] **Step 1: Agregar la tabla al schema y aplicarla a la base de test**

Agregar al final de `backend/db/schema.sql`:

```sql

CREATE TABLE IF NOT EXISTS feedback_respuestas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mensaje_id UUID NOT NULL UNIQUE REFERENCES mensajes(id),
    session_id UUID NOT NULL REFERENCES sesiones(id),
    util BOOLEAN NOT NULL,
    motivo TEXT,
    comentario TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT feedback_motivo_valido CHECK (
        motivo IS NULL OR motivo IN (
            'no_respondio', 'info_incorrecta', 'faltaba_info', 'otro_tramite',
            'desactualizada', 'poco_clara', 'otro'
        )
    ),
    CONSTRAINT feedback_comentario_largo CHECK (comentario IS NULL OR char_length(comentario) <= 500),
    CONSTRAINT feedback_detalle_solo_si_no_util CHECK (
        util = false OR (motivo IS NULL AND comentario IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS feedback_respuestas_session_idx ON feedback_respuestas (session_id);
```

Aplicarlo a la base de test (es idempotente):

Run (desde la raíz del repo): `docker compose up -d postgres && docker exec -i macacha-postgres-1 psql -U macacha -d macacha_test < backend/db/schema.sql`
Expected: termina sin errores (`CREATE TABLE`, `CREATE INDEX`).

- [ ] **Step 2: Limpiar la tabla nueva en los tests**

En `backend/tests/conftest.py`, dentro de `_clean`, agregar como **primera** sentencia (antes de `DELETE FROM mensajes`, por la clave foránea):

```python
            cur.execute("DELETE FROM feedback_respuestas")
```

En `backend/tests/test_schema_smoke.py`, agregar `"feedback_respuestas",` al set de tablas esperadas (después de `"solicitudes_contacto",`).

- [ ] **Step 3: Write the failing tests**

Crear `backend/tests/test_feedback.py`:

```python
import uuid

import pytest
from psycopg.errors import CheckViolation

from agent import feedback, sessions


def _respuesta(conn, session_id=None, **kwargs):
    session_id = session_id or str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    mensaje_id = sessions.guardar_mensaje(
        conn, session_id, rol="assistant", contenido="respuesta", **kwargs
    )
    conn.commit()
    return session_id, mensaje_id


def _filas(conn, mensaje_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT util, motivo, comentario FROM feedback_respuestas WHERE mensaje_id = %s",
            (mensaje_id,),
        )
        return cur.fetchall()


def test_motivos_son_la_lista_cerrada_del_spec():
    assert feedback.MOTIVOS == (
        "no_respondio",
        "info_incorrecta",
        "faltaba_info",
        "otro_tramite",
        "desactualizada",
        "poco_clara",
        "otro",
    )


def test_mensaje_votable_true_para_respuesta_final_del_asistente(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    assert feedback.mensaje_votable(db_conn, session_id, mensaje_id) is True


def test_mensaje_votable_false_para_mensaje_de_usuario(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    mensaje_id = sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    assert feedback.mensaje_votable(db_conn, session_id, mensaje_id) is False


def test_mensaje_votable_false_para_mensaje_intermedio_con_tool_calls(db_conn, clean_db):
    tool_calls = [{"id": "c1", "type": "function", "function": {"name": "buscar_tramite", "arguments": "{}"}}]
    session_id, mensaje_id = _respuesta(db_conn, tool_calls=tool_calls)

    assert feedback.mensaje_votable(db_conn, session_id, mensaje_id) is False


def test_mensaje_votable_false_si_pertenece_a_otra_sesion(db_conn, clean_db):
    _, mensaje_id = _respuesta(db_conn)
    otra_sesion = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, otra_sesion)
    db_conn.commit()

    assert feedback.mensaje_votable(db_conn, otra_sesion, mensaje_id) is False


def test_guardar_voto_positivo_crea_la_fila(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=True)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(True, None, None)]


def test_guardar_voto_negativo_con_motivo_y_comentario(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    feedback.guardar_voto(
        db_conn, session_id, mensaje_id, util=False, motivo="faltaba_info", comentario="Faltó el costo"
    )
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, "faltaba_info", "Faltó el costo")]


def test_doble_voto_seguido_deja_una_sola_fila(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, None, None)]


def test_voto_negativo_sin_detalle_no_borra_motivo_ni_comentario_guardados(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="poco_clara", comentario="No entendí")

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, "poco_clara", "No entendí")]


def test_cambiar_a_positivo_limpia_motivo_y_comentario(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="otro", comentario="x")

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=True)
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(True, None, None)]


def test_cambiar_de_positivo_a_negativo_actualiza_la_misma_fila(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=True)

    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="otro_tramite")
    db_conn.commit()

    assert _filas(db_conn, mensaje_id) == [(False, "otro_tramite", None)]


def test_la_base_rechaza_un_motivo_fuera_de_la_lista(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    with pytest.raises(CheckViolation):
        feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="inventado")


def test_obtener_voto_devuelve_none_si_no_hay_voto(db_conn, clean_db):
    _, mensaje_id = _respuesta(db_conn)

    assert feedback.obtener_voto(db_conn, mensaje_id) is None


def test_obtener_voto_devuelve_el_voto_guardado(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)
    feedback.guardar_voto(db_conn, session_id, mensaje_id, util=False, motivo="otro", comentario="c")
    db_conn.commit()

    assert feedback.obtener_voto(db_conn, mensaje_id) == {
        "util": False,
        "motivo": "otro",
        "comentario": "c",
    }
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_feedback.py -v`
Expected: FAIL en la colección (`ImportError: cannot import name 'feedback' from 'agent'`).

- [ ] **Step 5: Write minimal implementation**

Crear `backend/agent/feedback.py`:

```python
from typing import Literal

MOTIVOS = (
    "no_respondio",
    "info_incorrecta",
    "faltaba_info",
    "otro_tramite",
    "desactualizada",
    "poco_clara",
    "otro",
)

MotivoFeedback = Literal[MOTIVOS]  # type: ignore[valid-type]


def mensaje_votable(conn, session_id: str, mensaje_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM mensajes
            WHERE id = %s AND session_id = %s AND rol = 'assistant'
              AND tool_calls IS NULL AND contenido IS NOT NULL
            """,
            (mensaje_id, session_id),
        )
        return cur.fetchone() is not None


def guardar_voto(
    conn,
    session_id: str,
    mensaje_id: str,
    util: bool,
    motivo: str | None = None,
    comentario: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feedback_respuestas (mensaje_id, session_id, util, motivo, comentario)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (mensaje_id) DO UPDATE SET
                util = EXCLUDED.util,
                motivo = CASE WHEN EXCLUDED.util THEN NULL
                              ELSE COALESCE(EXCLUDED.motivo, feedback_respuestas.motivo) END,
                comentario = CASE WHEN EXCLUDED.util THEN NULL
                                  ELSE COALESCE(EXCLUDED.comentario, feedback_respuestas.comentario) END,
                updated_at = now()
            """,
            (mensaje_id, session_id, util, motivo, comentario),
        )


def obtener_voto(conn, mensaje_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT util, motivo, comentario FROM feedback_respuestas WHERE mensaje_id = %s",
            (mensaje_id,),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    util, motivo, comentario = fila
    return {"util": util, "motivo": motivo, "comentario": comentario}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_feedback.py tests/test_schema_smoke.py -v`
Expected: todos PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/db/schema.sql backend/tests/conftest.py backend/tests/test_schema_smoke.py backend/agent/feedback.py backend/tests/test_feedback.py
git commit -m "feat: tabla feedback_respuestas y módulo de votos"
```

---

### Task 3: El evento `fin` incluye `mensaje_id`

**Files:**
- Modify: `backend/agent/orchestrator.py:93-117` y `backend/agent/orchestrator.py:162-171`
- Modify: `backend/tests/test_orchestrator.py` (4 asserts + tests nuevos)

**Interfaces:**
- Consumes: `sessions.guardar_mensaje(...) -> str` (Task 1).
- Produces: el último evento de `procesar_turno` es `{"tipo": "fin", "fuentes": ..., "candidatos_ambiguos": ..., "sugerir_contacto": ..., "mensaje_id": str}`, donde `mensaje_id` es el `id` de la respuesta final del asistente guardada.

- [ ] **Step 1: Actualizar los 4 asserts existentes y escribir los tests nuevos**

En `backend/tests/test_orchestrator.py`, agregar este helper justo debajo de `_armar_tramite_de_prueba` (antes del primer test):

```python
def _fin_sin_mensaje_id(eventos):
    fin = dict(eventos[-1])
    assert isinstance(fin.pop("mensaje_id"), str)
    return fin
```

Reemplazar en todo el archivo `assert eventos[-1] == {` por `assert _fin_sin_mensaje_id(eventos) == {` (hay 4 ocurrencias: líneas ~70, 122, 222 y 432):

Run: `sed -i 's/assert eventos\[-1\] == {/assert _fin_sin_mensaje_id(eventos) == {/' tests/test_orchestrator.py && grep -c "_fin_sin_mensaje_id(eventos) == {" tests/test_orchestrator.py`
Expected: imprime `4`.

Agregar al final de `backend/tests/test_orchestrator.py`:

```python
def test_fin_incluye_el_id_de_la_respuesta_final_guardada(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient([{"role": "assistant", "content": "Hola", "tool_calls": None}])

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM mensajes WHERE session_id = %s AND rol = 'assistant' ORDER BY orden DESC LIMIT 1",
            (session_id,),
        )
        id_guardado = str(cur.fetchone()[0])
    assert eventos[-1]["mensaje_id"] == id_guardado


def test_fin_por_iteraciones_agotadas_incluye_el_id_del_mensaje_de_cierre(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    llamada = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "ofrecer_contacto_humano", "arguments": "{}"},
    }
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": None, "tool_calls": [llamada]} for _ in range(5)]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is True
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT id, contenido FROM mensajes WHERE session_id = %s AND rol = 'assistant' ORDER BY orden DESC LIMIT 1",
            (session_id,),
        )
        id_guardado, contenido = cur.fetchone()
    assert contenido.startswith("No pude resolver tu consulta")
    assert eventos[-1]["mensaje_id"] == str(id_guardado)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_orchestrator.py -v`
Expected: FAIL en los 4 tests con `_fin_sin_mensaje_id` (`KeyError: 'mensaje_id'`) y en los 2 nuevos.

- [ ] **Step 3: Write minimal implementation**

En `backend/agent/orchestrator.py`, en el bloque `if not tool_calls:`, reemplazar:

```python
            sessions.guardar_mensaje(
                conn,
                session_id,
                rol="assistant",
                contenido=contenido,
                proveedor=proveedor,
            )
            yield {
                "tipo": "fin",
                "fuentes": _armar_fuentes(conn, tramites_citados),
                "candidatos_ambiguos": (
                    [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
                ),
                "sugerir_contacto": sugerir_contacto,
            }
            return
```

por:

```python
            mensaje_id = sessions.guardar_mensaje(
                conn,
                session_id,
                rol="assistant",
                contenido=contenido,
                proveedor=proveedor,
            )
            yield {
                "tipo": "fin",
                "fuentes": _armar_fuentes(conn, tramites_citados),
                "candidatos_ambiguos": (
                    [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
                ),
                "sugerir_contacto": sugerir_contacto,
                "mensaje_id": mensaje_id,
            }
            return
```

Y al final de la función, reemplazar:

```python
    sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield {"tipo": "texto", "delta": mensaje_agotado}
    yield {
        "tipo": "fin",
        "fuentes": _armar_fuentes(conn, tramites_citados),
        "candidatos_ambiguos": (
            [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
        ),
        "sugerir_contacto": True,
    }
```

por:

```python
    mensaje_id = sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield {"tipo": "texto", "delta": mensaje_agotado}
    yield {
        "tipo": "fin",
        "fuentes": _armar_fuentes(conn, tramites_citados),
        "candidatos_ambiguos": (
            [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
        ),
        "sugerir_contacto": True,
        "mensaje_id": mensaje_id,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_orchestrator.py tests/test_api.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: el evento fin del chat incluye el id de la respuesta"
```

---

### Task 4: `POST /feedback`

**Files:**
- Modify: `backend/agent/api.py` (imports y un endpoint nuevo después de `/contacto`)
- Test: `backend/tests/test_feedback.py` (agregar)

**Interfaces:**
- Consumes: `feedback.mensaje_votable`, `feedback.guardar_voto`, `feedback.MotivoFeedback` (Task 2).
- Produces: `POST /feedback` con cuerpo `{"session_id": uuid, "mensaje_id": uuid, "util": bool, "motivo": str | null, "comentario": str | null}`; responde `{"ok": true}`, 404 si el mensaje no es votable en esa sesión, 422 si el cuerpo es inválido.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `backend/tests/test_feedback.py`. Primero ampliar los imports del archivo (reemplazar el bloque de imports inicial por):

```python
import uuid

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation

from agent import api, feedback, sessions
from agent.api import obtener_pool
```

Y agregar al final del archivo:

```python
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


def _post_feedback(conn, cuerpo):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(conn)
    try:
        return TestClient(api.app).post("/feedback", json=cuerpo)
    finally:
        api.app.dependency_overrides.clear()


def test_post_feedback_positivo_guarda_el_voto(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": mensaje_id, "util": True}
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}
    assert _filas(db_conn, mensaje_id) == [(True, None, None)]


def test_post_feedback_negativo_con_motivo_y_comentario(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {
            "session_id": session_id,
            "mensaje_id": mensaje_id,
            "util": False,
            "motivo": "desactualizada",
            "comentario": "El costo cambió",
        },
    )

    assert respuesta.status_code == 200
    assert _filas(db_conn, mensaje_id) == [(False, "desactualizada", "El costo cambió")]


def test_post_feedback_comentario_solo_con_espacios_se_guarda_como_null(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": False, "comentario": "  \n  "},
    )

    assert respuesta.status_code == 200
    assert _filas(db_conn, mensaje_id) == [(False, None, None)]


def test_post_feedback_mensaje_de_otra_sesion_devuelve_404_y_no_escribe(db_conn, clean_db):
    _, mensaje_id = _respuesta(db_conn)
    otra_sesion = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, otra_sesion)
    db_conn.commit()

    respuesta = _post_feedback(
        db_conn, {"session_id": otra_sesion, "mensaje_id": mensaje_id, "util": True}
    )

    assert respuesta.status_code == 404
    assert _filas(db_conn, mensaje_id) == []


def test_post_feedback_mensaje_inexistente_devuelve_404(db_conn, clean_db):
    session_id, _ = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": str(uuid.uuid4()), "util": True}
    )

    assert respuesta.status_code == 404


def test_post_feedback_motivo_con_voto_positivo_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": True, "motivo": "otro"},
    )

    assert respuesta.status_code == 422
    assert _filas(db_conn, mensaje_id) == []


def test_post_feedback_comentario_con_voto_positivo_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": True, "comentario": "gracias"},
    )

    assert respuesta.status_code == 422


def test_post_feedback_motivo_fuera_de_la_lista_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": False, "motivo": "inventado"},
    )

    assert respuesta.status_code == 422


def test_post_feedback_comentario_de_mas_de_500_caracteres_devuelve_422(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn,
        {"session_id": session_id, "mensaje_id": mensaje_id, "util": False, "comentario": "a" * 501},
    )

    assert respuesta.status_code == 422
    assert _filas(db_conn, mensaje_id) == []


def test_post_feedback_mensaje_id_que_no_es_uuid_devuelve_422(db_conn, clean_db):
    session_id, _ = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": "no-es-un-uuid", "util": True}
    )

    assert respuesta.status_code == 422


def test_post_feedback_no_requiere_cookie_de_admin(db_conn, clean_db):
    session_id, mensaje_id = _respuesta(db_conn)

    respuesta = _post_feedback(
        db_conn, {"session_id": session_id, "mensaje_id": mensaje_id, "util": True}
    )

    assert respuesta.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_feedback.py -k post_feedback -v`
Expected: FAIL (los endpoints devuelven 404/405 porque `/feedback` no existe).

- [ ] **Step 3: Write minimal implementation**

En `backend/agent/api.py`, cambiar la línea `from agent import mail, sessions` por:

```python
from agent import feedback, mail, sessions
```

Agregar justo después del endpoint `crear_solicitud_contacto` (antes de `class LoginRequest`):

```python
class FeedbackRequest(BaseModel):
    session_id: uuid.UUID
    mensaje_id: uuid.UUID
    util: bool
    motivo: feedback.MotivoFeedback | None = None
    comentario: str | None = Field(default=None, max_length=500)


@app.post("/feedback")
def registrar_feedback(request: FeedbackRequest, pool=Depends(obtener_pool)):
    comentario = (request.comentario or "").strip() or None
    if request.util and (request.motivo is not None or comentario is not None):
        raise HTTPException(
            status_code=422, detail="El motivo y el comentario solo aplican a un voto negativo"
        )

    with pool.connection() as conn:
        if not feedback.mensaje_votable(conn, str(request.session_id), str(request.mensaje_id)):
            raise HTTPException(status_code=404, detail="Respuesta no encontrada")
        feedback.guardar_voto(
            conn,
            str(request.session_id),
            str(request.mensaje_id),
            request.util,
            request.motivo,
            comentario,
        )
        conn.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_feedback.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/api.py backend/tests/test_feedback.py
git commit -m "feat: endpoint público POST /feedback"
```

---

### Task 5: El historial del chat incluye `id`, `votable` y `feedback`

**Files:**
- Modify: `backend/agent/sessions.py:60-74` (`obtener_mensajes_visibles`)
- Test: `backend/tests/test_sessions.py`

**Interfaces:**
- Consumes: tabla `feedback_respuestas` (Task 2).
- Produces: cada elemento de `sessions.obtener_mensajes_visibles(conn, session_id)` y de `GET /sesiones/{id}/mensajes` suma `id: str`, `votable: bool` (verdadero solo para mensajes del asistente sin `tool_calls`) y `feedback: {"util": bool, "motivo": str | None, "comentario": str | None} | None`. Siguen presentes `rol`, `contenido`, `creado_en`.

- [ ] **Step 1: Write the failing tests**

Agregar al final de `backend/tests/test_sessions.py`:

```python
def test_mensajes_visibles_incluyen_id_votable_y_feedback_nulo(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    id_usuario = sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    id_asistente = sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta")
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert visibles[0]["id"] == id_usuario
    assert visibles[0]["votable"] is False
    assert visibles[0]["feedback"] is None
    assert visibles[1]["id"] == id_asistente
    assert visibles[1]["votable"] is True
    assert visibles[1]["feedback"] is None


def test_mensajes_visibles_incluyen_el_voto_guardado(db_conn, clean_db):
    from agent import feedback

    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    id_asistente = sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta")
    feedback.guardar_voto(db_conn, session_id, id_asistente, util=False, motivo="poco_clara", comentario="no entendí")
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert visibles[0]["feedback"] == {"util": False, "motivo": "poco_clara", "comentario": "no entendí"}


def test_mensaje_intermedio_con_contenido_y_tool_calls_no_es_votable(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(
        db_conn,
        session_id,
        rol="assistant",
        contenido="Dejame buscar eso…",
        tool_calls=[{"id": "c1", "type": "function", "function": {"name": "buscar_tramite", "arguments": "{}"}}],
    )
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)

    assert visibles[0]["votable"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sessions.py -k "visibles or intermedio" -v`
Expected: FAIL (`KeyError: 'id'`).

- [ ] **Step 3: Write minimal implementation**

En `backend/agent/sessions.py`, reemplazar `obtener_mensajes_visibles` completa por:

```python
def obtener_mensajes_visibles(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.rol, m.contenido, m.created_at,
                   (m.rol = 'assistant' AND m.tool_calls IS NULL) AS votable,
                   f.util, f.motivo, f.comentario
            FROM mensajes m
            LEFT JOIN feedback_respuestas f ON f.mensaje_id = m.id
            WHERE m.session_id = %s AND m.rol IN ('user', 'assistant') AND m.contenido IS NOT NULL
            ORDER BY m.orden
            """,
            (session_id,),
        )
        return [
            {
                "id": str(mensaje_id),
                "rol": rol,
                "contenido": contenido,
                "creado_en": creado_en.isoformat(),
                "votable": votable,
                "feedback": (
                    None if util is None else {"util": util, "motivo": motivo, "comentario": comentario}
                ),
            }
            for mensaje_id, rol, contenido, creado_en, votable, util, motivo, comentario in cur.fetchall()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sessions.py tests/test_api.py tests/test_contacto_api.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/sessions.py backend/tests/test_sessions.py
git commit -m "feat: el historial del chat expone id, votable y feedback"
```

---

### Task 6: Panel admin (backend): detalle, listado y métricas

**Files:**
- Modify: `backend/agent/admin/chats_repository.py` (detalle, listado, wrappers públicos)
- Create: `backend/agent/admin/feedback_repository.py`
- Modify: `backend/agent/api.py` (import y endpoint de métricas)
- Test: `backend/tests/test_admin_feedback.py`

**Interfaces:**
- Consumes: `feedback.guardar_voto` (Task 2); `chats_repository` existente.
- Produces:
  - `chats_repository.obtener_mensajes_completos` suma `id` a **todos** los mensajes y `feedback` (`{util, motivo, comentario}` o `None`) a los mensajes con rol `assistant`.
  - `chats_repository.listar_sesiones` y `listar_sesiones_de_organismo` suman `votos_positivos: int` y `votos_negativos: int` a cada sesión.
  - `chats_repository.tramites_citados_por_sesion(conn, session_ids: list[str]) -> dict[str, list[str]]` y `chats_repository.organismos_de_tramites(conn, citados_por_sesion: dict[str, list[str]]) -> dict[str, int]` (wrappers públicos de los helpers privados existentes).
  - `feedback_repository.calcular_metricas(conn, organismo_id: int | None) -> dict` con claves: `total`, `positivos`, `negativos`, `porcentaje_util` (`float | None`), `motivos` (`[{"motivo": str, "cantidad": int}]` de mayor a menor), `sin_motivo` (`int`), `por_dia` (`[{"fecha": "AAAA-MM-DD", "positivos": int, "negativos": int}]` ascendente), `comentarios_recientes` (hasta 20 de `{"session_id", "mensaje_id", "motivo", "comentario", "creado_en"}`, más nuevos primero) y `por_organismo` (`[{"organismo": str, "positivos": int, "negativos": int}]` de mayor a menor total).
  - `GET /admin/feedback/metricas` (requiere admin) devuelve ese dict.

- [ ] **Step 1: Write the failing tests**

Crear `backend/tests/test_admin_feedback.py`:

```python
import uuid

from fastapi.testclient import TestClient

from agent import api, feedback, sessions
from agent.admin import chats_repository, feedback_repository
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


def _organismo(conn, nombre):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES (%s) RETURNING id", (nombre,))
        return cur.fetchone()[0]


def _tramite(conn, tramite_id, organismo_id):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tramites (id, organismo_id, categoria, nombre_oficial) VALUES (%s, %s, '', %s)",
            (tramite_id, organismo_id, tramite_id),
        )


def _cita(tramite_id):
    return [
        {
            "id": f"call_{tramite_id}",
            "type": "function",
            "function": {"name": "obtener_requisitos", "arguments": f'{{"tramite_id": "{tramite_id}"}}'},
        }
    ]


def _sesion_votada(conn, util, motivo=None, comentario=None, tramite_id=None):
    """Crea una sesión con una respuesta final votada; devuelve (session_id, mensaje_id)."""
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(conn, session_id)
    if tramite_id:
        sessions.guardar_mensaje(conn, session_id, rol="assistant", tool_calls=_cita(tramite_id))
    mensaje_id = sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido="respuesta")
    feedback.guardar_voto(conn, session_id, mensaje_id, util, motivo, comentario)
    conn.commit()
    return session_id, mensaje_id


# ---------- detalle y listado ----------


def test_detalle_incluye_id_y_feedback_en_mensajes_del_asistente(db_conn, clean_db):
    session_id, mensaje_id = _sesion_votada(db_conn, False, "otro", "mal")
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    asistente = next(m for m in mensajes if m.get("contenido") == "respuesta")
    usuario = next(m for m in mensajes if m["rol"] == "user")
    assert asistente["id"] == mensaje_id
    assert asistente["feedback"] == {"util": False, "motivo": "otro", "comentario": "mal"}
    assert "id" in usuario
    assert "feedback" not in usuario


def test_detalle_feedback_es_none_si_el_asistente_no_fue_votado(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="respuesta")
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    assert mensajes[0]["feedback"] is None


def test_listado_incluye_votos_por_sesion(db_conn, clean_db):
    session_id, _ = _sesion_votada(db_conn, False)
    sin_votos = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, sin_votos)
    db_conn.commit()

    sesiones = {s["id"]: s for s in chats_repository.listar_sesiones(db_conn, page=1, page_size=20)}

    assert (sesiones[session_id]["votos_positivos"], sesiones[session_id]["votos_negativos"]) == (0, 1)
    assert (sesiones[sin_votos]["votos_positivos"], sesiones[sin_votos]["votos_negativos"]) == (0, 0)


def test_listado_de_organismo_incluye_votos_por_sesion(db_conn, clean_db):
    organismo = _organismo(db_conn, "Registro Civil")
    _tramite(db_conn, "RC-0001", organismo)
    session_id, _ = _sesion_votada(db_conn, True, tramite_id="RC-0001")

    sesiones, total = chats_repository.listar_sesiones_de_organismo(db_conn, organismo, page=1, page_size=20)

    assert total == 1
    assert (sesiones[0]["votos_positivos"], sesiones[0]["votos_negativos"]) == (1, 0)


# ---------- métricas ----------


def test_metricas_sin_votos_devuelven_ceros_y_porcentaje_nulo(db_conn, clean_db):
    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert metricas["total"] == 0
    assert metricas["positivos"] == 0
    assert metricas["negativos"] == 0
    assert metricas["porcentaje_util"] is None
    assert metricas["motivos"] == []
    assert metricas["sin_motivo"] == 0
    assert metricas["por_dia"] == []
    assert metricas["comentarios_recientes"] == []
    assert metricas["por_organismo"] == []


def test_metricas_totales_y_porcentaje(db_conn, clean_db):
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, False, "faltaba_info")

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert (metricas["total"], metricas["positivos"], metricas["negativos"]) == (4, 3, 1)
    assert metricas["porcentaje_util"] == 75.0


def test_metricas_motivos_ordenados_y_sin_motivo(db_conn, clean_db):
    _sesion_votada(db_conn, False, "poco_clara")
    _sesion_votada(db_conn, False, "faltaba_info")
    _sesion_votada(db_conn, False, "faltaba_info")
    _sesion_votada(db_conn, False)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert metricas["motivos"] == [
        {"motivo": "faltaba_info", "cantidad": 2},
        {"motivo": "poco_clara", "cantidad": 1},
    ]
    assert metricas["sin_motivo"] == 1


def test_metricas_comentarios_recientes_solo_negativos_con_comentario(db_conn, clean_db):
    _sesion_votada(db_conn, False, "otro", "Primer comentario")
    _sesion_votada(db_conn, False, "otro")
    _sesion_votada(db_conn, True)
    _, ultimo = _sesion_votada(db_conn, False, "poco_clara", "Segundo comentario")

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    comentarios = metricas["comentarios_recientes"]
    assert [c["comentario"] for c in comentarios] == ["Segundo comentario", "Primer comentario"]
    assert comentarios[0]["mensaje_id"] == ultimo
    assert comentarios[0]["motivo"] == "poco_clara"


def test_metricas_por_dia_agrupa_votos(db_conn, clean_db):
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, False)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    assert len(metricas["por_dia"]) == 1
    assert metricas["por_dia"][0]["positivos"] == 1
    assert metricas["por_dia"][0]["negativos"] == 1


def test_metricas_por_organismo_cuenta_en_cada_organismo_citado_y_sin_tramite(db_conn, clean_db):
    rc = _organismo(db_conn, "Registro Civil")
    tr = _organismo(db_conn, "Secretaría de Trabajo")
    _tramite(db_conn, "RC-0001", rc)
    _tramite(db_conn, "TR-0001", tr)
    _sesion_votada(db_conn, True, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, tramite_id="TR-0001")
    _sesion_votada(db_conn, True)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=None)

    por_organismo = {f["organismo"]: (f["positivos"], f["negativos"]) for f in metricas["por_organismo"]}
    assert por_organismo == {
        "Registro Civil": (1, 1),
        "Secretaría de Trabajo": (0, 1),
        "Sin trámite": (1, 0),
    }
    assert metricas["por_organismo"][0]["organismo"] == "Registro Civil"


def test_metricas_de_admin_organismo_solo_cuentan_sus_sesiones(db_conn, clean_db):
    rc = _organismo(db_conn, "Registro Civil")
    tr = _organismo(db_conn, "Secretaría de Trabajo")
    _tramite(db_conn, "RC-0001", rc)
    _tramite(db_conn, "TR-0001", tr)
    _sesion_votada(db_conn, True, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, "otro", "Comentario de trabajo", tramite_id="TR-0001")
    _sesion_votada(db_conn, False)

    metricas = feedback_repository.calcular_metricas(db_conn, organismo_id=rc)

    assert (metricas["total"], metricas["positivos"], metricas["negativos"]) == (1, 1, 0)
    assert metricas["comentarios_recientes"] == []
    assert metricas["por_organismo"] == [{"organismo": "Registro Civil", "positivos": 1, "negativos": 0}]


# ---------- endpoint ----------


def _login(client, conn, rol="super_admin", organismo_id=None, email="admin@macacha.gob.ar"):
    admin_repository.crear_admin(conn, email, admin_security.hash_password("secreta123"), rol, organismo_id)
    conn.commit()
    client.post("/admin/login", json={"email": email, "password": "secreta123"})


def test_endpoint_metricas_requiere_autenticacion(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    try:
        respuesta = TestClient(api.app, base_url="https://testserver").get("/admin/feedback/metricas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 401


def test_endpoint_metricas_devuelve_el_resumen_para_super_admin(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    _sesion_votada(db_conn, True)
    _sesion_votada(db_conn, False, "otro", "mal")
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _login(client, db_conn)
        respuesta = client.get("/admin/feedback/metricas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["total"], cuerpo["positivos"], cuerpo["negativos"]) == (2, 1, 1)
    assert cuerpo["porcentaje_util"] == 50.0


def test_endpoint_metricas_filtra_por_organismo_del_admin(db_conn, clean_db, monkeypatch):
    monkeypatch.setenv("ADMIN_JWT_SECRET", "secreto-de-test")
    rc = _organismo(db_conn, "Registro Civil")
    tr = _organismo(db_conn, "Secretaría de Trabajo")
    _tramite(db_conn, "RC-0001", rc)
    _tramite(db_conn, "TR-0001", tr)
    _sesion_votada(db_conn, True, tramite_id="RC-0001")
    _sesion_votada(db_conn, False, tramite_id="TR-0001")
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app, base_url="https://testserver")
    try:
        _login(client, db_conn, rol="admin_organismo", organismo_id=rc, email="rc@macacha.gob.ar")
        respuesta = client.get("/admin/feedback/metricas")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_admin_feedback.py -v`
Expected: FAIL en la colección (`ImportError: cannot import name 'feedback_repository'`).

- [ ] **Step 3: Implementar cambios en `chats_repository.py`**

En `backend/agent/admin/chats_repository.py`:

(a) Reemplazar la consulta y el armado de `obtener_mensajes_completos` (la función completa) por:

```python
def obtener_mensajes_completos(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id, m.rol, m.contenido, m.tool_calls, m.tool_call_id, m.proveedor, m.created_at,
                   f.util, f.motivo, f.comentario
            FROM mensajes m
            LEFT JOIN feedback_respuestas f ON f.mensaje_id = m.id
            WHERE m.session_id = %s
            ORDER BY m.orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    mensajes = []
    for mensaje_id, rol, contenido, tool_calls, tool_call_id, proveedor, creado_en, util, motivo, comentario in filas:
        mensaje: dict = {
            "id": str(mensaje_id),
            "rol": rol,
            "contenido": contenido,
            "creado_en": creado_en.isoformat(),
        }
        if tool_calls is not None:
            mensaje["tool_calls"] = tool_calls
        if tool_call_id is not None:
            mensaje["tool_call_id"] = tool_call_id
        if proveedor is not None:
            mensaje["proveedor"] = proveedor
        if rol == "assistant":
            mensaje["feedback"] = (
                None if util is None else {"util": util, "motivo": motivo, "comentario": comentario}
            )
        mensajes.append(mensaje)
    return mensajes
```

(b) Agregar, junto a los otros helpers privados (por ejemplo debajo de `_contar_mensajes_visibles_batch`):

```python
def _contar_votos_batch(conn, session_ids: list[str]) -> dict[str, tuple[int, int]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, COUNT(*) FILTER (WHERE util), COUNT(*) FILTER (WHERE NOT util)
            FROM feedback_respuestas
            WHERE session_id = ANY(%s)
            GROUP BY session_id
            """,
            (session_ids,),
        )
        return {str(session_id): (positivos, negativos) for session_id, positivos, negativos in cur.fetchall()}
```

(c) En `listar_sesiones`, después de `citados = _extraer_tramites_citados_batch(conn, session_ids)` agregar `votos = _contar_votos_batch(conn, session_ids)` y, dentro del diccionario de cada sesión, después de `"tramites_citados": citados.get(str(sesion_id), []),` agregar:

```python
            "votos_positivos": votos.get(str(sesion_id), (0, 0))[0],
            "votos_negativos": votos.get(str(sesion_id), (0, 0))[1],
```

(d) En `listar_sesiones_de_organismo`, después de `ultimos = _obtener_ultimo_mensaje_batch(conn, ids_pagina)` agregar `votos = _contar_votos_batch(conn, ids_pagina)` y agregar las mismas dos claves al diccionario de cada sesión de `resultado`.

(e) Agregar los wrappers públicos al final del archivo:

```python
def tramites_citados_por_sesion(conn, session_ids: list[str]) -> dict[str, list[str]]:
    return _extraer_tramites_citados_batch(conn, session_ids)


def organismos_de_tramites(conn, citados_por_sesion: dict[str, list[str]]) -> dict[str, int]:
    return _organismos_de_tramites(conn, citados_por_sesion)
```

- [ ] **Step 4: Crear `feedback_repository.py`**

Crear `backend/agent/admin/feedback_repository.py`:

```python
from collections import Counter

from agent.admin import chats_repository

MAX_COMENTARIOS_RECIENTES = 20
SIN_TRAMITE = "Sin trámite"


def calcular_metricas(conn, organismo_id: int | None) -> dict:
    votos = _listar_votos(conn)
    citados = chats_repository.tramites_citados_por_sesion(
        conn, sorted({voto["session_id"] for voto in votos})
    )
    organismo_de_tramite = chats_repository.organismos_de_tramites(conn, citados)
    nombres = _nombres_de_organismos(conn)

    def organismos_de(session_id: str) -> set[int]:
        return {
            organismo_de_tramite[tramite_id]
            for tramite_id in citados.get(session_id, [])
            if tramite_id in organismo_de_tramite
        }

    if organismo_id is not None:
        votos = [voto for voto in votos if organismo_id in organismos_de(voto["session_id"])]

    positivos = sum(1 for voto in votos if voto["util"])
    negativos = len(votos) - positivos
    negativos_con_motivo = Counter(
        voto["motivo"] for voto in votos if not voto["util"] and voto["motivo"] is not None
    )

    por_dia: dict[str, dict] = {}
    for voto in votos:
        fecha = voto["creado_en"].date().isoformat()
        fila = por_dia.setdefault(fecha, {"fecha": fecha, "positivos": 0, "negativos": 0})
        fila["positivos" if voto["util"] else "negativos"] += 1

    por_organismo: dict[str, dict] = {}
    for voto in votos:
        if organismo_id is not None:
            claves = [nombres[organismo_id]]
        else:
            ids = organismos_de(voto["session_id"])
            claves = [nombres[i] for i in sorted(ids)] if ids else [SIN_TRAMITE]
        for clave in claves:
            fila = por_organismo.setdefault(clave, {"organismo": clave, "positivos": 0, "negativos": 0})
            fila["positivos" if voto["util"] else "negativos"] += 1

    comentarios = [
        {
            "session_id": voto["session_id"],
            "mensaje_id": voto["mensaje_id"],
            "motivo": voto["motivo"],
            "comentario": voto["comentario"],
            "creado_en": voto["creado_en"].isoformat(),
        }
        for voto in votos
        if not voto["util"] and voto["comentario"]
    ][:MAX_COMENTARIOS_RECIENTES]

    return {
        "total": len(votos),
        "positivos": positivos,
        "negativos": negativos,
        "porcentaje_util": round(100 * positivos / len(votos), 1) if votos else None,
        "motivos": [
            {"motivo": motivo, "cantidad": cantidad}
            for motivo, cantidad in sorted(negativos_con_motivo.items(), key=lambda par: (-par[1], par[0]))
        ],
        "sin_motivo": sum(1 for voto in votos if not voto["util"] and voto["motivo"] is None),
        "por_dia": sorted(por_dia.values(), key=lambda fila: fila["fecha"]),
        "comentarios_recientes": comentarios,
        "por_organismo": sorted(
            por_organismo.values(), key=lambda fila: (-(fila["positivos"] + fila["negativos"]), fila["organismo"])
        ),
    }


def _listar_votos(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mensaje_id, session_id, util, motivo, comentario, created_at
            FROM feedback_respuestas
            ORDER BY created_at DESC, id DESC
            """
        )
        return [
            {
                "mensaje_id": str(mensaje_id),
                "session_id": str(session_id),
                "util": util,
                "motivo": motivo,
                "comentario": comentario,
                "creado_en": creado_en,
            }
            for mensaje_id, session_id, util, motivo, comentario, creado_en in cur.fetchall()
        ]


def _nombres_de_organismos(conn) -> dict[int, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM organismos")
        return {organismo_id: nombre for organismo_id, nombre in cur.fetchall()}
```

- [ ] **Step 5: Agregar el endpoint**

En `backend/agent/api.py`, agregar el import (junto a los otros `from agent.admin import ...`):

```python
from agent.admin import feedback_repository as admin_feedback_repository
```

Y agregar el endpoint después de `admin_obtener_sesion`:

```python
@app.get("/admin/feedback/metricas")
def admin_metricas_feedback(admin: AdminActual = Depends(requiere_admin), pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = admin.organismo_id if admin.rol == "admin_organismo" else None
        return admin_feedback_repository.calcular_metricas(conn, organismo_id)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest -q`
Expected: toda la suite PASS (antes eran 245 tests; ahora más). Si algún test existente que compare diccionarios completos de sesiones o mensajes falla, agregarle las claves nuevas (`votos_positivos`, `votos_negativos`, `id`, `feedback`) a lo esperado.

- [ ] **Step 7: Commit**

```bash
git add backend/agent/admin/chats_repository.py backend/agent/admin/feedback_repository.py backend/agent/api.py backend/tests/test_admin_feedback.py
git commit -m "feat: feedback en el panel admin (detalle, listado y métricas)"
```

---

### Task 7: Frontend — `lib/feedback.ts` (motivos, tipos, estado inicial, envío)

**Files:**
- Create: `frontend/lib/feedback.ts`
- Test: `frontend/lib/feedback.test.ts`
- Modify: `frontend/lib/api.ts:1-5` (tipo `MensajeVisible`)

**Interfaces:**
- Produces:
  - `MOTIVOS: readonly { valor: MotivoFeedback; texto: string }[]`, `type MotivoFeedback`, `MAX_COMENTARIO = 500`.
  - `type FeedbackVoto = { util: boolean; motivo: MotivoFeedback | null; comentario: string | null }`.
  - `type EstadoFeedback = "pregunta" | "detalle" | "gracias_si" | "gracias_no"`.
  - `estadoInicialFeedback(feedback: FeedbackVoto | null | undefined): EstadoFeedback`.
  - `textoMotivo(valor: string | null): string`.
  - `enviarFeedback(payload: PayloadFeedback): Promise<boolean>` donde `PayloadFeedback = { session_id: string; mensaje_id: string; util: boolean; motivo?: MotivoFeedback; comentario?: string }`.
  - `MensajeVisible` (en `lib/api.ts`) suma `id: string; votable: boolean; feedback: FeedbackVoto | null`.

- [ ] **Step 1: Write the failing tests**

Crear `frontend/lib/feedback.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  MAX_COMENTARIO,
  MOTIVOS,
  estadoInicialFeedback,
  textoMotivo,
} from "./feedback";

describe("MOTIVOS", () => {
  it("coincide en valores y orden con la lista cerrada del backend", () => {
    const fuente = readFileSync(
      new URL("../../backend/agent/feedback.py", import.meta.url),
      "utf8"
    );
    const bloque = fuente.match(/MOTIVOS\s*=\s*\(([\s\S]*?)\)/)?.[1] ?? "";
    const valoresBackend = [...bloque.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);

    expect(valoresBackend.length).toBeGreaterThan(0);
    expect(MOTIVOS.map((m) => m.valor)).toEqual(valoresBackend);
  });

  it("tiene los textos de la interfaz", () => {
    expect(MOTIVOS.map((m) => m.texto)).toEqual([
      "No respondió mi pregunta",
      "La información era incorrecta",
      "Faltaba información",
      "Me mostró otro trámite",
      "La información estaba desactualizada",
      "La respuesta no fue clara",
      "Otro",
    ]);
  });

  it("el límite de comentario es 500", () => {
    expect(MAX_COMENTARIO).toBe(500);
  });
});

describe("estadoInicialFeedback", () => {
  it("sin voto pregunta", () => {
    expect(estadoInicialFeedback(null)).toBe("pregunta");
    expect(estadoInicialFeedback(undefined)).toBe("pregunta");
  });

  it("voto positivo agradece", () => {
    expect(estadoInicialFeedback({ util: true, motivo: null, comentario: null })).toBe("gracias_si");
  });

  it("voto negativo con motivo agradece el comentario", () => {
    expect(estadoInicialFeedback({ util: false, motivo: "otro", comentario: null })).toBe("gracias_no");
  });

  it("voto negativo con comentario agradece el comentario", () => {
    expect(estadoInicialFeedback({ util: false, motivo: null, comentario: "mal" })).toBe("gracias_no");
  });

  it("voto negativo sin motivo ni comentario reabre el detalle", () => {
    expect(estadoInicialFeedback({ util: false, motivo: null, comentario: null })).toBe("detalle");
  });
});

describe("textoMotivo", () => {
  it("devuelve el texto del motivo", () => {
    expect(textoMotivo("faltaba_info")).toBe("Faltaba información");
  });

  it("devuelve cadena vacía para null o desconocido", () => {
    expect(textoMotivo(null)).toBe("");
    expect(textoMotivo("inventado")).toBe("");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (desde `frontend/`): `npx vitest run lib/feedback.test.ts`
Expected: FAIL (`Failed to resolve import "./feedback"`).

- [ ] **Step 3: Write minimal implementation**

Crear `frontend/lib/feedback.ts`:

```ts
import { BASE_URL } from "./api";

export const MOTIVOS = [
  { valor: "no_respondio", texto: "No respondió mi pregunta" },
  { valor: "info_incorrecta", texto: "La información era incorrecta" },
  { valor: "faltaba_info", texto: "Faltaba información" },
  { valor: "otro_tramite", texto: "Me mostró otro trámite" },
  { valor: "desactualizada", texto: "La información estaba desactualizada" },
  { valor: "poco_clara", texto: "La respuesta no fue clara" },
  { valor: "otro", texto: "Otro" },
] as const;

export type MotivoFeedback = (typeof MOTIVOS)[number]["valor"];

export const MAX_COMENTARIO = 500;

export type FeedbackVoto = {
  util: boolean;
  motivo: MotivoFeedback | null;
  comentario: string | null;
};

export type EstadoFeedback = "pregunta" | "detalle" | "gracias_si" | "gracias_no";

export type PayloadFeedback = {
  session_id: string;
  mensaje_id: string;
  util: boolean;
  motivo?: MotivoFeedback;
  comentario?: string;
};

export function estadoInicialFeedback(
  feedback: FeedbackVoto | null | undefined
): EstadoFeedback {
  if (!feedback) return "pregunta";
  if (feedback.util) return "gracias_si";
  return feedback.motivo || feedback.comentario ? "gracias_no" : "detalle";
}

export function textoMotivo(valor: string | null): string {
  return MOTIVOS.find((m) => m.valor === valor)?.texto ?? "";
}

export async function enviarFeedback(payload: PayloadFeedback): Promise<boolean> {
  try {
    const respuesta = await fetch(`${BASE_URL}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return respuesta.ok;
  } catch {
    return false;
  }
}
```

En `frontend/lib/api.ts`, reemplazar el tipo `MensajeVisible` por:

```ts
import type { FeedbackVoto } from "./feedback";

export type MensajeVisible = {
  id: string;
  rol: "user" | "assistant";
  contenido: string;
  creado_en: string;
  votable: boolean;
  feedback: FeedbackVoto | null;
};
```

(`import type` va al principio del archivo, antes de los tipos.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run lib/feedback.test.ts && npx tsc --noEmit`
Expected: tests PASS y `tsc` sin errores (puede fallar `tsc` en `useChatStream.ts` por el campo nuevo de `MensajeVisible`; no debería, porque solo se agregan campos. Si falla, no avanzar sin entenderlo).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/feedback.ts frontend/lib/feedback.test.ts frontend/lib/api.ts
git commit -m "feat: lógica y tipos de feedback en el frontend"
```

---

### Task 8: Frontend — `useChatStream` asigna `id`/`votable` y carga el historial

**Files:**
- Modify: `frontend/hooks/useChatStream.ts`
- Test: `frontend/hooks/useChatStream.test.ts`

**Interfaces:**
- Consumes: `FeedbackVoto` (Task 7), `MensajeVisible` con `id`/`votable`/`feedback` (Task 7).
- Produces:
  - `Mensaje` suma `id?: string`, `votable?: boolean`, `feedback?: FeedbackVoto | null`.
  - El evento `fin` suma `mensaje_id: string`.
  - `aplicarEventoSSE(mensajes: Mensaje[], evento: EventoSSE): Mensaje[]` (exportada, pura).

- [ ] **Step 1: Write the failing tests**

En `frontend/hooks/useChatStream.test.ts`, reemplazar la línea `import { parsearLineasSSE } from "./useChatStream";` por:

```ts
import { aplicarEventoSSE, parsearLineasSSE, type Mensaje } from "./useChatStream";
```

y agregar al final del archivo:

```ts
describe("aplicarEventoSSE", () => {
  const base: Mensaje[] = [
    { rol: "user", contenido: "hola" },
    { rol: "assistant", contenido: "" },
  ];

  it("fin asigna el id y marca la respuesta como votable", () => {
    const resultado = aplicarEventoSSE(base, {
      tipo: "fin",
      fuentes: [],
      candidatos_ambiguos: [],
      sugerir_contacto: false,
      mensaje_id: "abc-123",
    });

    expect(resultado[1].id).toBe("abc-123");
    expect(resultado[1].votable).toBe(true);
  });

  it("error no asigna id ni votable", () => {
    const resultado = aplicarEventoSSE(base, { tipo: "error", mensaje: "falló" });

    expect(resultado[1].error).toBe(true);
    expect(resultado[1].id).toBeUndefined();
    expect(resultado[1].votable).toBeUndefined();
  });

  it("texto acumula el delta sin tocar el id", () => {
    const resultado = aplicarEventoSSE(base, { tipo: "texto", delta: "Hola" });

    expect(resultado[1].contenido).toBe("Hola");
    expect(resultado[1].id).toBeUndefined();
  });

  it("no muta el arreglo original", () => {
    aplicarEventoSSE(base, { tipo: "texto", delta: "Hola" });

    expect(base[1].contenido).toBe("");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run hooks/useChatStream.test.ts`
Expected: FAIL (`aplicarEventoSSE is not a function` / no exportada).

- [ ] **Step 3: Write minimal implementation**

En `frontend/hooks/useChatStream.ts`:

(a) Agregar el import al principio:

```ts
import type { FeedbackVoto } from "../lib/feedback";
```

(b) En el tipo `Mensaje`, agregar tres campos al final:

```ts
  id?: string;
  votable?: boolean;
  feedback?: FeedbackVoto | null;
```

(c) En `EventoSSE`, agregar `mensaje_id: string;` al evento de tipo `"fin"`:

```ts
  | {
      tipo: "fin";
      fuentes: Fuente[];
      candidatos_ambiguos: CandidatoAmbiguo[];
      sugerir_contacto: boolean;
      mensaje_id: string;
    }
```

(d) Agregar, después de `parsearLineasSSE`, la función pura:

```ts
export function aplicarEventoSSE(mensajes: Mensaje[], evento: EventoSSE): Mensaje[] {
  const copia = [...mensajes];
  const ultimo = copia[copia.length - 1];
  if (evento.tipo === "texto") {
    copia[copia.length - 1] = { ...ultimo, contenido: ultimo.contenido + evento.delta };
  } else if (evento.tipo === "fin") {
    copia[copia.length - 1] = {
      ...ultimo,
      fuentes: evento.fuentes,
      candidatosAmbiguos: evento.candidatos_ambiguos,
      sugerirContacto: evento.sugerir_contacto,
      id: evento.mensaje_id,
      votable: true,
    };
  } else if (evento.tipo === "error") {
    copia[copia.length - 1] = { ...ultimo, contenido: evento.mensaje, error: true };
  }
  return copia;
}
```

(e) Dentro de `useChatStream`, reemplazar la función `aplicarEvento` completa (la que hace `setMensajes((prev) => { ... })`) por:

```ts
  function aplicarEvento(evento: EventoSSE) {
    setMensajes((prev) => aplicarEventoSSE(prev, evento));
  }
```

(f) En el `useEffect` del historial, reemplazar el mapeo por:

```ts
        setMensajes(
          historial.map((m) => ({
            rol: m.rol,
            contenido: m.contenido,
            id: m.id,
            votable: m.votable,
            feedback: m.feedback,
          }))
        );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run && npx tsc --noEmit`
Expected: todos los tests PASS y `tsc` sin errores.

- [ ] **Step 5: Commit**

```bash
git add frontend/hooks/useChatStream.ts frontend/hooks/useChatStream.test.ts
git commit -m "feat: useChatStream asigna id y votable a las respuestas"
```

---

### Task 9: Frontend — componente `FeedbackRespuesta` montado en el chat

**Files:**
- Create: `frontend/components/FeedbackRespuesta.tsx`
- Modify: `frontend/components/ChatMessage.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `MOTIVOS`, `MAX_COMENTARIO`, `enviarFeedback`, `estadoInicialFeedback`, `EstadoFeedback`, `FeedbackVoto`, `MotivoFeedback` (Task 7); `Mensaje` con `id`/`votable`/`feedback` (Task 8).
- Produces: `<FeedbackRespuesta sessionId mensajeId feedbackInicial />`; `ChatMessage` recibe las props nuevas `sessionId: string` y `mostrarFeedback: boolean`.

Este componente no tiene test unitario (vitest corre en entorno `node`, sin DOM); la lógica pura ya está cubierta en la Task 7 y el componente se verifica visualmente al final de la tarea.

- [ ] **Step 1: Crear el componente**

Crear `frontend/components/FeedbackRespuesta.tsx`:

```tsx
"use client";

import { useState } from "react";
import {
  MAX_COMENTARIO,
  MOTIVOS,
  enviarFeedback,
  estadoInicialFeedback,
  type EstadoFeedback,
  type FeedbackVoto,
  type MotivoFeedback,
} from "../lib/feedback";

export function FeedbackRespuesta({
  sessionId,
  mensajeId,
  feedbackInicial,
}: {
  sessionId: string;
  mensajeId: string;
  feedbackInicial?: FeedbackVoto | null;
}) {
  const [estado, setEstado] = useState<EstadoFeedback>(estadoInicialFeedback(feedbackInicial));
  const [util, setUtil] = useState<boolean | null>(feedbackInicial?.util ?? null);
  const [motivo, setMotivo] = useState<MotivoFeedback | "">(feedbackInicial?.motivo ?? "");
  const [comentario, setComentario] = useState(feedbackInicial?.comentario ?? "");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(false);

  async function votar(nuevoUtil: boolean) {
    if (enviando) return;
    setEnviando(true);
    setError(false);
    const ok = await enviarFeedback({ session_id: sessionId, mensaje_id: mensajeId, util: nuevoUtil });
    setEnviando(false);
    if (!ok) {
      setError(true);
      return;
    }
    setUtil(nuevoUtil);
    if (nuevoUtil) {
      setMotivo("");
      setComentario("");
      setEstado("gracias_si");
    } else {
      setEstado("detalle");
    }
  }

  async function enviarDetalle() {
    if (enviando) return;
    const comentarioLimpio = comentario.trim();
    if (!motivo && !comentarioLimpio) {
      setEstado("gracias_no");
      return;
    }
    setEnviando(true);
    setError(false);
    const ok = await enviarFeedback({
      session_id: sessionId,
      mensaje_id: mensajeId,
      util: false,
      ...(motivo ? { motivo } : {}),
      ...(comentarioLimpio ? { comentario: comentarioLimpio } : {}),
    });
    setEnviando(false);
    if (!ok) {
      setError(true);
      return;
    }
    setEstado("gracias_no");
  }

  const contenedor = "mt-3 border-t border-gray-300 pt-2 text-sm dark:border-white/20";

  if (estado === "gracias_si" || estado === "gracias_no") {
    return (
      <div className={`${contenedor} flex flex-wrap items-center gap-2`}>
        <span className="texto-secundario">
          {estado === "gracias_si"
            ? "¡Gracias por tu opinión!"
            : "Gracias, tu comentario nos ayuda a mejorar."}
        </span>
        <button type="button" onClick={() => setEstado("pregunta")} className="underline">
          Cambiar mi voto
        </button>
      </div>
    );
  }

  return (
    <div className={contenedor}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="texto-secundario">¿Te sirvió esta respuesta?</span>
        <button
          type="button"
          disabled={enviando}
          aria-pressed={util === true}
          onClick={() => votar(true)}
          className={`boton-neutro ${util === true ? "ring-2 ring-emerald-400" : ""}`}
        >
          👍 Sí
        </button>
        <button
          type="button"
          disabled={enviando}
          aria-pressed={util === false}
          onClick={() => votar(false)}
          className={`boton-neutro ${util === false ? "ring-2 ring-rose-400" : ""}`}
        >
          👎 No
        </button>
      </div>

      {estado === "detalle" && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <select
            value={motivo}
            onChange={(e) => setMotivo(e.target.value as MotivoFeedback | "")}
            aria-label="¿Por qué no te sirvió?"
            className="campo-input"
          >
            <option value="">¿Por qué no te sirvió?</option>
            {MOTIVOS.map((m) => (
              <option key={m.valor} value={m.valor}>
                {m.texto}
              </option>
            ))}
          </select>
          <textarea
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            maxLength={MAX_COMENTARIO}
            rows={2}
            placeholder="Comentario opcional"
            aria-label="Comentario opcional"
            className="campo-input resize-none"
          />
          <p className="text-xs texto-secundario sm:col-span-2">
            No incluyas datos personales en tu comentario.
          </p>
          <div className="sm:col-span-2">
            <button type="button" disabled={enviando} onClick={enviarDetalle} className="boton-secundario">
              Enviar
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-1 text-xs texto-error">No se pudo enviar tu opinión. Probá de nuevo.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Montarlo en `ChatMessage`**

En `frontend/components/ChatMessage.tsx`:

(a) Agregar el import:

```tsx
import { FeedbackRespuesta } from "./FeedbackRespuesta";
```

(b) Reemplazar la firma del componente por:

```tsx
export function ChatMessage({
  mensaje,
  sessionId,
  mostrarFeedback,
  onReintentar,
  onPedirContacto,
}: {
  mensaje: Mensaje;
  sessionId: string;
  mostrarFeedback: boolean;
  onReintentar?: () => void;
  onPedirContacto?: () => void;
}) {
```

(c) Agregar, justo después del bloque `{mensaje.sugerirContacto && onPedirContacto && (...)}` y antes del bloque `{mensaje.error && onReintentar && (...)}`:

```tsx
      {mostrarFeedback &&
        !esUsuario &&
        !mensaje.error &&
        mensaje.votable &&
        mensaje.id &&
        mensaje.contenido && (
          <FeedbackRespuesta
            sessionId={sessionId}
            mensajeId={mensaje.id}
            feedbackInicial={mensaje.feedback}
          />
        )}
```

- [ ] **Step 3: Pasar las props desde la página**

En `frontend/app/page.tsx`, dentro del `mensajes.map`, agregar a `<ChatMessage` las dos props nuevas (después de `mensaje={mensaje}`):

```tsx
                sessionId={sessionId}
                mostrarFeedback={!enviando}
```

- [ ] **Step 4: Typecheck y tests**

Run (desde `frontend/`): `npx tsc --noEmit && npx vitest run`
Expected: sin errores de tipos; todos los tests PASS.

- [ ] **Step 5: Verificación visual**

Levantar backend y frontend auxiliares apuntando entre sí y a la base de test (el `.env` tiene `FRONTEND_ORIGIN` de producción y la base real):

```bash
cd backend && (DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha_test ADMIN_JWT_SECRET=visual-secret FRONTEND_ORIGIN=http://localhost:3001 nohup .venv/bin/uvicorn agent.api:app --port 8001 &> /tmp/backend8001.log &)
cd ../frontend && (NEXT_PUBLIC_API_URL=http://localhost:8001 nohup npx next dev -p 3001 &> /tmp/frontend3001.log &)
```

**No** enviar mensajes reales al chat (crearía sesiones y alteraría `veces_consultado` en la base de `.env`). `useSession` genera un UUID nuevo en cada carga, así que no se puede reutilizar una sesión existente. En su lugar, interceptar `/chat` y `/feedback` en el navegador con Puppeteer: escribir `/tmp/feedback-visual.cjs`

```js
const { createRequire } = require("module");
const req = createRequire(process.cwd() + "/package.json");
const puppeteer = req("puppeteer-core");
const cors = {
  "access-control-allow-origin": "http://localhost:3001",
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "*",
};
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const clickTexto = (p, texto) =>
  p.evaluate((t) => [...document.querySelectorAll("button")].find((b) => b.textContent.includes(t))?.click(), texto);

(async () => {
  const b = await puppeteer.launch({ executablePath: "/snap/bin/chromium", headless: "new", args: ["--no-sandbox"] });
  for (const [nombre, ancho, alto, movil] of [["m390", 390, 844, true], ["d1440", 1440, 900, false]]) {
    const p = await b.newPage();
    await p.setViewport({ width: ancho, height: alto, isMobile: movil, hasTouch: movil, deviceScaleFactor: movil ? 2 : 1 });
    await p.setRequestInterception(true);
    p.on("request", (r) => {
      const u = r.url();
      if (r.method() === "OPTIONS") return r.respond({ status: 204, headers: cors });
      if (u.endsWith("/chat")) {
        const cuerpo =
          'data: {"tipo":"texto","delta":"Para renovar tu DNI necesitás turno y abonar la tasa."}\n\n' +
          'data: {"tipo":"fin","fuentes":[],"candidatos_ambiguos":[],"sugerir_contacto":false,"mensaje_id":"11111111-1111-1111-1111-111111111111"}\n\n';
        return r.respond({ status: 200, headers: { ...cors, "content-type": "text/event-stream" }, body: cuerpo });
      }
      if (u.endsWith("/feedback"))
        return r.respond({ status: 200, headers: { ...cors, "content-type": "application/json" }, body: '{"ok":true}' });
      r.continue();
    });
    await p.goto("http://localhost:3001", { waitUntil: "networkidle0" });
    await p.addStyleTag({ content: "nextjs-portal{display:none!important}" });
    await p.type("textarea", "¿Cómo renuevo el DNI?");
    await p.keyboard.press("Enter");
    await p.waitForFunction(() => document.body.innerText.includes("¿Te sirvió esta respuesta?"), { timeout: 15000 });
    await p.screenshot({ path: `/tmp/fb-${nombre}-1-pregunta.png` });
    await clickTexto(p, "No");
    await p.waitForSelector("select", { timeout: 5000 });
    await p.select("select", "faltaba_info");
    await p.type("textarea[aria-label='Comentario opcional']", "Faltó el costo del trámite");
    await p.screenshot({ path: `/tmp/fb-${nombre}-2-detalle.png` });
    await clickTexto(p, "Enviar");
    await espera(500);
    await p.screenshot({ path: `/tmp/fb-${nombre}-3-gracias-no.png` });
    await clickTexto(p, "Cambiar mi voto");
    await clickTexto(p, "Sí");
    await espera(500);
    await p.screenshot({ path: `/tmp/fb-${nombre}-4-gracias-si.png` });
    await p.close();
  }
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
```

Correrlo desde `frontend/` con `node /tmp/feedback-visual.cjs` y revisar las 8 capturas `/tmp/fb-*.png`: pregunta inicial (Sí/No), selector + comentario con la leyenda de datos personales, "Gracias, tu comentario nos ayuda a mejorar." y "¡Gracias por tu opinión!", sin desbordes en 390 px. (`clickTexto(p, "No")` toma el primer botón cuyo texto contiene "No": confirmar que sea "👎 No" y no otro; si no, afinar el selector.)

Apagar los auxiliares al terminar:

```bash
for p in 8001 3001; do ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill; done
```

- [ ] **Step 6: Commit**

```bash
git add frontend/components/FeedbackRespuesta.tsx frontend/components/ChatMessage.tsx frontend/app/page.tsx
git commit -m "feat: widget de feedback bajo cada respuesta del chat"
```

---

### Task 10: Frontend — feedback en el detalle y el listado de chats del admin

**Files:**
- Modify: `frontend/lib/admin-api.ts` (tipos)
- Modify: `frontend/components/ConversacionChat.tsx`
- Modify: `frontend/app/admin/chats/page.tsx`

**Interfaces:**
- Consumes: `FeedbackVoto`, `textoMotivo` (Task 7); respuestas del backend de la Task 6.
- Produces: `MensajeAdmin` suma `id?: string` y `feedback?: FeedbackVoto | null`; `SesionResumen` suma `votos_positivos: number` y `votos_negativos: number`.

- [ ] **Step 1: Tipos**

En `frontend/lib/admin-api.ts`, agregar al principio:

```ts
import type { FeedbackVoto } from "./feedback";
```

En `MensajeAdmin`, agregar:

```ts
  id?: string;
  feedback?: FeedbackVoto | null;
```

En `SesionResumen`, agregar:

```ts
  votos_positivos: number;
  votos_negativos: number;
```

- [ ] **Step 2: Detalle del chat**

En `frontend/components/ConversacionChat.tsx`, agregar el import:

```tsx
import { textoMotivo, type FeedbackVoto } from "../lib/feedback";
```

Dentro del `BurbujaMensaje`, después del bloque del badge de `proveedor` y antes del bloque de `tool_calls`, agregar:

```tsx
          {mensaje.rol === "assistant" && mensaje.feedback && (
            <FeedbackAdmin feedback={mensaje.feedback} />
          )}
```

Y agregar al final del archivo:

```tsx
function FeedbackAdmin({ feedback }: { feedback: FeedbackVoto }) {
  const motivo = textoMotivo(feedback.motivo);
  return (
    <div className="mt-2 rounded border border-gray-300 bg-white p-2 text-xs">
      <p className="font-semibold">
        {feedback.util ? "👍 Le sirvió" : "👎 No le sirvió"}
        {motivo ? ` · ${motivo}` : ""}
      </p>
      {feedback.comentario && <p className="mt-1 whitespace-pre-wrap">{feedback.comentario}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Listado de chats**

En `frontend/app/admin/chats/page.tsx`, agregar una columna. En el `<thead>`, después de `<th className="p-2">Trámites citados</th>`:

```tsx
            <th className="p-2">Feedback</th>
```

Y en el `<tbody>`, después de la celda de trámites citados (el `<td>` que contiene el `map` de `tramites_citados`), agregar:

```tsx
              <td className="p-2 whitespace-nowrap">
                {sesion.votos_positivos + sesion.votos_negativos === 0
                  ? "—"
                  : `👍 ${sesion.votos_positivos} · 👎 ${sesion.votos_negativos}`}
              </td>
```

- [ ] **Step 4: Typecheck y tests**

Run: `npx tsc --noEmit && npx vitest run`
Expected: sin errores; tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/admin-api.ts frontend/components/ConversacionChat.tsx frontend/app/admin/chats/page.tsx
git commit -m "feat: feedback visible en el detalle y el listado de chats del admin"
```

---

### Task 11: Frontend — pantalla de métricas "Feedback"

**Files:**
- Create: `frontend/lib/feedback-metricas.ts`
- Test: `frontend/lib/feedback-metricas.test.ts`
- Modify: `frontend/lib/admin-api.ts` (tipo y función de métricas)
- Create: `frontend/app/admin/feedback/page.tsx`
- Modify: `frontend/app/admin/layout.tsx` (ítem de menú)

**Interfaces:**
- Consumes: `GET /admin/feedback/metricas` (Task 6); `textoMotivo` (Task 7).
- Produces:
  - `formatearPorcentaje(valor: number | null): string` → `"—"` si es `null`, si no `"75,0%"` (coma decimal, un decimal).
  - `anchoBarra(cantidad: number, maximo: number): number` → porcentaje entero 0–100 (0 si `maximo` es 0).
  - `type MetricasFeedback` y `obtenerMetricasFeedback(): Promise<MetricasFeedback>` en `lib/admin-api.ts`.

- [ ] **Step 1: Write the failing tests**

Crear `frontend/lib/feedback-metricas.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { anchoBarra, formatearPorcentaje } from "./feedback-metricas";

describe("formatearPorcentaje", () => {
  it("devuelve guion cuando no hay votos", () => {
    expect(formatearPorcentaje(null)).toBe("—");
  });

  it("usa coma decimal y un decimal", () => {
    expect(formatearPorcentaje(75)).toBe("75,0%");
    expect(formatearPorcentaje(33.3)).toBe("33,3%");
  });

  it("nunca devuelve NaN", () => {
    expect(formatearPorcentaje(0)).toBe("0,0%");
    expect(formatearPorcentaje(Number.NaN)).toBe("—");
  });
});

describe("anchoBarra", () => {
  it("calcula el porcentaje respecto del máximo", () => {
    expect(anchoBarra(5, 10)).toBe(50);
    expect(anchoBarra(10, 10)).toBe(100);
  });

  it("devuelve 0 si el máximo es 0", () => {
    expect(anchoBarra(0, 0)).toBe(0);
  });

  it("redondea al entero más cercano", () => {
    expect(anchoBarra(1, 3)).toBe(33);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/feedback-metricas.test.ts`
Expected: FAIL (`Failed to resolve import "./feedback-metricas"`).

- [ ] **Step 3: Write minimal implementation**

Crear `frontend/lib/feedback-metricas.ts`:

```ts
export function formatearPorcentaje(valor: number | null): string {
  if (valor === null || Number.isNaN(valor)) return "—";
  return `${valor.toFixed(1).replace(".", ",")}%`;
}

export function anchoBarra(cantidad: number, maximo: number): number {
  if (maximo <= 0) return 0;
  return Math.round((cantidad / maximo) * 100);
}
```

En `frontend/lib/admin-api.ts`, agregar al final:

```ts
export type MetricasFeedback = {
  total: number;
  positivos: number;
  negativos: number;
  porcentaje_util: number | null;
  motivos: { motivo: string; cantidad: number }[];
  sin_motivo: number;
  por_dia: { fecha: string; positivos: number; negativos: number }[];
  comentarios_recientes: {
    session_id: string;
    mensaje_id: string;
    motivo: string | null;
    comentario: string;
    creado_en: string;
  }[];
  por_organismo: { organismo: string; positivos: number; negativos: number }[];
};

export async function obtenerMetricasFeedback(): Promise<MetricasFeedback> {
  const respuesta = await fetch(`${BASE_URL}/admin/feedback/metricas`, {
    credentials: "include",
  });
  if (!respuesta.ok) {
    throw new Error("No se pudieron cargar las métricas de feedback");
  }
  return respuesta.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run lib/feedback-metricas.test.ts`
Expected: PASS.

- [ ] **Step 5: Crear la pantalla**

Crear `frontend/app/admin/feedback/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { obtenerMetricasFeedback, type MetricasFeedback } from "../../../lib/admin-api";
import { textoMotivo } from "../../../lib/feedback";
import { anchoBarra, formatearPorcentaje } from "../../../lib/feedback-metricas";

export default function FeedbackPage() {
  const [metricas, setMetricas] = useState<MetricasFeedback | null>(null);
  const [error, setError] = useState(false);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    cargar();
  }, []);

  async function cargar() {
    setCargando(true);
    setError(false);
    try {
      setMetricas(await obtenerMetricasFeedback());
    } catch {
      setError(true);
    } finally {
      setCargando(false);
    }
  }

  if (cargando) {
    return <p className="p-4 text-sm texto-secundario">Cargando…</p>;
  }

  if (error || !metricas) {
    return (
      <div className="p-4">
        <p className="text-sm texto-error">No se pudieron cargar las métricas de feedback</p>
        <button onClick={cargar} className="boton-secundario mt-2">
          Reintentar
        </button>
      </div>
    );
  }

  if (metricas.total === 0) {
    return <p className="p-4 text-sm texto-secundario">Todavía no hay votos registrados</p>;
  }

  const maxMotivo = Math.max(...metricas.motivos.map((m) => m.cantidad), metricas.sin_motivo, 0);
  const maxDia = Math.max(...metricas.por_dia.map((d) => d.positivos + d.negativos), 0);

  return (
    <div className="space-y-6 p-4">
      <h1 className="text-xl font-semibold">Feedback</h1>

      <div className="grid gap-3 sm:grid-cols-4">
        <Tarjeta titulo="Votos" valor={String(metricas.total)} />
        <Tarjeta titulo="👍 Útil" valor={String(metricas.positivos)} />
        <Tarjeta titulo="👎 No útil" valor={String(metricas.negativos)} />
        <Tarjeta titulo="% útil" valor={formatearPorcentaje(metricas.porcentaje_util)} />
      </div>

      <section>
        <h2 className="mb-2 font-semibold">Motivos de los votos negativos</h2>
        {metricas.motivos.length === 0 && metricas.sin_motivo === 0 ? (
          <p className="text-sm texto-secundario">Sin votos negativos.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {metricas.motivos.map((m) => (
              <Barra
                key={m.motivo}
                etiqueta={textoMotivo(m.motivo) || m.motivo}
                cantidad={m.cantidad}
                ancho={anchoBarra(m.cantidad, maxMotivo)}
              />
            ))}
            {metricas.sin_motivo > 0 && (
              <Barra
                etiqueta="Sin motivo"
                cantidad={metricas.sin_motivo}
                ancho={anchoBarra(metricas.sin_motivo, maxMotivo)}
              />
            )}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Votos por día (UTC)</h2>
        <ul className="space-y-2 text-sm">
          {metricas.por_dia.map((d) => (
            <Barra
              key={d.fecha}
              etiqueta={d.fecha}
              cantidad={d.positivos + d.negativos}
              detalle={`👍 ${d.positivos} · 👎 ${d.negativos}`}
              ancho={anchoBarra(d.positivos + d.negativos, maxDia)}
            />
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-1 font-semibold">Por organismo</h2>
        <p className="mb-2 text-xs texto-secundario">
          Aproximación: un voto cuenta en cada organismo citado en su conversación, por lo que puede
          aparecer en más de uno. Las conversaciones sin trámite citado figuran como "Sin trámite".
        </p>
        <table className="w-full text-sm">
          <thead>
            <tr className="tabla-cabecera">
              <th className="p-2">Organismo</th>
              <th className="p-2">👍</th>
              <th className="p-2">👎</th>
            </tr>
          </thead>
          <tbody>
            {metricas.por_organismo.map((fila) => (
              <tr key={fila.organismo} className="tabla-fila">
                <td className="p-2">{fila.organismo}</td>
                <td className="p-2">{fila.positivos}</td>
                <td className="p-2">{fila.negativos}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="mb-2 font-semibold">Comentarios recientes de votos negativos</h2>
        {metricas.comentarios_recientes.length === 0 ? (
          <p className="text-sm texto-secundario">Todavía no hay comentarios.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {metricas.comentarios_recientes.map((c) => (
              <li key={c.mensaje_id} className="tarjeta">
                <p className="whitespace-pre-wrap">{c.comentario}</p>
                <p className="mt-1 text-xs texto-secundario">
                  {new Date(c.creado_en).toLocaleString("es-AR")}
                  {c.motivo ? ` · ${textoMotivo(c.motivo)}` : ""} ·{" "}
                  <Link href={`/admin/chats/${c.session_id}`} className="underline">
                    Ver chat
                  </Link>
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Tarjeta({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div className="tarjeta">
      <p className="text-xs texto-secundario">{titulo}</p>
      <p className="text-2xl font-semibold">{valor}</p>
    </div>
  );
}

function Barra({
  etiqueta,
  cantidad,
  ancho,
  detalle,
}: {
  etiqueta: string;
  cantidad: number;
  ancho: number;
  detalle?: string;
}) {
  return (
    <li>
      <div className="flex justify-between">
        <span>{etiqueta}</span>
        <span className="texto-secundario">{detalle ?? cantidad}</span>
      </div>
      <div className="h-2 rounded bg-gray-100">
        <div className="h-2 rounded bg-macacha-blue" style={{ width: `${ancho}%` }} />
      </div>
    </li>
  );
}
```

- [ ] **Step 6: Ítem de menú**

En `frontend/app/admin/layout.tsx`, agregar después del `<li>` de "Contacto" y antes del bloque de "Usuarios":

```tsx
            <li>
              <ItemNav href="/admin/feedback" pathname={pathname} icono="★">
                Feedback
              </ItemNav>
            </li>
```

- [ ] **Step 7: Typecheck, tests y verificación visual**

Run: `npx tsc --noEmit && npx vitest run`
Expected: sin errores; todos los tests PASS.

Verificación visual contra la **base de test** (nunca la real). Cargar datos de ejemplo y un admin:

```bash
cd backend && DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha_test .venv/bin/python - <<'EOF'
import os, uuid, psycopg
from agent import feedback, sessions
from agent.admin import repository as admin_repository, security

with psycopg.connect(os.environ["DATABASE_URL"]) as c:
    admin_repository.crear_admin(c, "visual@macacha.local", security.hash_password("visual123"), "super_admin", None)
    casos = [(True, None, None), (True, None, None), (False, "faltaba_info", "Faltó el costo"),
             (False, "poco_clara", "No entendí los pasos"), (False, None, None)]
    for util, motivo, comentario in casos:
        sid = str(uuid.uuid4())
        sessions.crear_sesion_si_no_existe(c, sid)
        sessions.guardar_mensaje(c, sid, rol="user", contenido="¿Cómo renuevo el DNI?")
        mid = sessions.guardar_mensaje(c, sid, rol="assistant", contenido="Para renovar tu DNI necesitás turno.")
        feedback.guardar_voto(c, sid, mid, util, motivo, comentario)
    c.commit()
EOF
```

Levantar backend y frontend auxiliares contra esa base:

```bash
cd backend && (DATABASE_URL=postgresql://macacha:macacha@localhost:5432/macacha_test ADMIN_JWT_SECRET=visual-secret FRONTEND_ORIGIN=http://localhost:3001 nohup .venv/bin/uvicorn agent.api:app --port 8001 &> /tmp/backend8001.log &)
cd ../frontend && (NEXT_PUBLIC_API_URL=http://localhost:8001 nohup npx next dev -p 3001 &> /tmp/frontend3001.log &)
```

Con Puppeteer (mismo patrón que la Task 9, sin interceptar nada), iniciar sesión en `http://localhost:3001/admin/login` con `visual@macacha.local` / `visual123` y capturar `/admin/feedback` (con datos), `/admin/chats` (columna Feedback) y el detalle de un chat (bloque "👎 No le sirvió · …"). Para el estado vacío, borrar los votos (`DELETE FROM feedback_respuestas;` en `macacha_test`) y capturar `/admin/feedback` otra vez ("Todavía no hay votos registrados").

Limpiar y apagar al terminar:

```bash
docker exec -i macacha-postgres-1 psql -U macacha -d macacha_test -c "DELETE FROM feedback_respuestas; DELETE FROM mensajes; DELETE FROM sesiones; DELETE FROM admins;"
for p in 8001 3001; do ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill; done
```

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/feedback-metricas.ts frontend/lib/feedback-metricas.test.ts frontend/lib/admin-api.ts frontend/app/admin/feedback/page.tsx frontend/app/admin/layout.tsx
git commit -m "feat: pantalla de métricas de feedback en el panel admin"
```

---

### Task 12: Verificación final y notas de despliegue

**Files:**
- Modify: `docs/deploy-dokploy.md` (nota breve en la sección de `schema.sql`)

- [ ] **Step 1: Suites completas**

Run: `cd backend && .venv/bin/pytest -q`
Expected: toda la suite PASS.

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: sin errores de tipos; todos los tests PASS.

- [ ] **Step 2: Nota de despliegue**

En `docs/deploy-dokploy.md`, junto a la instrucción permanente de volver a correr `schema.sql` (la que dice "cada vez que `schema.sql` cambie"), agregar una línea:

```markdown
   > La tabla `feedback_respuestas` (feedback de respuestas del chat) se crea con este mismo
   > comando. Correrlo **antes** de desplegar el frontend que muestra los botones 👍/👎; si el
   > frontend sale primero, los votos fallan con el aviso "No se pudo enviar tu opinión".
```

- [ ] **Step 3: Commit**

```bash
git add docs/deploy-dokploy.md
git commit -m "docs: nota de despliegue para la tabla feedback_respuestas"
```

- [ ] **Step 4: Revisión de estado**

Run: `git status --short && git log --oneline -14`
Expected: el árbol solo muestra los cambios previos ajenos a este plan (`frontend/package*.json`, `.claude/`); los commits del plan están presentes. No hacer push sin que el usuario lo pida.
