# Macacha — Fallback a Gemini para chat, rerank y generación de FAQs

## Contexto

Hoy los tres usos de OpenAI que son llamados de texto→texto (chat completions
del agente, rerank de resultados de búsqueda, generación automática de FAQs
en la ingesta) dependen enteramente de que `OPENAI_API_KEY` funcione — si
falla (como está pasando ahora mismo en el entorno local, con la key
vencida), el agente no puede responder nada. Este documento agrega Gemini
como fallback opcional para esos tres usos.

**Fuera de alcance de este documento**: `generate_embeddings` (usa un modelo
de 1536 dimensiones fijo en el schema de Postgres; Gemini usa otra
dimensión — necesita su propio diseño, sub-proyecto aparte).

## Por qué reusar el SDK de OpenAI

Google ofrece un endpoint compatible con la API de OpenAI para Gemini
(`https://generativelanguage.googleapis.com/v1beta/openai/`), usable con el
mismo SDK `openai` que ya está instalado — mismo `chat.completions.create()`,
mismo formato de tool-calling, mismo `response_format={"type":
"json_object"}`. Esto evita escribir cualquier conversor de formato de
mensajes/tools entre proveedores: "usar Gemini" es simplemente instanciar
otro `OpenAI(api_key=..., base_url=...)`.

## Arquitectura del fallback

Cada wrapper (`ChatClient` en `agent/chat_client.py`, `OpenAIClient` en
`ingest/openai_client.py`) recibe un segundo cliente SDK opcional, el de
Gemini. Cada método que llama al LLM (`completar`, `rerank`,
`generate_faqs`) sigue el mismo patrón:

1. Intenta la llamada contra el cliente primario (OpenAI).
2. Si tira **cualquier excepción** y hay un cliente de Gemini configurado:
   imprime un aviso a stdout y reintenta la misma llamada (mismos
   `messages`/`tools`/`response_format`) contra Gemini.
3. Si Gemini también falla, o no hay cliente de Gemini configurado
   (`GEMINI_API_KEY` no seteada), se propaga la excepción — la de Gemini
   en el caso 3a (es el último error real), la de OpenAI en el caso 3b (no
   se intentó nada más).

No hay reintentos múltiples ni backoff: un solo intento por proveedor. No
se distingue tipo de error (auth, rate limit, timeout, 5xx) — cualquier
excepción dispara el fallback.

**Configuración**: `.env` suma `GEMINI_API_KEY` (opcional). Si no está
seteada, el comportamiento es idéntico al actual — sin cliente de fallback,
la excepción de OpenAI se propaga tal cual. Modelo fijo como constante,
`"gemini-2.0-flash"`, igual criterio que ya usa el código con
`gpt-4o-mini` (una sola constante para todos los usos, no configurable por
env).

## Chat completions — persistencia del proveedor

**`agent/chat_client.py`**:

```python
class ChatClient:
    MODEL_OPENAI = "gpt-4o-mini"
    MODEL_GEMINI = "gemini-2.0-flash"

    def __init__(self, sdk_client, sdk_client_gemini=None):
        self._sdk_client = sdk_client
        self._sdk_client_gemini = sdk_client_gemini

    def completar(self, messages: list[dict], tools: list[dict]) -> dict:
        # intenta OpenAI, cae a Gemini si falla y hay cliente configurado
        # devuelve {"role": "assistant", "content": ..., "tool_calls": ..., "proveedor": "openai" | "gemini"}
```

`build_real_chat_client()` arma el cliente Gemini solo si
`os.environ.get("GEMINI_API_KEY")` está seteada.

**Schema**: `ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS proveedor TEXT;`
— nullable; solo se completa en mensajes `assistant` que dispararon una
llamada real al LLM.

**`agent/sessions.py`**: `guardar_mensaje` suma un parámetro opcional
`proveedor: str | None = None`, insertado en la columna nueva. Las llamadas
existentes que no lo pasan siguen funcionando, guardando `NULL`.

**`agent/orchestrator.py`**: en `procesar_turno`, cada `guardar_mensaje` de
un mensaje `assistant` pasa `proveedor=respuesta.get("proveedor")` — se usa
`.get()`, no acceso directo por clave, para que los tests existentes que
arman respuestas fake de chat client sin la clave `"proveedor"` no se
rompan (persisten `NULL` en ese caso).

## Rerank y generación de FAQs — mismo mecanismo, sin persistencia

**`ingest/openai_client.py`**: `OpenAIClient` recibe también un
`sdk_client_gemini` opcional en el constructor. `rerank()` y
`generate_faqs()` siguen el mismo patrón try/except que `completar()`, pero
sin devolver ni persistir qué proveedor respondió — solo un `print()` a
stdout si se usó el fallback. `generate_embeddings()` no cambia.

`build_real_client()` arma el cliente Gemini con el mismo criterio que
`build_real_chat_client()`.

## Panel de admin — mostrar el proveedor

`agent/admin/chats_repository.py`'s `obtener_mensajes_completos` suma
`proveedor` al `SELECT` y al dict devuelto, solo cuando no es `NULL` (mismo
patrón condicional que ya usa con `tool_calls`/`tool_call_id`).

