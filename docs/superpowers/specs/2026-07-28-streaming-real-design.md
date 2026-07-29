# Macacha — Streaming real token-a-token (sub-proyecto B de 4)

## Contexto

Tercero de los 4 sub-proyectos para humanizar el chat (orden acordado:
A → D → B → C). **A** (personalidad/estilo del prompt) y **D** (panel
toolbox) ya están completos. Este documento cubre **B**: hoy
`backend/agent/orchestrator.py` arma la respuesta completa del LLM y recién
ahí la trocea artificialmente en palabras (`_emitir_respuesta_trozeada`)
para simular un efecto de "escritura en vivo". Este sub-proyecto reemplaza
eso por streaming real: los eventos SSE que llegan al frontend son los
mismos tokens que el LLM va generando, en el momento en que los genera.

El frontend (`frontend/hooks/useChatStream.ts`) **no necesita ningún
cambio** — ya consume eventos `{"tipo": "texto", "delta": ...}` uno por uno
y los va concatenando a medida que llegan; hoy simplemente los recibe a un
ritmo artificial.

## Qué cambia

Solo backend: `backend/agent/chat_client.py` y `backend/agent/orchestrator.py`,
más sus tests.

### 1. `ChatClient.completar_streaming` reemplaza a `completar`

`completar` (no streaming) hoy solo lo usa `orchestrator.py`; al migrar
ese caller, queda sin uso y se elimina (YAGNI), junto con sus tests
actuales en `tests/test_chat_client.py`.

```python
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
```

**Semántica del fallback a Gemini** (decisión tomada en el brainstorming):
el `try/except` envuelve *solo* la llamada `.create()` — ahí es donde ya
falla hoy un error de auth/modelo, porque el SDK de OpenAI hace el
handshake HTTP en esa llamada. El `for chunk in stream:` que sigue **no**
está protegido: si el stream se corta ahí (con contenido ya emitido al
cliente), la excepción se propaga sin reintentar con Gemini — evita
mezclar/duplicar texto ya mostrado.

### 2. `orchestrator.py` — consumir el streaming en vez de trocear

```python
for _ in range(MAX_ITERACIONES_TOOLS):
    contenido, tool_calls, proveedor = "", None, None

    for evento in chat_client.completar_streaming(messages=messages, tools=TOOL_SCHEMAS):
        if evento["tipo"] == "delta":
            yield {"tipo": "texto", "delta": evento["texto"]}
        else:
            contenido, tool_calls, proveedor = evento["content"], evento["tool_calls"], evento["proveedor"]

    if not tool_calls:
        sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=contenido, proveedor=proveedor)
        yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
        return

    sessions.guardar_mensaje(
        conn, session_id, rol="assistant", contenido=contenido,
        tool_calls=tool_calls, proveedor=proveedor,
    )
    messages.append({"role": "assistant", "content": contenido, "tool_calls": tool_calls})

    for tool_call in tool_calls:
        nombre = tool_call["function"]["name"]
        argumentos = json.loads(tool_call["function"]["arguments"])
        resultado = ejecutar_tool(nombre, argumentos, conn, embed_fn, rerank_fn)
        if "tramite_id" in argumentos and argumentos["tramite_id"] not in tramites_citados:
            tramites_citados.append(argumentos["tramite_id"])
        resultado_json = json.dumps(resultado, ensure_ascii=False)
        sessions.guardar_mensaje(conn, session_id, rol="tool", contenido=resultado_json, tool_call_id=tool_call["id"])
        messages.append({"role": "tool", "content": resultado_json, "tool_call_id": tool_call["id"]})

mensaje_agotado = "No pude resolver tu consulta en este momento. ¿Podés reformularla?"
sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
yield {"tipo": "texto", "delta": mensaje_agotado}
yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
```

`_emitir_respuesta_trozeada` se elimina — el único caller que quedaba (el
mensaje fijo de "se agotaron los reintentos") ahora se manda como un único
evento de texto, sin trocear.

**El corte-con-error a mitad de stream ya funciona gratis, sin tocar
`api.py`:** `backend/agent/api.py:93-96` ya envuelve todo el consumo de
`procesar_turno` en un `try/except Exception` que hace `conn.rollback()` y
emite `{"tipo": "error", "mensaje": "Ocurrió un error al procesar tu
mensaje."}`. Ese `except` corre después de que varios `yield` ya se
mandaron al cliente — si `completar_streaming` explota a mitad de camino,
la excepción sube sin capturar por `procesar_turno` y cae directo en ese
handler existente. No requiere ningún cambio en `api.py`.

