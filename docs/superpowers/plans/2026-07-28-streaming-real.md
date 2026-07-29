# Streaming real token-a-token (sub-proyecto B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el trozeado artificial de la respuesta del chat por streaming real: los eventos SSE que recibe el frontend son los tokens que el LLM genera en el momento, no una respuesta completa troceada después.

**Architecture:** `ChatClient` gana un método generador `completar_streaming` que reemplaza a `completar` (se elimina); `orchestrator.py` itera ese generador y reenvía cada delta de contenido como evento SSE en el momento en que llega, en vez de esperar la respuesta completa. El frontend no cambia — `useChatStream.ts` ya consume eventos delta uno por uno.

**Tech Stack:** Python (backend existente, sin dependencias nuevas — el SDK de `openai` ya soporta `stream=True`).

## Global Constraints

- Ningún cambio en el frontend — `useChatStream.ts` ya consume eventos `{"tipo": "texto", "delta": ...}` incrementalmente.
- Ningún cambio en `backend/agent/api.py` — el `try/except` que ya existe en el endpoint `/chat` (líneas 93-96) ya corta la respuesta con un evento de error genérico si el streaming falla a mitad de camino; no hace falta duplicar esa lógica en `orchestrator.py`.
- El fallback a Gemini en `completar_streaming` solo se intenta si la excepción ocurre en la llamada `.create()` (antes de iterar el stream) — si falla durante la iteración (con contenido ya emitido), la excepción se propaga sin reintentar.
- `ChatClient.completar` y `agent/orchestrator._emitir_respuesta_trozeada` se eliminan del código — no queda ningún caller de ninguno de los dos al finalizar este plan.
- Ningún cambio en `ingest/openai_client.py` (rerank, embeddings, FAQs) — usan su propio cliente OpenAI directo, no pasan por `ChatClient`.

---

### Task 1: `ChatClient.completar_streaming`

**Files:**
- Modify: `backend/agent/chat_client.py`
- Modify: `backend/tests/test_chat_client.py` (reescritura completa — los fakes actuales simulan una respuesta completa, no un stream de chunks)

**Interfaces:**
- Consumes: nada nuevo (mismo `self._sdk_client` / `self._sdk_client_gemini` ya inyectados en `ChatClient.__init__`).
- Produces: `completar_streaming(self, messages: list[dict], tools: list[dict])` — generador que yieldea:
  - `{"tipo": "delta", "texto": str}` por cada fragmento de contenido que llega.
  - Como último evento: `{"tipo": "fin", "content": str | None, "tool_calls": list[dict] | None, "proveedor": "openai" | "gemini"}`.
  Task 2 (`orchestrator.py`) consume este generador con esta forma exacta.

- [ ] **Step 1: Reescribir `backend/tests/test_chat_client.py`**

Reemplazar TODO el contenido del archivo por:

