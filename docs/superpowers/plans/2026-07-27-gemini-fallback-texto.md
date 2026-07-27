# Fallback a Gemini (chat, rerank, FAQs) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar Gemini como fallback opcional para los tres usos de OpenAI que son llamados de texto→texto (chat completions del agente, rerank de búsqueda, generación de FAQs), según el spec aprobado en `docs/superpowers/specs/2026-07-27-gemini-fallback-texto-design.md`.

**Architecture:** Se reutiliza el SDK `openai` apuntando al endpoint de Gemini compatible con la API de OpenAI (`https://generativelanguage.googleapis.com/v1beta/openai/`) — sin conversores de formato. Cada wrapper existente (`ChatClient`, `OpenAIClient`) recibe un segundo cliente SDK opcional; si la llamada primaria (OpenAI) falla y hay cliente de Gemini configurado, se reintenta contra Gemini. El proveedor usado en el chat se persiste en `mensajes.proveedor` y se muestra en el panel de admin.

**Tech Stack:** Sin dependencias nuevas (el SDK `openai` ya cubre Gemini vía `base_url`).

## Global Constraints

- Identificadores en español, sin comentarios salvo WHY no obvio.
- `GEMINI_API_KEY` es opcional: si no está seteada, el comportamiento es idéntico al actual (sin cliente de fallback, la excepción de OpenAI se propaga tal cual).
- Ante cualquier excepción de OpenAI (sin distinguir tipo) se reintenta la misma llamada contra Gemini, un solo intento. Si Gemini también falla, se propaga **la excepción de Gemini** (la última). Si no hay cliente de Gemini configurado, se propaga la excepción original de OpenAI.
- Modelo de Gemini fijo como constante: `"gemini-2.0-flash"`, para los tres usos.
- `agent/orchestrator.py` usa `respuesta.get("proveedor")` (no acceso directo por clave) al pasarlo a `guardar_mensaje`, para no romper los tests existentes que arman respuestas fake de chat client sin esa clave.
- Tests de backend contra la DB real de test (`db_conn`/`clean_db`), sin mockear la DB — solo se fakean los SDKs de OpenAI/Gemini.
- Fuera de alcance: fallback de `generate_embeddings`, proveedor expuesto en el SSE del chat público, persistencia en DB del proveedor usado en rerank/FAQs (solo `print()`).

---

## Backend

### Task 1: Columna `proveedor` en `mensajes` + `agent/sessions.py`

**Files:**
- Modify: `backend/db/schema.sql`
- Modify: `backend/agent/sessions.py`
- Modify: `backend/tests/test_sessions.py`

**Interfaces:**
- Produces: columna `mensajes.proveedor TEXT` (nullable); `guardar_mensaje(conn, session_id, rol, contenido=None, tool_calls=None, tool_call_id=None, proveedor=None)`. Usada por Task 4 (orchestrator) y consumida por Task 5 (chats_repository).

- [ ] **Step 1: Agregar la columna al schema**

Al final de `backend/db/schema.sql`:

```sql
ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS proveedor TEXT;
```

- [ ] **Step 2: Aplicar la migración contra el Postgres corriendo**

No es automática sobre un contenedor ya inicializado (mismo caso que la tabla `admins`). Aplicarla directo, sin recrear el volumen (la DB tiene poco volumen de datos hoy, pero de todas formas es más simple que un `down -v`):

Run: `docker exec macacha-postgres-1 psql -U macacha -d macacha -c "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS proveedor TEXT;"`
Run: `docker exec macacha-postgres-1 psql -U macacha -d macacha_test -c "ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS proveedor TEXT;"`

Expected: ambos comandos imprimen `ALTER TABLE`.

- [ ] **Step 3: Escribir los tests que fallan**

Agregar al final de `backend/tests/test_sessions.py`:

```python
def test_guardar_mensaje_persiste_proveedor(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="hola", proveedor="gemini")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT proveedor FROM mensajes WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] == "gemini"


def test_guardar_mensaje_sin_proveedor_persiste_null(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)

    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT proveedor FROM mensajes WHERE session_id = %s", (session_id,))
        assert cur.fetchone()[0] is None
```

