# Macacha — Panel de admin: esqueleto (login) + sección de Chats

## Contexto

Hoy no existe ningún panel de administración: los datos de sesiones y
mensajes ya se persisten (`sesiones`, `mensajes`), pero no hay forma de
verlos salvo con SQL directo. Este documento cubre la primera pieza de un
panel de admin más amplio (ver "Fuera de alcance" para las secciones que
quedan para specs posteriores): el esqueleto de autenticación y la sección
de **Chats**, que permite listar sesiones y ver el detalle de cada una,
incluyendo el detalle técnico (tool calls) para debugging.

## Modelo de datos

Tabla nueva en `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

No hace falta tabla de sesiones de admin: la autenticación es stateless vía
JWT. No se modifica el schema de `sesiones` ni `mensajes` — todo lo que
necesita la sección de Chats ya está persistido ahí.

**Alta del primer admin**: no hay UI de registro (es un panel interno, no
un producto multi-tenant). Se agrega un script CLI
`python -m agent.admin.create_admin <email>` que pide la contraseña por
input oculto (`getpass`), la hashea con bcrypt y la inserta en `admins`.

## Dependencias nuevas

En `backend/requirements.txt`:
- `passlib[bcrypt]` — hashing de contraseñas
- `pyjwt` — firma y verificación de JWT

Variable de entorno nueva en `.env` / `.env.example`: `ADMIN_JWT_SECRET`.

## Backend — autenticación

Módulo nuevo `backend/agent/admin/`:
- `auth.py`: lógica de login, hashing, JWT, y la dependencia `requiere_admin`
- `chats.py`: endpoints de sesiones/mensajes para el admin
- `create_admin.py`: script CLI de alta de admin

### `POST /admin/login`

Body: `{ "email": str, "password": str }`.

- Busca el admin por email, verifica el hash con bcrypt.
- Si es válido: firma un JWT con payload `{ "sub": admin_id, "exp":
  now + 24h }` usando `ADMIN_JWT_SECRET`, y lo setea en una cookie
  `admin_session` (`httpOnly=True`, `secure=True`, `samesite="lax"`,
  `max_age=86400`).
- Si no es válido (email no existe o password no matchea): `401` con
  `{"detail": "Credenciales inválidas"}` en ambos casos — no se distingue
  cuál de las dos falló.

### `POST /admin/logout`

Borra la cookie `admin_session` (`Set-Cookie` con `max_age=0`). No requiere
`requiere_admin` — funciona incluso si la cookie ya expiró.

### `GET /admin/me`

Protegido por `requiere_admin`. Devuelve `{"email": str}` del admin
autenticado. `401` si no hay cookie o el JWT es inválido/expiró. Lo usa el
frontend para decidir si mostrar el login o el dashboard.

### Dependencia `requiere_admin`

`Depends` de FastAPI: lee la cookie `admin_session`, decodifica el JWT con
`ADMIN_JWT_SECRET`, valida expiración y devuelve el `admin_id` (`sub`). Si
falta la cookie, el JWT es inválido, o expiró: `HTTPException(401)`. Se
aplica a todos los endpoints bajo `/admin/*` excepto `/admin/login` y
`/admin/logout`.

### CORS

En `agent/api.py`, el middleware `CORSMiddleware` existente agrega
`allow_credentials=True` (ya tiene `allow_origins` con `FRONTEND_ORIGIN`
explícito, requisito para poder combinarlo con credentials).

## Backend — endpoints de chats (admin)

Ambos protegidos por `requiere_admin`.

### `GET /admin/sesiones?page=1&page_size=20`

Devuelve las sesiones ordenadas por `created_at` descendente:

```json
{
  "sesiones": [
    {
      "id": "uuid",
      "creado_en": "2026-07-24T10:00:00Z",
      "cantidad_mensajes": 12,
      "ultimo_mensaje": "texto truncado a 140 caracteres...",
      "tramites_citados": ["RC-0001", "RC-0002"]
    }
  ],
  "total": 143,
  "page": 1,
  "page_size": 20
}
```

- `cantidad_mensajes`: cuenta filas de `mensajes` con `rol IN ('user',
  'assistant')` para esa sesión (mismo criterio de "visible" que ya usa
  `obtener_mensajes_visibles`).
- `ultimo_mensaje`: `contenido` del último mensaje visible (por `orden`
  descendente), truncado a 140 caracteres con `…` si excede. `null` si la
  sesión no tiene ningún mensaje visible todavía.
- `tramites_citados`: se deriva escaneando el campo `tool_calls` (JSONB) de
  los mensajes `assistant` de la sesión en orden de `orden` ascendente,
  extrayendo `tramite_id` de los argumentos de cada tool call que lo tenga,
  deduplicado preservando el orden de primera aparición. No es una columna
  nueva — es una lectura calculada, igual que ya hace `procesar_turno` en
  memoria durante el turno (`agent/orchestrator.py`), pero acá sobre lo ya
  persistido.
- Paginación: `page` arranca en 1; si se pide una página fuera de rango,
  devuelve `sesiones: []` (no error).

### `GET /admin/sesiones/{session_id}`

Devuelve **todos** los mensajes de la sesión (a diferencia de
`obtener_mensajes_visibles`, que filtra a `user`/`assistant`), para
soportar la vista de detalle técnico expandible:

```json
[
  {"rol": "user", "contenido": "...", "creado_en": "..."},
  {"rol": "assistant", "contenido": "...", "tool_calls": [...], "creado_en": "..."},
  {"rol": "tool", "contenido": "...", "tool_call_id": "...", "creado_en": "..."}
]
```

`404` si `session_id` no existe en `sesiones`.

Ambos endpoints son de solo lectura — no hay riesgo de mutar datos de chat
en producción.

## Frontend

Todo dentro del proyecto Next.js existente, bajo `/admin`:

```
app/admin/
  login/page.tsx          → formulario email + password
  layout.tsx               → layout del dashboard (nav lateral, por ahora solo "Chats")
  page.tsx                 → redirect a /admin/chats
  chats/page.tsx            → lista paginada de sesiones
  chats/[id]/page.tsx      → detalle de una sesión
middleware.ts               → protege /admin/** (excepto /admin/login)
lib/admin-api.ts            → cliente fetch con credentials:"include" para /admin/*
```

### `middleware.ts`

Intercepta requests a `/admin/*` salvo `/admin/login`. Llama a
`GET /admin/me` en el backend reenviando la cookie; si devuelve `401`,
redirige a `/admin/login`. Se delega la validación del JWT al backend (el
secreto vive solo ahí) en vez de decodificarlo en el middleware.

### `login/page.tsx`

Formulario simple (email, password). Al enviar, `POST /admin/login` con
`credentials:"include"`. Si responde `200`, redirige a `/admin/chats`. Si
`401`, muestra "Credenciales inválidas" debajo del formulario sin recargar
la página.

### `chats/page.tsx`

Tabla con columnas: fecha (formateada localmente), cantidad de mensajes,
preview del último mensaje, badges con los `tramites_citados`. Paginación
Anterior/Siguiente usando `page`/`page_size` de la respuesta. Cada fila
linkea a `chats/[id]`.

Estados:
- Cargando: skeleton simple de filas.
- Vacío (`total === 0`): "Todavía no hay chats registrados".
- Error de red/backend: "No se pudo cargar la lista de chats" + botón
  "Reintentar".

### `chats/[id]/page.tsx`

Reutiliza el estilo visual de `components/ChatMessage.tsx` (ya usado en el
chat público) para renderizar los mensajes `user`/`assistant` en burbujas.
Debajo de cada mensaje `assistant` que tiene `tool_calls`, un botón "Ver
detalle técnico" que expande un bloque con, por cada tool call: nombre de
la tool, argumentos (JSON formateado) y el `contenido` del mensaje `tool`
correspondiente (matcheado por `tool_call_id`).

Estados:
- `404` → "Sesión no encontrada" con link de vuelta a `/admin/chats`.
- Error de red/backend → mismo patrón de "Reintentar" que la lista.

### `lib/admin-api.ts`

Cliente fetch dedicado (separado de `lib/api.ts`, que es del chat público)
con `credentials:"include"` en todas las llamadas: `login(email,
password)`, `logout()`, `obtenerMe()`, `obtenerSesiones(page, pageSize)`,
`obtenerSesion(id)`.

### Estilo

Reutiliza Tailwind y los componentes existentes (`ChatMessage.tsx` como
base visual) en vez de traer una librería de UI nueva, para mantener
consistencia con el chat público.

## Manejo de errores

- Login fallido: mensaje genérico, sin distinguir la causa (ver arriba).
- JWT expirado/inválido en cualquier request a `/admin/*`: `401` →
  middleware redirige a `/admin/login`.
- Sesión de chat inexistente: `404` → estado "Sesión no encontrada".
- Backend caído / error de red: estado de error con botón "Reintentar" en
  vez de una excepción no manejada.
- Lista de sesiones vacía: estado vacío explícito, no un error.

## Testing

- **Backend** (`pytest`, infraestructura ya existente en `backend/tests/`):
  - `POST /admin/login`: credenciales válidas → `200` + cookie seteada;
    inválidas (email inexistente, password incorrecto) → `401` en ambos
    casos.
  - `GET /admin/me`, `GET /admin/sesiones`, `GET /admin/sesiones/{id}`:
    sin cookie → `401`; con cookie válida → `200`.
  - `GET /admin/sesiones`: con datos de prueba insertados directamente
    (varias sesiones, mensajes con y sin `tool_calls`), verificar
    `cantidad_mensajes`, `ultimo_mensaje` truncado correctamente, y
    `tramites_citados` deduplicado y en el orden esperado.
  - `GET /admin/sesiones/{id}`: incluye mensajes `tool` y `tool_calls`
    (a diferencia de `obtener_mensajes_visibles`); `404` si no existe.
- **Frontend**: no hay infraestructura E2E en el repo (solo Vitest para
  componentes unitarios). El login y las páginas de admin se verifican
  manualmente en el browser como parte de la implementación. Si a futuro
  se justifica, se puede evaluar Playwright como proyecto aparte.

## Fuera de alcance

- Las demás secciones del panel de admin (carga de fuentes, edición de
  trámites, visor/editor del prompt del agente) — quedan para specs
  posteriores independientes.
- Filtros de búsqueda en la lista de sesiones (por fecha, por trámite
  citado) — se agregan más adelante si el volumen de chats lo justifica.
- Múltiples roles o permisos distintos entre admins — todo admin tiene el
  mismo acceso total.
- Recuperación de contraseña / cambio de contraseña desde la UI — para
  resetear una contraseña hoy hace falta volver a correr
  `create_admin.py` (que hace `ON CONFLICT` update) o hacerlo a mano en la
  DB.
- Invalidar sesiones activas de un admin (ej. forzar logout remoto) — al
  ser JWT stateless, una sesión firmada es válida hasta que expira (24h)
  aunque se cambie la contraseña después.

## Criterios de aceptación

- Con el backend y frontend corriendo, entrar a `/admin/chats` sin sesión
  redirige a `/admin/login`.
- Loguearse con las credenciales creadas vía `create_admin.py` redirige a
  `/admin/chats` y muestra la lista de sesiones existentes, más reciente
  primero.
- Cada fila muestra fecha, cantidad de mensajes, preview del último
  mensaje y los trámites citados en esa sesión.
- Entrar al detalle de una sesión muestra la conversación limpia; expandir
  "Ver detalle técnico" en un turno con tool calls muestra la tool
  llamada, sus argumentos y el resultado.
- Cerrar sesión (`/admin/logout`) y volver a entrar a `/admin/chats`
  redirige de nuevo a `/admin/login`.
- Loguearse con credenciales inválidas muestra "Credenciales inválidas"
  sin redirigir.