```python
from agent.chat_client import ChatClient


class _FakeDeltaFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _FakeToolCallDelta:
    def __init__(self, index, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class _FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeChunkChoice:
    def __init__(self, delta):
        self.delta = delta


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [_FakeChunkChoice(delta)]


class _FakeCompletions:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks if chunks is not None else []
        self._error = error
        self.last_call = None
        self.llamadas = 0

    def create(self, model, messages, tools, stream=False):
        self.llamadas += 1
        self.last_call = {"model": model, "messages": messages, "tools": tools, "stream": stream}
        if self._error is not None:
            raise self._error
        return iter(self._chunks)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAISDK:
    def __init__(self, chunks=None, error=None):
        self.chat = _FakeChat(_FakeCompletions(chunks=chunks, error=error))


def test_completar_streaming_devuelve_respuesta_sin_tool_calls():
    chunks = [
        _FakeChunk(_FakeDelta(content="Hola, ")),
        _FakeChunk(_FakeDelta(content="¿en qué te ayudo?")),
    ]
    fake_openai = _FakeOpenAISDK(chunks=chunks)
    client = ChatClient(fake_openai)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))

    deltas = [e["texto"] for e in eventos if e["tipo"] == "delta"]
    assert deltas == ["Hola, ", "¿en qué te ayudo?"]
    assert eventos[-1] == {
        "tipo": "fin",
        "content": "Hola, ¿en qué te ayudo?",
        "tool_calls": None,
        "proveedor": "openai",
    }
    assert fake_openai.chat.completions.last_call["model"] == "gpt-4o-mini"
    assert fake_openai.chat.completions.last_call["stream"] is True


def test_completar_streaming_acumula_tool_calls_fragmentados():
    chunks = [
        _FakeChunk(_FakeDelta(tool_calls=[
            _FakeToolCallDelta(0, id="call_1", function=_FakeDeltaFunction(name="buscar_tramite", arguments=""))
        ])),
        _FakeChunk(_FakeDelta(tool_calls=[
            _FakeToolCallDelta(0, function=_FakeDeltaFunction(arguments='{"query"'))
        ])),
        _FakeChunk(_FakeDelta(tool_calls=[
            _FakeToolCallDelta(0, function=_FakeDeltaFunction(arguments=': "acta"}'))
        ])),
    ]
    fake_openai = _FakeOpenAISDK(chunks=chunks)
    client = ChatClient(fake_openai)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "quiero un acta"}], tools=[]))

    assert len(eventos) == 1
    assert eventos[-1] == {
        "tipo": "fin",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
            }
        ],
        "proveedor": "openai",
    }


def test_completar_streaming_usa_gemini_si_openai_falla():
    fake_openai = _FakeOpenAISDK(error=RuntimeError("401 de OpenAI"))
    fake_gemini = _FakeOpenAISDK(chunks=[_FakeChunk(_FakeDelta(content="Respuesta de Gemini"))])
    client = ChatClient(fake_openai, fake_gemini)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))

    deltas = [e["texto"] for e in eventos if e["tipo"] == "delta"]
    assert "".join(deltas) == "Respuesta de Gemini"
    assert eventos[-1] == {
        "tipo": "fin",
        "content": "Respuesta de Gemini",
        "tool_calls": None,
        "proveedor": "gemini",
    }
    assert fake_gemini.chat.completions.last_call["model"] == "gemini-2.0-flash"


def test_completar_streaming_no_llama_a_gemini_si_openai_responde_bien():
    fake_openai = _FakeOpenAISDK(chunks=[_FakeChunk(_FakeDelta(content="Hola"))])
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("no debería llamarse"))
    client = ChatClient(fake_openai, fake_gemini)

    eventos = list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))

    assert eventos[-1]["proveedor"] == "openai"
    assert fake_gemini.chat.completions.llamadas == 0


def test_completar_streaming_sin_cliente_gemini_propaga_error_de_openai():
    fake_openai = _FakeOpenAISDK(error=ValueError("401 de OpenAI"))
    client = ChatClient(fake_openai)

    try:
        list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))
        assert False, "debería haber propagado la excepción"
    except ValueError as exc:
        assert str(exc) == "401 de OpenAI"


def test_completar_streaming_con_ambos_proveedores_fallando_propaga_error_de_gemini():
    fake_openai = _FakeOpenAISDK(error=ValueError("falla de OpenAI"))
    fake_gemini = _FakeOpenAISDK(error=RuntimeError("falla de Gemini"))
    client = ChatClient(fake_openai, fake_gemini)

    try:
        list(client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[]))
        assert False, "debería haber propagado la excepción"
    except RuntimeError as exc:
        assert str(exc) == "falla de Gemini"


def test_completar_streaming_corte_a_mitad_de_stream_no_reintenta_con_gemini():
    def chunks_que_se_cortan():
        yield _FakeChunk(_FakeDelta(content="Hola"))
        raise RuntimeError("se cortó la conexión")

    fake_openai = _FakeOpenAISDK(chunks=chunks_que_se_cortan())
    fake_gemini = _FakeOpenAISDK(chunks=[_FakeChunk(_FakeDelta(content="no debería usarse"))])
    client = ChatClient(fake_openai, fake_gemini)

    generador = client.completar_streaming(messages=[{"role": "user", "content": "hola"}], tools=[])

    primer_evento = next(generador)
    assert primer_evento == {"tipo": "delta", "texto": "Hola"}

    try:
        next(generador)
        assert False, "debería haber propagado la excepción"
    except RuntimeError as exc:
        assert str(exc) == "se cortó la conexión"
    assert fake_gemini.chat.completions.llamadas == 0
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_chat_client.py -v`
Expected: FAIL — `AttributeError: 'ChatClient' object has no attribute 'completar_streaming'` en todos los tests.

