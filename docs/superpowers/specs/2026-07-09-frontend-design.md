# Macacha — Frontend (chat en Next.js)

## Contexto general del sistema

Este es el **cuarto y último** de los subsistemas de Macacha, el asistente
virtual de trámites de la administración pública de la Provincia de Salta:

1. **Núcleo de datos** (implementado): esquema Postgres+pgvector, pipeline de
   ingesta, 32 trámites reales del Registro Civil cargados.
2. **Motor de recuperación** (implementado): búsqueda híbrida (vectorial +
   full-text) fusionada por RRF y re-ranking vía LLM.
3. **Agente conversacional** (implementado): `backend/agent/`, FastAPI con
   `POST /chat` (SSE) y `GET /sesiones/{id}/mensajes`, tool-calling sobre 7
   herramientas, sesiones/historial persistentes en Postgres.
4. **Frontend** (este documento): interfaz de chat en Next.js que consume el
   backend del punto 3.

## Contrato real del backend (ya implementado)

### `POST /chat`

Body: `{"session_id": "<uuid>", "mensaje": "<texto del usuario>"}`.
`session_id` se valida como UUID (422 si no lo es). Respuesta:
`StreamingResponse` (`text/event-stream`), cada evento como una línea
`data: <json>\n\n`. Tipos de evento posibles:

- `{"tipo": "texto", "delta": "<palabra> "}` — uno o más, en secuencia, con
  el texto de la respuesta troceado por palabra (no es streaming real del
  modelo — el texto ya está completo del lado del backend, y se emite
  progresivamente para dar sensación de streaming al usuario).
- `{"tipo": "fin", "fuentes": [{"tramite_id", "nombre_oficial",
  "fuente_url"}, ...]}` — siempre el último evento en el caso exitoso.
  `fuentes` solo incluye trámites sobre los que el agente efectivamente
  consultó datos (requisitos, costos, pasos, etc.), no todos los candidatos
  de una búsqueda ambigua.
- `{"tipo": "error", "mensaje": "<texto amigable>"}` — si ocurre una
  excepción durante el procesamiento del turno; es el único evento en ese
  caso (no hay `"fin"` después).

### `GET /sesiones/{session_id}/mensajes`

`session_id` se valida como UUID (422 si no lo es). Devuelve un array JSON
de mensajes visibles de esa sesión, en orden cronológico:
`[{"rol": "user" | "assistant", "contenido": "<texto>", "creado_en":
"<iso8601>"}, ...]`. Si la sesión no existe todavía, devuelve `[]` (no
error). Este endpoint no incluye la información de `fuentes` de turnos
anteriores (esa solo viaja en el evento `"fin"` del `POST /chat` original,
en el momento en que ocurre) — el frontend no necesita reconstruir fuentes
de turnos pasados al recargar la página, solo el texto de la conversación.

## Cambio necesario en el backend: CORS

`backend/agent/api.py` no tiene CORS configurado. Se agrega
`fastapi.middleware.cors.CORSMiddleware`, permitiendo como origen el del
frontend en desarrollo (`http://localhost:3000`), configurable vía una
variable de entorno (`FRONTEND_ORIGIN`, con ese valor como default). Esto
permite que el frontend haga `fetch` directo a la URL del backend sin pasar
por un proxy de Next.js.

## Alcance

Una aplicación Next.js (App Router, TypeScript, Tailwind CSS) con una única
pantalla de chat, sin autenticación:

1. Sesión anónima: `session_id` (uuid) generado y persistido en
   `localStorage` en el primer uso.
2. Al cargar, hidrata el historial visible de la sesión (si existe) vía
   `GET /sesiones/{id}/mensajes`.
3. Envío de mensajes con streaming visual de la respuesta del asistente
   (parseando los eventos `"texto"`/`"fin"`/`"error"` del `POST /chat`).
4. Muestra las fuentes citadas (nombre oficial + enlace) debajo de cada
   respuesta del asistente, cuando las hay.
5. Manejo de errores: el evento `"error"` se muestra de forma amigable, con
   un botón para reintentar el mismo mensaje.
6. Diseño responsive, mobile-first.

Sin librerías de estado adicionales (React Query, SWR, Zustand, Redux): el
estado de la conversación es una lista de mensajes en memoria del componente
de la pantalla de chat, manejado con hooks propios.

## Estructura de archivos