- [ ] **Step 4: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sessions.py -v -k proveedor`
Expected: FAIL — `guardar_mensaje() got an unexpected keyword argument 'proveedor'`

- [ ] **Step 5: Implementar el parámetro nuevo**

En `backend/agent/sessions.py`, reemplazar `guardar_mensaje` completa:

```python
def guardar_mensaje(
    conn,
    session_id: str,
    rol: str,
    contenido: str | None = None,
    tool_calls: list[dict] | None = None,
    tool_call_id: str | None = None,
    proveedor: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mensajes (session_id, rol, contenido, tool_calls, tool_call_id, proveedor)
            VALUES (%s, %s, %s, %s, %s, %s)
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
```

- [ ] **Step 6: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_sessions.py -v`
Expected: PASS (5 tests: 3 existentes + 2 nuevos)

- [ ] **Step 7: Correr la suite completa para confirmar que no rompe nada**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: PASS (toda la suite — las llamadas existentes a `guardar_mensaje` sin `proveedor` siguen funcionando, insertan `NULL`)

- [ ] **Step 8: Commit**

```bash
git add backend/db/schema.sql backend/agent/sessions.py backend/tests/test_sessions.py
git commit -m "feat: columna proveedor en mensajes para trackear qué LLM respondió"
```

---

### Task 2: `agent/chat_client.py` — fallback a Gemini

**Files:**
- Modify: `backend/agent/chat_client.py`
- Modify: `backend/tests/test_chat_client.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: nada nuevo (el SDK `openai` ya está en `requirements.txt`).
- Produces: `ChatClient(sdk_client, sdk_client_gemini=None)`; `completar(messages, tools) -> dict` ahora incluye `"proveedor": "openai" | "gemini"`. `build_real_chat_client()` arma el cliente Gemini solo si `GEMINI_API_KEY` está seteada. Usado por Task 4 (orchestrator).

- [ ] **Step 1: Agregar `GEMINI_API_KEY` al ejemplo de env**

En `.env.example`, agregar:

```
GEMINI_API_KEY=
```

- [ ] **Step 2: Escribir los tests que fallan**

Reemplazar `backend/tests/test_chat_client.py` completo (las fakes cambian de forma — pasan a soportar simular una excepción — por eso se reemplaza el archivo entero en vez de solo agregar tests):

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
    def __init__(self, message=None, error=None):
        self._message = message
        self._error = error
        self.last_call = None
        self.llamadas = 0

    def create(self, model, messages, tools):
        self.llamadas += 1
        self.last_call = {"model": model, "messages": messages, "tools": tools}
        if self._error is not None:
            raise self._error
        return _FakeChatCompletionResponse(self._message)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, message=None, error=None):
        self.chat = _FakeChat(_FakeCompletions(message=message, error=error))


def test_completar_devuelve_respuesta_sin_tool_calls():
    fake_sdk = _FakeOpenAISDK(message=_FakeMessage(content="Hola, ¿en qué te ayudo?"))
    client = ChatClient(fake_sdk)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado == {
        "role": "assistant",
        "content": "Hola, ¿en qué te ayudo?",
        "tool_calls": None,
        "proveedor": "openai",
    }
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_completar_devuelve_tool_calls_normalizados():
    argumentos = json.dumps({"query": "acta"})
    tool_call = _FakeToolCall("call_1", "buscar_tramite", argumentos)
    fake_sdk = _FakeOpenAISDK(message=_FakeMessage(content=None, tool_calls=[tool_call]))
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
        "proveedor": "openai",
    }


def test_completar_usa_gemini_si_openai_falla():
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(message=_FakeMessage(content="Respuesta de Gemini"))
    client = ChatClient(fake_openai, fake_gemini)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado == {
        "role": "assistant",
        "content": "Respuesta de Gemini",
        "tool_calls": None,
        "proveedor": "gemini",
    }
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_completar_no_llama_a_gemini_si_openai_responde_bien():
    fake_openai = _FakeOpenAISDK(message=_FakeMessage(content="Hola"))
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("no debería llamarse"))
    client = ChatClient(fake_openai, fake_gemini)

    resultado = client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])

    assert resultado["proveedor"] == "openai"
    assert fake_gemini.chat.completions.llamadas == 0


def test_completar_sin_cliente_gemini_propaga_error_de_openai():
    fake_openai = _FakeOpenAISDK(error=ValueError("401 de OpenAI"))
    client = ChatClient(fake_openai)

    try:
        client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])
        assert False, "debería haber propagado la excepción"
    except ValueError as exc:
        assert str(exc) == "401 de OpenAI"


def test_completar_con_ambos_proveedores_fallando_propaga_error_de_gemini():
    fake_openai = _FakeOpenAISDK(error=ValueError("falla de OpenAI"))
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("falla de Gemini"))
    client = ChatClient(fake_openai, fake_gemini)

    try:
        client.completar(messages=[{"role": "user", "content": "hola"}], tools=[])
        assert False, "debería haber propagado la excepción"
    except RuntimeError as exc:
        assert str(exc) == "falla de Gemini"
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_chat_client.py -v`
Expected: FAIL — los dos primeros tests fallan porque `resultado` no tiene la clave `"proveedor"`; los nuevos fallan con `TypeError: ChatClient() takes 2 positional arguments but 3 were given` o similar (constructor todavía no acepta el segundo cliente)

- [ ] **Step 4: Implementar el fallback**

Reemplazar `backend/agent/chat_client.py` completo:

```python
import os


class ChatClient:
    MODEL_OPENAI = "gpt-4o-mini"
    MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

    def completar(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            response = self._sdk_client.chat.completions.create(
                model=self.MODEL_OPENAI, messages=messages, tools=tools
            )
            proveedor = "openai"
        except Exception:
            if self._sdk_client_gemini is None:
                raise
            print("OpenAI falló, usando fallback a Gemini")
            response = self._sdk_client_gemini.chat.completions.create(
                model=self.MODEL_GEMINI, messages=messages, tools=tools
            )
            proveedor = "gemini"

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

        return {
            "role": "assistant",
            "content": mensaje.content,
            "tool_calls": tool_calls,
            "proveedor": proveedor,
        }


def build_real_chat_client() -> ChatClient:
    from openai import OpenAI

    sdk_client_gemini = None
    if os.environ.get("GEMINI_API_KEY"):
        sdk_client_gemini = OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return ChatClient(OpenAI(), sdk_client_gemini)
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_chat_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/chat_client.py backend/tests/test_chat_client.py .env.example
git commit -m "feat: fallback a Gemini para chat completions"
```

---

### Task 3: `ingest/openai_client.py` — fallback a Gemini (rerank + FAQs)

**Files:**
- Modify: `backend/ingest/openai_client.py`
- Modify: `backend/tests/test_openai_client.py`

**Interfaces:**
- Produces: `OpenAIClient(sdk_client, sdk_client_gemini=None)`; `rerank`/`generate_faqs` reintentan contra Gemini ante cualquier excepción de OpenAI, vía un helper interno `_completar_con_fallback`. `build_real_client()` arma el cliente Gemini solo si `GEMINI_API_KEY` está seteada. `generate_embeddings` no cambia.

- [ ] **Step 1: Escribir los tests que fallan**

Reemplazar `backend/tests/test_openai_client.py` completo:

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
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.last_call = None

    def create(self, model, messages, response_format):
        self.last_call = {"model": model, "messages": messages, "response_format": response_format}
        if self._error is not None:
            raise self._error
        return _FakeChatCompletionResponse(self._content)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, vectors=None, content=None, error=None):
        self.embeddings = _FakeEmbeddings(vectors or [])
        self.chat = _FakeChat(_FakeCompletions(content=content, error=error))