- [ ] **Step 3: Reescribir `backend/agent/chat_client.py`**

Reemplazar TODO el contenido del archivo por:

```python
import os


class ChatClient:
    MODEL_OPENAI = "gpt-4o-mini"
    MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

    def completar_streaming(self, messages: list[dict], tools: list[dict]):
        try:
            stream = self._sdk_client.chat.completions.create(
                model=self.MODEL_OPENAI, messages=messages, tools=tools, stream=True
            )
            proveedor = "openai"
        except Exception:
            if self._sdk_client_gemini is None:
                raise
            print("OpenAI falló, usando fallback a Gemini")
            stream = self._sdk_client_gemini.chat.completions.create(
                model=self.MODEL_GEMINI, messages=messages, tools=tools, stream=True
            )
            proveedor = "gemini"

        contenido_acumulado = ""
        tool_calls_acumulados: dict[int, dict] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                contenido_acumulado += delta.content
                yield {"tipo": "delta", "texto": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    entrada = tool_calls_acumulados.setdefault(
                        tc.index,
                        {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if tc.id:
                        entrada["id"] = tc.id
                    if tc.function and tc.function.name:
                        entrada["function"]["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        entrada["function"]["arguments"] += tc.function.arguments

        tool_calls = [tool_calls_acumulados[i] for i in sorted(tool_calls_acumulados)] or None

        yield {
            "tipo": "fin",
            "content": contenido_acumulado or None,
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

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_chat_client.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/agent/chat_client.py backend/tests/test_chat_client.py
git commit -m "feat: agregar ChatClient.completar_streaming y eliminar completar"
```

---

### Task 2: `orchestrator.py` consume el streaming

**Files:**
- Modify: `backend/agent/orchestrator.py`
- Modify: `backend/tests/test_orchestrator.py` (solo la clase `_FakeChatClient`, líneas 16-24)
- Modify: `backend/tests/test_api.py` (solo la clase `_FakeChatClient`, líneas 31-39)

**Interfaces:**
- Consumes: `chat_client.completar_streaming(messages, tools)` de Task 1 — generador que yieldea `{"tipo": "delta", "texto": ...}` y termina con `{"tipo": "fin", "content": ..., "tool_calls": ..., "proveedor": ...}`.
- Produces: sin cambios en la interfaz pública de `procesar_turno` — sigue siendo un generador que yieldea `{"tipo": "texto", "delta": ...}`, `{"tipo": "fin", "fuentes": [...]}`.

- [ ] **Step 1: Actualizar `_FakeChatClient` en `backend/tests/test_orchestrator.py`**

Reemplazar las líneas 16-24 (la clase `_FakeChatClient` completa) por:

```python
class _FakeChatClient:
    def __init__(self, respuestas):
        self._respuestas = respuestas
        self._indice = 0

    def completar_streaming(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        if respuesta.get("content"):
            yield {"tipo": "delta", "texto": respuesta["content"]}
        yield {
            "tipo": "fin",
            "content": respuesta.get("content"),
            "tool_calls": respuesta.get("tool_calls"),
            "proveedor": respuesta.get("proveedor", "openai"),
        }
```

