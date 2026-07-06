# Macacha — Agente conversacional (tools + orquestación + sesiones + FastAPI)

## Contexto general del sistema

Este es el **tercer** de los cuatro subsistemas de Macacha, el asistente
virtual de trámites de la administración pública de la Provincia de Salta:

1. **Núcleo de datos** (implementado): esquema Postgres+pgvector con
   versionado de trámites y pipeline de ingesta.
2. **Motor de recuperación** (implementado): `backend/retrieval/`, búsqueda
   híbrida (vectorial + full-text) fusionada por RRF y re-ranking vía LLM,
   expuesta como `hybrid_search.buscar_chunks(query, conn, embed_fn,
   rerank_fn, top_k=5) -> list[dict]`.
3. **Agente conversacional** (este documento): tool-calling nativo de OpenAI
   sobre 7 herramientas separadas, orquestado en FastAPI, con sesiones e
   historial de conversación persistentes en Postgres y streaming de la
   respuesta final al frontend.
4. **Frontend** (próxima etapa): chat en Next.js + Tailwind consumiendo el
   endpoint de chat de este subsistema.

### Pendiente heredado del motor de recuperación

La revisión final de ese subsistema dejó anotado que `buscar_chunks` asume
una conexión con `pgvector.psycopg.register_vector(conn)` ya aplicado, sin
forzarlo. Este documento lo resuelve: el pool de conexiones de este
subsistema (`backend/db/pool.py`) registra el adaptador en cada conexión
nueva que crea, así que cualquier conexión que la app FastAPI le pase a
`buscar_chunks` ya lo tiene aplicado.

## Alcance

Un servicio FastAPI (`backend/agent/`) que exponga un endpoint de chat con
streaming, capaz de:

1. Mantener una conversación multi-turno por sesión anónima (UUID generado
   por el frontend, sin login), persistiendo cada turno en Postgres.
2. Decidir, vía tool-calling nativo de OpenAI, qué herramienta(s) invocar
   para responder — nunca inventar información no traída por una tool.
3. Streamear la respuesta final al cliente (no los pasos intermedios de
   tool-calling, que se resuelven de forma síncrona).
4. Citar los trámites/enlaces oficiales usados como fuente en cada turno.

## Estructura de archivos

```
backend/
  db/
    pool.py                 # ConnectionPool (psycopg_pool) + register_vector
    schema.sql               # se extiende con sesiones/mensajes
  ingest/
    repository.py            # se extiende con obtener_snapshot_vigente
  agent/
    __init__.py
    chat_client.py            # ChatClient: wrapper OpenAI para tool-calling (gpt-4o-mini)
    tools.py                  # esquemas OpenAI + funciones de despacho de las 7 tools
    sessions.py                # acceso a datos de sesiones/mensajes
    orchestrator.py           # loop de tool-calling + streaming trozeado + fuentes
    api.py                     # FastAPI: POST /chat, GET /sesiones/{id}/mensajes
```

`ChatClient` es una clase separada de `ingest.openai_client.OpenAIClient`:
esta última queda enfocada en las necesidades del pipeline de datos y el
motor de recuperación (embeddings, generación de FAQs, rerank); `ChatClient`
tiene una responsabilidad distinta (conversación multi-turno con tools) y una
forma de uso distinta (mensajes + historial, no textos sueltos).

## Modelo de datos

### `sesiones` / `mensajes` (extienden `backend/db/schema.sql`)

```sql
CREATE TABLE sesiones (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mensajes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sesiones(id),
    rol TEXT NOT NULL,              -- 'user' | 'assistant' | 'tool'
    contenido TEXT,                 -- null si el mensaje del asistente solo trae tool_calls
    tool_calls JSONB,                -- presente si el asistente decidió llamar tools
    tool_call_id TEXT,               -- presente en mensajes rol='tool'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`sesiones.id` es el UUID que genera el frontend; no hay autenticación. El
historial completo (incluidos los mensajes internos de tool-calling) queda
persistido para auditoría, pero `GET /sesiones/{id}/mensajes` solo devuelve
los mensajes visibles (`rol` en `user`/`assistant` con `contenido` no nulo).

### `obtener_snapshot_vigente` (nueva función en `backend/ingest/repository.py`)

```python
def obtener_snapshot_vigente(conn, tramite_id: str) -> dict | None:
    # SELECT snapshot FROM tramite_versiones
    # WHERE tramite_id = %s AND es_vigente = true