```
frontend/
  app/
    layout.tsx           # layout raíz, fuente, metadata
    page.tsx              # pantalla única de chat
    globals.css            # Tailwind
  components/
    ChatMessage.tsx         # burbuja de mensaje (usuario/asistente), fuentes citadas, estado de error+reintentar
    ChatInput.tsx             # textarea + botón enviar (Enter para enviar, Shift+Enter salto de línea)
  hooks/
    useSession.ts             # session_id: string (uuid), generado/leído de localStorage
    useChatStream.ts           # enviarMensaje(texto) -> maneja el fetch+parseo SSE, expone el estado de streaming
  lib/
    api.ts                     # BASE_URL desde NEXT_PUBLIC_API_URL; obtenerHistorial(sessionId)
  package.json
  tsconfig.json
  tailwind.config.ts
  next.config.ts
  .env.local.example          # NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Componentes y hooks

### `hooks/useSession.ts`

`useSession(): { sessionId: string }`. En el primer render en el cliente,
lee `localStorage.getItem("macacha_session_id")`; si no existe, genera un
`crypto.randomUUID()` y lo guarda. Devuelve siempre el mismo `sessionId`
mientras dure el `localStorage` del navegador.

### `lib/api.ts`

- `obtenerHistorial(sessionId: string): Promise<MensajeVisible[]>` — `GET
  {BASE_URL}/sesiones/{sessionId}/mensajes`, tipado según el contrato real
  de arriba.
- `BASE_URL` leído de `process.env.NEXT_PUBLIC_API_URL`.

### `hooks/useChatStream.ts`

`useChatStream(sessionId: string)` devuelve:
- `mensajes: Mensaje[]` — el estado completo de la conversación visible en
  pantalla (incluye los hidratados del historial + los nuevos de esta
  sesión de navegador).
- `enviando: boolean` — true mientras se espera/streamea una respuesta.
- `enviarMensaje(texto: string): void` — agrega la burbuja del usuario de
  inmediato, hace `fetch(POST {BASE_URL}/chat, {session_id, mensaje})`, lee
  el `body` como `ReadableStream`, decodifica y parsea cada línea `data:
  ...`, y va actualizando la burbuja de respuesta del asistente en curso
  según el `tipo` de cada evento (`texto` concatena `delta`; `fin` cierra la
  burbuja y adjunta `fuentes`; `error` marca la burbuja como error con el
  mensaje recibido).

Al montar, `useChatStream` llama a `obtenerHistorial(sessionId)` para
poblar `mensajes` con la conversación previa (si la hay).

### `components/ChatMessage.tsx`

Renderiza una burbuja (usuario a la derecha, asistente a la izquierda).
Para mensajes del asistente con `fuentes`, muestra una lista compacta
debajo (nombre oficial del trámite, como link si `fuente_url` no es null).
Para mensajes en estado de error, muestra el texto de error y un botón
"Reintentar" que vuelve a llamar a `enviarMensaje` con el último texto de
usuario enviado.

### `components/ChatInput.tsx`

Textarea controlado + botón enviar. `Enter` envía (si no está vacío y no se
está esperando una respuesta), `Shift+Enter` inserta salto de línea.
Deshabilitado mientras `enviando` es `true`.

### `app/page.tsx`

Compone `useSession` + `useChatStream`, renderiza el header ("Macacha —
Asistente de trámites de la Provincia de Salta"), la lista de
`ChatMessage`, y el `ChatInput` al pie.

## Testing

Es una interfaz de usuario — la verificación principal es manual: levantar
Postgres + backend (`uvicorn`) + frontend (`npm run dev`) y probar el flujo
real en el navegador (enviar un mensaje, ver el streaming, ver las fuentes,
recargar la página y ver el historial, forzar un error y ver el botón de
reintentar).

Se agrega un test unitario liviano con Vitest para el parseo de eventos SSE
de `useChatStream` (dado un cuerpo de `ReadableStream` simulado con líneas
`data: {...}`, confirmar que produce la secuencia correcta de
actualizaciones de estado) — es la única lógica no trivial de este
subsistema, el resto es composición de UI.

## Fuera de alcance de este documento

- Autenticación de usuarios.
- Despliegue a producción / CI-CD.
- Múltiples conversaciones por sesión (solo hay una conversación lineal por
  `session_id`).
- Internacionalización (todo en español, sin selector de idioma).
- Docker Compose para el frontend (se corre con `npm run dev`, separado del
  backend, según lo acordado).

## Criterios de aceptación

- Con el backend y el frontend corriendo, abrir la página en el navegador
  genera un `session_id` nuevo, muestra el chat vacío, y permite enviar un
  mensaje como "¿qué necesito para sacar un acta de nacimiento?" — la
  respuesta aparece progresivamente (streaming visual) y al final se ven
  las fuentes citadas con un enlace al sitio oficial.
- Recargar la página mantiene la misma sesión (mismo `session_id`) y
  muestra el historial de la conversación anterior.
- Si el backend no está corriendo o devuelve un evento `"error"`, la UI lo
  muestra de forma clara con un botón de reintentar, sin romper el resto de
  la interfaz.
- La interfaz es usable en una pantalla de celular (viewport angosto).