El resto del archivo (todos los tests) queda sin cambios — siguen construyendo
`_FakeChatClient` con la misma lista de dicts `{"role": ..., "content": ..., "tool_calls": ..., "proveedor": ...}` que ya usaban.

- [ ] **Step 2: Actualizar `_FakeChatClient` en `backend/tests/test_api.py`**

Reemplazar las líneas 31-39 (la clase `_FakeChatClient` completa) por el mismo código del Step 1:

```python
class _FakeChatClient:
    def __init__(self, respuestas):
        self._respuestas = respuestas
        self._indice = 0

    def completar_streaming(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        if respuesta.get("content"):
            yield {"tipo": "delta", "texto": respuesta["content"]}
        yield {
            "tipo": "fin",
            "content": respuesta.get("content"),
            "tool_calls": respuesta.get("tool_calls"),
            "proveedor": respuesta.get("proveedor", "openai"),
        }
```

El resto del archivo queda sin cambios.

- [ ] **Step 3: Correr los tests de orchestrator y api, verificar que fallan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_orchestrator.py tests/test_api.py -v`
Expected: FAIL — `orchestrator.py` todavía llama a `chat_client.completar(...)`, que ya no existe en el fake (`AttributeError`).

- [ ] **Step 4: Reescribir `backend/agent/orchestrator.py`**

Reemplazar TODO el contenido del archivo por:

```python
import json

from agent import sessions
from agent.tools import TOOL_SCHEMAS, ejecutar_tool
from ingest.repository import obtener_snapshot_vigente

SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Tu objetivo es ayudar a las personas a entender y "
    "completar sus trámites de la forma más simple posible. Sabés que muchos "
    "trámites pueden ser confusos o estresantes, así que tratá a cada persona "
    "con calidez y empatía — como alguien de confianza que se toma el trabajo en "
    "serio, no como un formulario que recita datos. Podés usar un tono cercano y "
    "humano. Contá las cosas como lo haría una persona explicándole a otra: en "
    "oraciones seguidas, no como una lista de trámite. Usá viñetas o numeración "
    "solo si hay varios ítems y de verdad ayuda a leerlos (por ejemplo, más de "
    "cuatro requisitos o pasos) — nunca como formato por defecto. Variá cómo "
    "empezás y cerrás cada respuesta: no repitas la misma pregunta de cierre en "
    "todos los mensajes. Si la persona comenta que algo le resulta tedioso, "
    "confuso o frustrante, reconocelo antes de pasar a la información, en vez "
    "de ignorarlo. No uses emojis. Sin perder precisión: respondé siempre "
    "basándote únicamente en la información que te devuelven las herramientas "
    "disponibles, nunca inventes requisitos, costos, pasos ni plazos. Si la "
    "herramienta buscar_tramite devuelve varios trámites candidatos y no está "
    "claro cuál necesita la persona, preguntá con calidez para desambiguar "
    "antes de usar las demás herramientas. Cuando menciones un trámite, usá su "
    "nombre oficial y, si corresponde, su enlace oficial."
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

    tramites_citados: list[str] = []

    for _ in range(MAX_ITERACIONES_TOOLS):
        contenido = ""
        tool_calls = None
        proveedor = None

        for evento in chat_client.completar_streaming(messages=messages, tools=TOOL_SCHEMAS):
            if evento["tipo"] == "delta":
                yield {"tipo": "texto", "delta": evento["texto"]}
            else:
                contenido = evento["content"]
                tool_calls = evento["tool_calls"]
                proveedor = evento["proveedor"]

        if not tool_calls:
            sessions.guardar_mensaje(
                conn,
                session_id,
                rol="assistant",
                contenido=contenido,
                proveedor=proveedor,
            )
            yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
            return

        sessions.guardar_mensaje(
            conn,
            session_id,
            rol="assistant",
            contenido=contenido,
            tool_calls=tool_calls,
            proveedor=proveedor,
        )
        messages.append(
            {
                "role": "assistant",
                "content": contenido,
                "tool_calls": tool_calls,
            }
        )

        for tool_call in tool_calls:
            nombre = tool_call["function"]["name"]
            argumentos = json.loads(tool_call["function"]["arguments"])
            resultado = ejecutar_tool(nombre, argumentos, conn, embed_fn, rerank_fn)

            if "tramite_id" in argumentos and argumentos["tramite_id"] not in tramites_citados:
                tramites_citados.append(argumentos["tramite_id"])

            resultado_json = json.dumps(resultado, ensure_ascii=False)
            sessions.guardar_mensaje(
                conn, session_id, rol="tool", contenido=resultado_json, tool_call_id=tool_call["id"]
            )
            messages.append(
                {"role": "tool", "content": resultado_json, "tool_call_id": tool_call["id"]}
            )

    mensaje_agotado = "No pude resolver tu consulta en este momento. ¿Podés reformularla?"
    sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield {"tipo": "texto", "delta": mensaje_agotado}
    yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}