def test_generate_embeddings_calls_api_and_returns_vectors():
    fake_sdk = _FakeOpenAISDK(vectors=[[0.1, 0.2], [0.3, 0.4]], content="{}")
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
    fake_sdk = _FakeOpenAISDK(content=faq_json)
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


def test_rerank_parses_json_response_as_order():
    orden_json = json.dumps({"orden": [2, 0, 1]})
    fake_sdk = _FakeOpenAISDK(content=orden_json)
    client = OpenAIClient(fake_sdk)

    candidatos = [
        {"texto": "fragmento A"},
        {"texto": "fragmento B"},
        {"texto": "fragmento C"},
    ]

    resultado = client.rerank("una pregunta cualquiera", candidatos)

    assert resultado == [2, 0, 1]
    assert fake_sdk.chat.completions.last_call["model"] == "gpt-4o-mini"


def test_generate_faqs_usa_gemini_si_openai_falla():
    faq_json = json.dumps({"faqs": [{"pregunta": "p", "respuesta": "r"}]})
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(content=faq_json)
    client = OpenAIClient(fake_openai, fake_gemini)

    resultado = client.generate_faqs(
        nombre_oficial="Actas Regulares", descripcion="desc", requisitos=["DNI"], pasos=["Paso 1"]
    )

    assert resultado == [{"pregunta": "p", "respuesta": "r"}]
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_rerank_usa_gemini_si_openai_falla():
    orden_json = json.dumps({"orden": [1, 0]})
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(content=orden_json)
    client = OpenAIClient(fake_openai, fake_gemini)

    resultado = client.rerank("query", [{"texto": "a"}, {"texto": "b"}])

    assert resultado == [1, 0]
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_rerank_sin_cliente_gemini_propaga_error_de_openai():
    fake_openai = _FakeOpenAISDK(error=ValueError("401 de OpenAI"))
    client = OpenAIClient(fake_openai)

    try:
        client.rerank("query", [{"texto": "a"}])
        assert False, "debería haber propagado la excepción"
    except ValueError as exc:
        assert str(exc) == "401 de OpenAI"
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_openai_client.py -v`
Expected: FAIL — los tests nuevos de fallback fallan (`OpenAIClient()` no acepta un segundo argumento todavía)

- [ ] **Step 3: Implementar el fallback**

Reemplazar `backend/ingest/openai_client.py` completo:

```python
import json
import os