## Testing

Los fakes actuales del SDK de OpenAI en `tests/test_chat_client.py`
(`_FakeCompletions.create`) simulan una respuesta completa de una sola vez;
pasan a simular un iterable de chunks. Fakes nuevos:

```python
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


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [_FakeChunkChoice(delta)]


class _FakeChunkChoice:
    def __init__(self, delta):
        self.delta = delta
```

`_FakeCompletions.create(**kwargs)` pasa a devolver `iter(self._chunks)`
(o lanzar `self._error` si se configuró uno, igual que antes).

**Casos a cubrir en `test_chat_client.py`:**
- Streaming exitoso con OpenAI: varios chunks de `content`, se verifica que
  cada uno produce un evento `{"tipo": "delta", ...}` y el evento final
  junta todo el contenido con `proveedor: "openai"`.
- Fallback a Gemini cuando `.create()` de OpenAI lanza una excepción antes
  de devolver el stream (mismo caso que hoy, pero adaptado a streaming).
- Sin cliente Gemini configurado, propaga el error de OpenAI.
- Ambos proveedores fallan en `.create()`: propaga el error de Gemini.
- **Caso nuevo:** `tool_calls` fragmentados en 2-3 chunks (ej. `id` y
  `function.name` en el primer chunk, `function.arguments` partido en los
  siguientes dos) — el evento final debe traer el `tool_calls` completo y
  bien armado.
- **Caso nuevo:** un chunk con contenido seguido de una excepción durante
  la iteración (no en `.create()`) — se verifica que la excepción se
  propaga tal cual, sin intentar Gemini (aunque haya cliente Gemini
  configurado).

**`test_orchestrator.py` y `test_api.py`:** cada uno tiene su propio
`_FakeChatClient` duplicado; ambos pasan de exponer `completar(...) -> dict`
a exponer `completar_streaming(...) -> Iterator[dict]` (generador que yieldea
los mismos `"delta"`/`"fin"` armados a mano por cada test, replicando el
dict de respuesta que antes devolvían directo). Los asserts existentes
sobre el texto final concatenado y el evento `"fin"` con `fuentes` no
cambian — solo cambia cómo el fake entrega esos datos.

## Casos borde

- **`tool_calls` sin `id` en el primer fragmento:** algunos proveedores
  mandan el `id` recién en el segundo chunk de un mismo `tool_call` — el
  `setdefault` con `id: None` y la actualización condicional (`if tc.id:`)
  cubren esto sin romper.
- **Ronda con contenido de texto Y `tool_calls` en la misma respuesta:**
  técnicamente posible aunque raro con `gpt-4o-mini`. El contenido de esa
  ronda se muestra igual (se yieldean sus deltas), y luego el loop sigue a
  la ronda de tool calls con normalidad. No se agrega lógica para
  ocultarlo — es un comportamiento razonable y agregar la complejidad para
  prevenir un caso que casi no ocurre no se justifica.
- **`stream` se corta después de emitir contenido:** ver semántica del
  fallback arriba — no se reintenta, se propaga y el handler de `api.py`
  ya existente corta con el mensaje de error genérico.
- **Ronda de tool-calls sin contenido de texto:** `contenido_acumulado`
  queda `""`, se normaliza a `None` (`or None`) al armar el evento final,
  igual que hacía `mensaje.content` de la respuesta no-streaming original.

## Fuera de alcance

- Memoria conversacional más inteligente (sub-proyecto C, pendiente).
- Cualquier cambio en el frontend — `useChatStream.ts` ya consume eventos
  delta uno por uno, no necesita saber si vienen troceados artificialmente
  o son tokens reales.
- Cambios en `api.py` — el manejo de error a mitad de stream ya funciona
  con el `try/except` existente.
- Rerank y generación de FAQs (`ingest/openai_client.py`) — usan su propio
  cliente OpenAI directo, no pasan por `ChatClient`; no los toca este
  sub-proyecto.

## Criterios de aceptación

- Conversando con el chat real, el texto aparece de forma progresiva a
  medida que el LLM lo genera (no todo junto ni con un ritmo artificial
  palabra por palabra).
- Una consulta que dispara tool calls (ej. preguntar por un trámite real)
  sigue funcionando end-to-end: se ejecutan las tools, se arman las
  fuentes, y la respuesta final llega igual que antes.
- Los tests de `test_chat_client.py`, `test_orchestrator.py` y
  `test_api.py` pasan con los fakes actualizados a streaming.
- `ChatClient.completar` y `_emitir_respuesta_trozeada` ya no existen en
  el código.