def _armar_fuentes(conn, tramites_citados: list[str]) -> list[dict]:
    fuentes = []
    for tramite_id in tramites_citados:
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

Nota: `_emitir_respuesta_trozeada` queda eliminada — ya no existe en el archivo.

- [ ] **Step 5: Correr los tests de orchestrator y api, verificar que pasan**

Run: `cd backend && source .venv/bin/activate && pytest tests/test_orchestrator.py tests/test_api.py -v`
Expected: PASS (7 tests en `test_orchestrator.py`, 3 en `test_api.py`).

- [ ] **Step 6: Correr toda la suite del backend**

Run: `cd backend && source .venv/bin/activate && pytest -q`
Expected: todos los tests pasan (149 tests previos, menos los 6 viejos de `completar` que ya no existen, más los 7 nuevos de `completar_streaming` de Task 1 — el número total cambia levemente, lo importante es 0 failures).

- [ ] **Step 7: Commit**

```bash
git add backend/agent/orchestrator.py backend/tests/test_orchestrator.py backend/tests/test_api.py
git commit -m "feat: orchestrator consume streaming real en vez de trocear la respuesta"
```

---

### Task 3: Verificación manual

**Files:** ninguno (solo verificación).

**Interfaces:**
- Consumes: backend real corriendo (reiniciar el proceso de `uvicorn` para que cargue el código nuevo, ya que corre con `--reload` pero conviene confirmar), endpoint `POST /chat`.

- [ ] **Step 1: Confirmar que el streaming llega en fragmentos reales, no todo junto**

Run:
```bash
SESSION_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID\",\"mensaje\":\"hola\"}"
```
Expected: se ven múltiples líneas `data: {"tipo": "texto", "delta": "..."}` a medida que curl las recibe (con `-N` para no bufferear) — cada delta es un fragmento real del LLM (puede ser una palabra, parte de una palabra, o varias palabras juntas, según cómo tokenice el modelo — ya no son palabras completas separadas por espacios como con el trozeado artificial anterior).

- [ ] **Step 2: Confirmar que una consulta con tool calls sigue funcionando end-to-end**

Run:
```bash
SESSION_ID_2=$(python3 -c "import uuid; print(uuid.uuid4())")
curl -s -N -m 30 -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION_ID_2\",\"mensaje\":\"qué necesito para hacer el seguimiento y descarga de mi acta\"}"
```
Expected: la respuesta llega en streaming y el evento final `{"tipo": "fin", "fuentes": [...]}` trae `RC-0004` (o el trámite que corresponda) en `fuentes` — confirma que el loop de tool-calls (que ahora también pasa por streaming en cada ronda) sigue armando bien las fuentes.

- [ ] **Step 3: Reportar resultado**

Si ambos pasos confirman streaming real y las fuentes se arman bien, marcar la tarea como completa.