```

Devuelve el `snapshot` JSONB completo (el objeto enriquecido definido en el
núcleo de datos: `requisitos`, `costo`, `modalidad`, `duracion`, `pasos`,
`problemas_frecuentes`, `enlaces_oficiales`, `objetivo`, `descripcion`, etc.)
o `None` si el trámite no existe o no tiene versión vigente.

## Las 7 herramientas (`backend/agent/tools.py`)

| Tool | Parámetros | Fuente de datos |
|---|---|---|
| `buscar_tramite` | `query: str` | `hybrid_search.buscar_chunks`, deduplicado por `tramite_id` (se conserva el de mejor ranking), devuelve `{tramite_id, nombre_oficial, categoria, organismo}` por candidato |
| `obtener_requisitos` | `tramite_id: str` | `snapshot["requisitos"]` |
| `obtener_costos_modalidad` | `tramite_id: str` | `{costo, modalidad, duracion}` del snapshot |
| `obtener_pasos` | `tramite_id: str` | `snapshot["pasos"]` |
| `obtener_normativa` | `tramite_id: str` | `{objetivo, descripcion}` del snapshot (no hay normativa legal separada en los datos actuales) |
| `obtener_formularios_enlaces` | `tramite_id: str` | `snapshot["enlaces_oficiales"]` |
| `obtener_problemas_frecuentes` | `tramite_id: str` | `snapshot["problemas_frecuentes"]` |

Cada tool se expone también como un esquema de function-calling de OpenAI
(`name`, `description`, `parameters` en JSON Schema). Las 6 últimas
comparten la misma forma (reciben un `tramite_id` ya conocido); solo
`buscar_tramite` hace búsqueda semántica cuando el trámite todavía no fue
identificado.

## Orquestación (`backend/agent/orchestrator.py`)

**`procesar_turno(conn, chat_client, embed_fn, rerank_fn, session_id, mensaje_usuario) -> Iterator[dict]`:**

1. Recupera el historial persistido de `session_id` (`sessions.obtener_historial`)
   y arma `messages = [system_prompt] + historial + [mensaje_usuario]`.
2. Persiste el mensaje del usuario.
3. **Loop de tool-calling** (máximo 5 iteraciones): llama a
   `chat_client.completar(messages, tools=TOOL_SCHEMAS)` (sin streaming,
   `gpt-4o-mini`). Si la respuesta trae `tool_calls`: ejecuta cada uno vía
   un dict de despacho, persiste el mensaje del asistente (con sus
   `tool_calls`) y un mensaje `rol=tool` por resultado, acumula qué
   trámites/enlaces se citaron, y vuelve a loopear con los resultados
   añadidos a `messages`.
4. Cuando la respuesta ya no trae `tool_calls`, ese texto es la respuesta
   final completa — ya generada por esa misma llamada no-streaming (no se
   pide una segunda vez en modo streaming, para no duplicar el costo de
   tokens). Se persiste como mensaje del asistente.
5. El texto final se trocea por palabra y se emite como una secuencia de
   eventos `{"tipo": "texto", "delta": "..."}`, con una pequeña demora entre
   trozos, dándole al frontend una experiencia de streaming progresivo sin
   necesidad de acumular deltas de `tool_calls` en modo streaming real.
6. Al final: un evento `{"tipo": "fin", "fuentes": [{"tramite_id",
   "nombre_oficial", "fuente_url"}, ...]}` con los trámites/enlaces citados
   en el turno, deduplicados.

**System prompt (persona "Macacha"):** asistente de trámites de la
administración pública de Salta, hoy con foco en Registro Civil; responde
solo con información traída por las tools, nunca inventa requisitos, costos
ni pasos; si `buscar_tramite` devuelve varios candidatos ambiguos, pregunta
para desambiguar antes de invocar las demás tools; siempre menciona el
trámite por su nombre oficial y, cuando corresponda, el enlace oficial.

## FastAPI (`backend/agent/api.py`)

- `POST /chat` — body `{"session_id": str, "mensaje": str}`. Crea la sesión
  si no existe. Devuelve `StreamingResponse` (`media_type="text/event-stream"`),
  emitiendo los eventos de `procesar_turno` como líneas SSE
  (`data: <json>\n\n`).
- `GET /sesiones/{session_id}/mensajes` — devuelve la lista de mensajes
  visibles de esa sesión, ordenados por `created_at`.

## Conexión a Postgres (`backend/db/pool.py`)

```python
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