class OpenAIClient:
    EMBEDDING_MODEL = "text-embedding-3-small"
    FAQ_MODEL_OPENAI = "gpt-4o-mini"
    FAQ_MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

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
        content = self._completar_con_fallback(prompt)
        data = json.loads(content)
        return data["faqs"]

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
        content = self._completar_con_fallback(prompt)
        data = json.loads(content)
        return data["orden"]

    def _completar_con_fallback(self, prompt: str) -> str:
        try:
            response = self._sdk_client.chat.completions.create(
                model=self.FAQ_MODEL_OPENAI,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
        except Exception:
            if self._sdk_client_gemini is None:
                raise
            print("OpenAI falló, usando fallback a Gemini")
            response = self._sdk_client_gemini.chat.completions.create(
                model=self.FAQ_MODEL_GEMINI,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
        return response.choices[0].message.content


def build_real_client() -> OpenAIClient:
    from openai import OpenAI

    sdk_client_gemini = None
    if os.environ.get("GEMINI_API_KEY"):
        sdk_client_gemini = OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    return OpenAIClient(OpenAI(), sdk_client_gemini)
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_openai_client.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Correr la suite completa (incluye `ingest/loader.py` y demás consumidores de `OpenAIClient`) para confirmar que no rompe nada**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/ingest/openai_client.py backend/tests/test_openai_client.py
git commit -m "feat: fallback a Gemini para rerank y generación de FAQs"
```

---

### Task 4: `agent/orchestrator.py` — persistir el proveedor del turno

**Files:**
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `respuesta["proveedor"]` (clave nueva en el dict que devuelve `ChatClient.completar`, Task 2), `sessions.guardar_mensaje(..., proveedor=...)` (Task 1).

- [ ] **Step 1: Agregar el test que falla**

Agregar al final de `backend/tests/test_orchestrator.py`:

```python
def test_procesar_turno_persiste_el_proveedor_del_chat_client(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": "Hola", "tool_calls": None, "proveedor": "gemini"}]
    )

    list(procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola"))
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT proveedor FROM mensajes WHERE session_id = %s AND rol = 'assistant'",
            (session_id,),
        )
        assert cur.fetchone()[0] == "gemini"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_orchestrator.py -v -k proveedor`
Expected: FAIL — `assert None == 'gemini'` (todavía no se persiste)

- [ ] **Step 3: Pasar `proveedor` en ambos `guardar_mensaje` de mensajes `assistant`**

En `backend/agent/orchestrator.py`, dentro de `procesar_turno`, el bloque:

```python
        if not respuesta["tool_calls"]:
            sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=respuesta["content"])
            yield from _emitir_respuesta_trozeada(respuesta["content"] or "")
            yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
            return

        sessions.guardar_mensaje(
            conn,
            session_id,
            rol="assistant",
            contenido=respuesta["content"],
            tool_calls=respuesta["tool_calls"],
        )
```

pasa a:

```python
        if not respuesta["tool_calls"]:
            sessions.guardar_mensaje(
                conn,
                session_id,
                rol="assistant",
                contenido=respuesta["content"],
                proveedor=respuesta.get("proveedor"),
            )
            yield from _emitir_respuesta_trozeada(respuesta["content"] or "")
            yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
            return

        sessions.guardar_mensaje(
            conn,
            session_id,
            rol="assistant",
            contenido=respuesta["content"],
            tool_calls=respuesta["tool_calls"],
            proveedor=respuesta.get("proveedor"),
        )
```

(El resto de la función no cambia.)

- [ ] **Step 4: Correr el test nuevo y toda la suite de orchestrator**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_orchestrator.py -v`
Expected: PASS (7 tests: 6 existentes + 1 nuevo — los existentes usan respuestas fake sin `"proveedor"`, y siguen pasando porque `.get()` devuelve `None` en ese caso)

- [ ] **Step 5: Correr la suite completa**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agent/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: persistir el proveedor del LLM en cada mensaje del asistente"
```

---

### Task 5: `agent/admin/chats_repository.py` — exponer el proveedor

**Files:**
- Modify: `backend/agent/admin/chats_repository.py`
- Modify: `backend/tests/test_admin_chats_repository.py`

**Interfaces:**
- Produces: `obtener_mensajes_completos` incluye `"proveedor"` en cada mensaje cuando la columna no es `NULL` (mismo patrón condicional que ya usa con `tool_calls`/`tool_call_id`). Consumida por el endpoint `GET /admin/sesiones/{id}` (ya existente, sin cambios — el dict que arma `obtener_mensajes_completos` se devuelve tal cual).

- [ ] **Step 1: Escribir el test que falla**

Agregar al final de `backend/tests/test_admin_chats_repository.py`:

```python
def test_obtener_mensajes_completos_incluye_proveedor_cuando_no_es_null(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id, datetime.now(timezone.utc))
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(
        db_conn, session_id, rol="assistant", contenido="respuesta", proveedor="gemini"
    )
    db_conn.commit()

    mensajes = chats_repository.obtener_mensajes_completos(db_conn, session_id)

    assert "proveedor" not in mensajes[0]
    assert mensajes[1]["proveedor"] == "gemini"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_chats_repository.py -v -k proveedor`
Expected: FAIL — `KeyError: 'proveedor'`

- [ ] **Step 3: Agregar `proveedor` a la query y al dict devuelto**

En `backend/agent/admin/chats_repository.py`, `obtener_mensajes_completos` pasa de:

```python
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
```

a:

```python
def obtener_mensajes_completos(conn, session_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rol, contenido, tool_calls, tool_call_id, proveedor, created_at
            FROM mensajes
            WHERE session_id = %s
            ORDER BY orden ASC
            """,
            (session_id,),
        )
        filas = cur.fetchall()

    mensajes = []
    for rol, contenido, tool_calls, tool_call_id, proveedor, creado_en in filas:
        mensaje: dict = {"rol": rol, "contenido": contenido, "creado_en": creado_en.isoformat()}
        if tool_calls is not None:
            mensaje["tool_calls"] = tool_calls
        if tool_call_id is not None:
            mensaje["tool_call_id"] = tool_call_id
        if proveedor is not None:
            mensaje["proveedor"] = proveedor
        mensajes.append(mensaje)
    return mensajes
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_admin_chats_repository.py -v`
Expected: PASS (toda la suite del archivo, incluyendo el test nuevo)

- [ ] **Step 5: Correr la suite completa del backend**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: PASS (toda la suite, sin regresiones)

- [ ] **Step 6: Commit**

```bash
git add backend/agent/admin/chats_repository.py backend/tests/test_admin_chats_repository.py
git commit -m "feat: exponer el proveedor del LLM en el detalle de sesión del admin"
```

---

## Frontend

### Task 6: Badge de proveedor en el detalle de sesión del admin

**Files:**
- Modify: `frontend/lib/admin-api.ts`
- Modify: `frontend/app/admin/chats/[id]/page.tsx`

**Interfaces:**
- Consumes: campo `proveedor` que ahora puede venir en la respuesta de `GET /admin/sesiones/{id}` (Task 5).

No hay test automatizado (mismo criterio que el resto del panel de admin).

- [ ] **Step 1: Agregar el campo al tipo `MensajeAdmin`**

En `frontend/lib/admin-api.ts`, el tipo pasa de:

```typescript
export type MensajeAdmin = {
  rol: "user" | "assistant" | "tool";
  contenido: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  creado_en: string;
};
```

a:

```typescript
export type MensajeAdmin = {
  rol: "user" | "assistant" | "tool";
  contenido: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  proveedor?: string;
  creado_en: string;
};
```

- [ ] **Step 2: Mostrar el badge en el detalle de sesión**

En `frontend/app/admin/chats/[id]/page.tsx`, dentro del `visibles.map(...)`, el bloque:

```tsx
        <BurbujaMensaje key={indice} esUsuario={mensaje.rol === "user"}>
          <p className="whitespace-pre-wrap">{mensaje.contenido}</p>
          {mensaje.rol === "assistant" && mensaje.tool_calls && mensaje.tool_calls.length > 0 && (
            <DetalleTecnico mensaje={mensaje} todosLosMensajes={mensajes} />
          )}
        </BurbujaMensaje>
```

pasa a:

```tsx
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
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores nuevos

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/admin-api.ts "frontend/app/admin/chats/[id]/page.tsx"
git commit -m "feat: badge de proveedor (OpenAI/Gemini) en el detalle de sesión del admin"
```

---

### Task 7: Verificación manual

**Files:** ninguno (solo verificación).

- [ ] **Step 1: Confirmar que sin `GEMINI_API_KEY` el comportamiento es idéntico al actual**

Sin setear `GEMINI_API_KEY` en `.env` (estado actual), con `OPENAI_API_KEY` inválida (como está hoy en este entorno): preguntar algo en el chat público (`http://localhost:3000`).

Expected: el chat muestra el mismo mensaje de error genérico que mostraba antes de este plan — ningún cambio de comportamiento observable.

- [ ] **Step 2: (Si hay una `GEMINI_API_KEY` real disponible) Verificar el fallback en vivo**

Setear `GEMINI_API_KEY` en `.env` con una key real, reiniciar el backend (o confiar en `--reload`), y con `OPENAI_API_KEY` todavía inválida, preguntar algo en el chat público.

Expected: el chat responde igual (el usuario no nota diferencia), y en los logs de `uvicorn` aparece la línea `OpenAI falló, usando fallback a Gemini`.

- [ ] **Step 3: Verificar el badge en el admin**

Loguearse en `/admin/login`, entrar a `/admin/chats`, abrir la sesión generada en el Step 2.

Expected: el turno que usó el fallback muestra el badge "Gemini" junto a la respuesta del asistente.

Si no hay una `GEMINI_API_KEY` real disponible para probar el Step 2 en vivo, se puede simular sembrando un mensaje con `proveedor="gemini"` directamente en Postgres (mismo patrón usado en la verificación manual de planes anteriores) para confirmar al menos que el badge se renderiza correctamente.

- [ ] **Step 4: Correr toda la suite de tests una última vez**

Run: `cd backend && source .venv/bin/activate && pytest -v`
Run: `cd frontend && npx tsc --noEmit`
Expected: PASS en ambos.