Frontend: `lib/admin-api.ts`'s tipo `MensajeAdmin` suma `proveedor?:
string`. En `app/admin/chats/[id]/page.tsx`, cada burbuja de `assistant`
que tenga `proveedor` muestra un badge chico ("OpenAI" / "Gemini") junto al
botón "Ver detalle técnico" existente.

## Testing

- **`ChatClient.completar`**: OpenAI falla + Gemini configurado y responde
  bien → `proveedor == "gemini"`; OpenAI responde bien → `proveedor ==
  "openai"` y Gemini nunca se llama (verificable con un mock que falla si
  se invoca); ambos fallan → se propaga la excepción de Gemini; sin cliente
  Gemini (`None`) y falla OpenAI → se propaga la excepción original de
  OpenAI sin intentar nada más.
- Mismo set de casos para `OpenAIClient.rerank` y `.generate_faqs`.
- **`agent/sessions.py`**: `guardar_mensaje` persiste `proveedor` cuando se
  pasa; lo deja `NULL` cuando no se pasa (compatibilidad).
- **`agent/orchestrator.py`**: test de que cuando el chat client fake
  devuelve `proveedor`, se guarda correctamente en el mensaje `assistant`;
  los tests existentes con respuestas fake sin esa clave siguen pasando sin
  modificarlos.
- **`chats_repository.obtener_mensajes_completos`**: `proveedor` aparece en
  el dict cuando la columna no es `NULL`, está ausente cuando sí lo es.
- **Frontend**: sin test automatizado para el badge (mismo criterio que el
  resto del panel de admin — sin `jsdom`/`@testing-library`).

## Fuera de alcance

- Fallback de `generate_embeddings` (sub-proyecto aparte).
- Exponer el proveedor en el stream SSE del chat público — solo se
  persiste en DB y se muestra en el admin.
- Reintentos múltiples o backoff antes de caer a Gemini.
- Elegir proveedor por un criterio distinto a "OpenAI tiró una excepción"
  (balanceo de carga, costo, latencia).
- Tracking del proveedor usado en rerank/generación de FAQs más allá de un
  `print()` a stdout (no hay un registro persistente natural para esos dos
  usos, a diferencia del chat que tiene la tabla `mensajes`).

## Comportamiento explícito no obvio

- Si Gemini también falla, se propaga **la excepción de Gemini**, no la de
  OpenAI — es el último error real que impidió responder.
- El modelo `gemini-2.0-flash` y la compatibilidad exacta del endpoint de
  Gemini con `tools=`/`response_format` de este proyecto son un supuesto a
  verificar empíricamente en la primera llamada real contra la API durante
  la implementación — si el endpoint rechaza algo del formato (tool
  schemas, JSON mode), se ajusta ahí; no bloquea este diseño.
- Agregar la columna `proveedor` a `mensajes` requiere correr el `ALTER
  TABLE` contra el Postgres ya corriendo (o recrear el volumen) para que
  aplique — no es automático sobre un contenedor ya inicializado, mismo
  caso que la tabla `admins` en el plan anterior.
- **El fallback NO cubre los turnos que disparan búsqueda.** Como
  `generate_embeddings` queda fuera de alcance (ver arriba) y no tiene
  fallback, cualquier turno donde el modelo llame a la tool
  `buscar_tramite` sigue dependiendo enteramente de que `OPENAI_API_KEY`
  funcione — si OpenAI está caído, ese turno falla igual aunque Gemini esté
  configurado y funcionando, porque `embed_fn` explota antes de llegar a
  usar el resultado. El fallback cubre las respuestas conversacionales
  puras (sin tool call) y las que solo llaman a tools de lookup directo por
  `tramite_id` ya conocido (no pasan por embeddings), más rerank y FAQs.
  Es decir: cubre una parte real pero acotada del tráfico — no un caso
  "el agente sigue funcionando entero ante una caída de OpenAI".
- **Los mensajes del ciudadano se envían a un segundo proveedor externo
  (Google) cuando se dispara el fallback.** Es una decisión consciente,
  aceptada para el alcance actual de este proyecto, pero vale dejarla
  documentada: mientras el fallback esté activo y se dispare, el contenido
  de la conversación (que puede incluir detalles personales del trámite que
  la persona está consultando) sale de la infraestructura de OpenAI y pasa
  por la API de Google Generative Language. No hay opt-out por sesión ni
  aviso al usuario final — es invisible salvo para un admin mirando el
  badge en `/admin/chats`.

## Criterios de aceptación

- Con `GEMINI_API_KEY` sin setear, el comportamiento del chat/rerank/FAQs
  es idéntico al actual (sin cambios de UI, sin cambios de respuesta ante
  una falla de OpenAI).
- Con `GEMINI_API_KEY` seteada y `OPENAI_API_KEY` inválida (como está hoy
  en este entorno), **un turno conversacional que no dispare `buscar_tramite`**
  (saludo, pregunta general, o una tool de lookup directo con
  `tramite_id` ya conocido) sigue respondiendo — la respuesta viene de
  Gemini. Un turno que sí dispare `buscar_tramite` sigue fallando igual que
  hoy, porque `generate_embeddings` no tiene fallback (ver "Comportamiento
  explícito no obvio").
- En el panel de admin, la sesión del turno que usó el fallback muestra el
  badge "Gemini" junto a esa respuesta.
- Con ambas keys inválidas, el chat público muestra el mismo mensaje de
  error genérico que ya muestra hoy ante una falla de OpenAI.