def _configurar_conexion(conn):
    register_vector(conn)

pool = ConnectionPool(os.environ["DATABASE_URL"], configure=_configurar_conexion)
```

Cada request de FastAPI toma una conexión prestada del pool (`with
pool.connection() as conn: ...`) y la devuelve al terminar. Esto resuelve de
raíz la precondición de `register_vector` que `hybrid_search.buscar_chunks`
asumía implícitamente.

## Testing

- `sessions.py` y `obtener_snapshot_vigente`: tests de integración contra
  Postgres real (fixtures `db_conn`/`clean_db` ya existentes), reutilizando
  `ingest.repository` para armar datos de prueba.
- `tools.py`: tests con Postgres real (para `buscar_tramite`, que usa
  `hybrid_search.buscar_chunks` con `embed_fn`/`rerank_fn` falsos) y tests
  puros para las 6 tools que solo leen del snapshot (con `obtener_snapshot_vigente`
  real contra datos insertados de prueba).
- `orchestrator.py`: tests con un `ChatClient` falso inyectado que simula
  las respuestas de OpenAI (con y sin `tool_calls`, en distintas secuencias),
  verificando que persiste los mensajes correctos, ejecuta las tools
  correctas, y arma bien la secuencia de eventos (`texto`/`fin` con
  `fuentes`) — sin red real a OpenAI.
- `api.py`: tests con `TestClient` de FastAPI, inyectando el pool y el
  `ChatClient` falsos (vía dependency overrides de FastAPI).
- Ningún test de este subsistema hace una llamada real a la API de OpenAI.

## Fuera de alcance de este documento

- Frontend (subsistema 4).
- Autenticación de usuarios.
- Despliegue a producción / CI-CD.
- Rate limiting, cuotas de uso, o límites de costo por sesión.
- Truncado o resumen de historiales de conversación muy largos (se persiste
  todo el historial y se pasa completo al modelo en cada turno; el manejo
  de ventanas de contexto muy largas queda para una iteración futura si
  hace falta).

## Criterios de aceptación

- Un `POST /chat` con `{"session_id": "<uuid nuevo>", "mensaje": "¿qué
  necesito para sacar un acta de nacimiento?"}` contra los 32 trámites
  reales devuelve una secuencia de eventos SSE que termina en un evento
  `"fin"` con al menos un trámite de categoría "Actas" o "Nacimiento" en
  `fuentes`, y el texto acumulado de los eventos `"texto"` menciona
  requisitos reales del trámite (verificación manual, no automatizada).
- Un segundo `POST /chat` con el mismo `session_id` y una pregunta de
  seguimiento (ej. "¿y cuánto sale?") recibe una respuesta coherente con el
  trámite identificado en el turno anterior, sin que el usuario tenga que
  volver a especificarlo — prueba de que el historial persistido se está
  usando.
- `GET /sesiones/{session_id}/mensajes` después de esos dos turnos devuelve
  los 2 mensajes de usuario y los 2 mensajes de asistente visibles, en
  orden, sin los mensajes internos de tool-calling.
- Todos los tests automatizados pasan de forma determinística, sin red real
  a OpenAI.
