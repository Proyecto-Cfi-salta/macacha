# Roles de admin por organismo

**Fecha:** 2026-08-07
**Estado:** Aprobado, pendiente de implementación

## Contexto y objetivo

Hoy cualquier admin autenticado (`agent/admin/*`, tabla `admins`) tiene acceso total
al panel: ve todos los chats y todos los trámites de todos los organismos, y puede
crear/editar cualquier trámite. Los admins se crean únicamente por CLI
(`agent/admin/create_admin.py`), sin rol ni organismo asociado.

El objetivo es introducir dos roles — **super_admin** (acceso total, gestiona
usuarios y organismos) y **admin_organismo** (acceso acotado a un único
organismo) — de forma que un admin de organismo solo vea y edite los chats y
trámites de su propio organismo.

### Decisiones de alcance (confirmadas con el usuario)

- Un chat es visible para el admin de organismo X si en algún momento de la
  conversación se citó al menos un trámite de X. Un mismo chat puede quedar
  visible para más de un organismo si mezcló temas. Los chats que no citaron
  ningún trámite solo los ve `super_admin`.
- Solo dos roles: `super_admin` y `admin_organismo`. Sin rol de solo-lectura.
- Un admin de organismo puede crear y editar trámites, acotado a su organismo.
- Un admin de organismo pertenece a **exactamente un** organismo (no N:M).
- La gestión de usuarios (alta/edición/desactivación, asignación de rol y
  organismo) se hace desde una pantalla nueva del panel admin, solo accesible
  a `super_admin` — no por CLI.
- El admin existente en la base (`admin@macacha.gob.ar`) pasa a `super_admin`
  como parte de la migración.
- El filtrado de chats por organismo se resuelve en Python sobre el código que
  ya extrae trámites citados de `tool_calls` (sin tabla de denormalización ni
  cambios al orchestrator). Con el volumen actual de chats (decenas), el costo
  de traer y filtrar en memoria es despreciable. Si el volumen creciera mucho,
  se puede migrar a una tabla de índice `sesion_tramites_citados` más adelante
  — no forma parte de este trabajo.
- El panel de super-admin también permite dar de alta organismos nuevos (hoy
  solo se crean implícitamente vía la ingesta de trámites).

## 1. Modelo de datos

Cambios sobre `backend/db/schema.sql`, agregados al final del archivo con el
mismo estilo idempotente que ya usa (`ADD COLUMN IF NOT EXISTS`):

```sql
CREATE TYPE admin_rol AS ENUM ('super_admin', 'admin_organismo');

ALTER TABLE admins ADD COLUMN IF NOT EXISTS rol admin_rol NOT NULL DEFAULT 'admin_organismo';
ALTER TABLE admins ADD COLUMN IF NOT EXISTS organismo_id INTEGER REFERENCES organismos(id);
ALTER TABLE admins ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT true;
```

- `organismo_id` es `NULL` para `super_admin` y obligatorio para
  `admin_organismo`. Esta regla se valida en código (en el endpoint de alta/
  edición de usuarios), no con un `CHECK` condicional en la base.
- `activo=false` permite desactivar un admin sin borrar su fila (preserva el
  historial de quién editó qué, si en el futuro se audita).
- `organismos` no cambia de estructura. Sigue creándose vía
  `upsert_organismo` durante la ingesta y, con este trabajo, también desde el
  endpoint nuevo `POST /admin/organismos`.

`CREATE TYPE ... IF NOT EXISTS` no existe en Postgres — como `schema.sql` se
corre completo cada vez (`psql -f schema.sql` contra una base que puede ya
tener el tipo), el `CREATE TYPE` va envuelto:

```sql
DO $$ BEGIN
    CREATE TYPE admin_rol AS ENUM ('super_admin', 'admin_organismo');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
```

## 2. Autenticación y autorización (backend)

### `agent/admin/repository.py`

`obtener_admin_por_email` y `obtener_admin_por_id` se extienden para
devolver también `rol`, `organismo_id` y `activo` (hoy solo devuelven
`id`/`email`/`password_hash` o `id`/`email`). `crear_admin` pasa a aceptar
`rol` y `organismo_id` como parámetros (con default `rol="admin_organismo"`,
`organismo_id=None`, para no romper la firma en los pocos lugares que la
llaman sin esos datos).

### JWT

El payload pasa de `{"sub": admin_id, "exp": ...}` a incluir también rol y
organismo:

```python
payload = {
    "sub": admin_id,
    "rol": admin["rol"],
    "organismo_id": admin["organismo_id"],
    "exp": datetime.now(timezone.utc) + timedelta(hours=24),
}
```

`agent/admin/security.py`:
- `crear_token(admin: dict) -> str` — pasa a recibir el dict completo del
  admin (antes solo `admin_id`), para poder incluir `rol`/`organismo_id`.
- `decodificar_token(token: str) -> dict | None` — pasa a devolver el payload
  completo (`{"sub", "rol", "organismo_id"}`) en vez de solo el `sub`.
  Devuelve `None` si el token es inválido/expirado, igual que hoy.

Los tokens emitidos antes de este cambio no tienen `rol`/`organismo_id` y
quedan inválidos de forma natural en cuanto el código empiece a exigir esas
claves — no hace falta invalidación explícita, fuerza un re-login.

### `agent/admin/dependencies.py`

```python
@dataclass
class AdminActual:
    id: str
    rol: str
    organismo_id: int | None

def requiere_admin(request: Request) -> AdminActual: ...

def requiere_super_admin(admin: AdminActual = Depends(requiere_admin)) -> AdminActual:
    if admin.rol != "super_admin":
        raise HTTPException(status_code=403, detail="Requiere permisos de super admin")
    return admin
```

Todos los endpoints que hoy reciben `admin_id: str = Depends(requiere_admin)`
pasan a recibir `admin: AdminActual = Depends(requiere_admin)`.

**Limitación conocida y aceptada — revocación no es inmediata en la API.**
`requiere_admin` lee `rol`/`organismo_id`/`activo` únicamente del JWT, sin
consultar la base en cada request (por diseño, para no pagar una query en
cada llamada al panel admin). Solo `GET /admin/me` — que el middleware del
frontend llama en cada navegación a `/admin/*` — vuelve a consultar la DB y
aplica el chequeo de `activo`. Consecuencia: desactivar un admin, o cambiarle
el rol/organismo, no tiene efecto sobre una cookie de sesión ya emitida
hasta que esta expira (máximo 24hs) o hasta que el frontend la fuerza a
re-loguearse vía `/admin/me`. Un acceso directo a la API (sin pasar por la
UI) con una cookie retenida de una cuenta recién desactivada sigue
funcionando durante esa ventana. Aceptado conscientemente: el panel admin es
de bajo tráfico y pocos usuarios internos: el costo de una consulta a la DB
en cada request no se justifica frente a este riesgo. Si el perfil de uso
cambiara, la mitigación es hacer que `requiere_admin` resuelva `rol`/
`organismo_id`/`activo` desde la DB (como ya hace `/admin/me`), reduciendo el
JWT a una simple aserción de identidad — no forma parte de este trabajo.

### Regla de acceso cross-organismo

Para cualquier endpoint que accede a un recurso (trámite o sesión) por id:
- `super_admin`: sin restricción, comportamiento actual.
- `admin_organismo`: si el recurso no pertenece a su organismo, `404` (no
  `403` — no confirmamos que el recurso exista en otro organismo).

## 3. Endpoints

### Modificados

| Endpoint | Cambio |
|---|---|
| `POST /admin/login` | Si `admin.activo` es `false`, responde `401` igual que password incorrecta (mismo mensaje, no distingue el motivo). Si es válido, la respuesta incluye `rol` y `organismo` (nombre, `null` si `super_admin`). |
| `GET /admin/me` | Incluye también `rol` y `organismo`. |
| `GET /admin/sesiones` | `admin_organismo`: se filtra a sesiones donde al menos un trámite citado pertenece a su organismo. Filtrado y paginado en Python (ver Nota de implementación). `super_admin`: sin cambios. |
| `GET /admin/sesiones/{id}` | `admin_organismo`: `404` si ningún trámite citado en esa sesión es de su organismo. |
| `GET /admin/tramites` | `admin_organismo`: filtra por `organismo_id`. |
| `GET /admin/tramites/{id}` | `admin_organismo`: `404` si el trámite no es de su organismo. |
| `PUT /admin/tramites/{id}` | `admin_organismo`: `404` si el trámite no es de su organismo (chequeo previo, como hoy). Además, `400` si `payload.organismo` (nombre) no coincide exactamente con el nombre de su organismo asignado. |
| `POST /admin/tramites` | `admin_organismo`: `400` si `payload.organismo` no coincide con el nombre de su organismo asignado. |

`GET /admin/organismos` no cambia — sigue disponible para cualquier admin
autenticado (lo usan el selector de trámites y, ahora, el de usuarios).

**Por qué el chequeo de `400` en `PUT`/`POST /admin/tramites`:** hoy
`agent/admin/tramite_editor.py` hace `upsert_organismo(conn, payload["organismo"])`
al crear o editar un trámite — es decir, el campo `organismo` del payload es
lo que efectivamente decide a qué organismo pertenece el trámite (crea uno
nuevo si el nombre no existe). Sin este chequeo, un `admin_organismo` podría
reasignar un trámite propio a otro organismo, o crear uno nuevo, simplemente
mandando un nombre de organismo distinto en el payload.

### Nuevos — solo `super_admin` (`Depends(requiere_super_admin)`)

| Endpoint | Qué hace |
|---|---|
| `GET /admin/usuarios` | Lista admins: `id`, `email`, `rol`, `organismo` (nombre o `null`), `activo`. |
| `POST /admin/usuarios` | Crea un admin. Payload: `email`, `password`, `rol`, `organismo_id` (requerido si `rol == "admin_organismo"`, debe ser `null`/omitido si `super_admin`). `400` si la combinación rol/organismo_id es inconsistente, `409` si el email ya existe. |
| `PUT /admin/usuarios/{id}` | Edita `rol`, `organismo_id`, `activo`. `password` opcional (si viene, resetea el hash; si no, no se toca). Mismas validaciones de consistencia rol/organismo que el alta. |
| `POST /admin/organismos` | Crea un organismo. Payload: `nombre`. `409` si ya existe (mismo criterio que el `UNIQUE` de la columna). |

### Nota de implementación — filtrado de `/admin/sesiones` en Python

`agent/admin/chats_repository.listar_sesiones` hoy pagina en SQL
(`LIMIT`/`OFFSET`). Para `admin_organismo`, en vez de paginar en SQL:

1. Traer todas las sesiones ordenadas por `created_at DESC` (sin `LIMIT`/
   `OFFSET` en la query SQL) junto con sus trámites citados — reutilizando
   `_extraer_tramites_citados_batch`, que ya existe.
2. Resolver a qué organismo pertenece cada trámite citado (una query a
   `tramites` con `organismo_id = ANY(...)` sobre el conjunto de ids
   citados en todas las sesiones traídas, o reutilizar
   `admin_tramites_repository.listar_tramites` y armar un mapa `tramite_id
   -> organismo_id` en memoria).
3. Filtrar las sesiones cuyo conjunto de trámites citados no incluye ninguno
   del organismo del admin.
4. Paginar el resultado ya filtrado en Python (`sesiones[offset:offset+page_size]`)
   y devolver `total` como el conteo post-filtro (no el `SELECT COUNT(*)`
   global — el `total` que ve el frontend para paginar debe ser el filtrado).

Esto solo aplica cuando `admin.rol == "admin_organismo"`. Para `super_admin`
se mantiene el camino actual (paginado 100% en SQL), sin cambios de
comportamiento ni de costo.

## 4. Frontend

### Contexto de sesión admin

`app/admin/layout.tsx` (ya es `"use client"`) hace un fetch a `/admin/me` una
vez al montar y expone `{ email, rol, organismo }` vía un `AdminAuthContext`
+ hook `useAdminActual()`, para que cualquier página bajo `/admin` conozca el
rol sin repetir el fetch. Reemplaza cualquier necesidad de leer esos datos
del JWT en el cliente (el cliente nunca decodifica el JWT — solo confía en la
cookie httponly y en lo que devuelve `/admin/me`).

### `AdminLayout`

Agrega el link **"Usuarios"** al nav lateral, visible solo si
`useAdminActual().rol === "super_admin"`.

### `TramiteForm` (`components/TramiteForm.tsx`)

Nueva prop opcional `organismoFijo?: string`. Cuando está presente (se pasa
siempre que `useAdminActual().rol === "admin_organismo"`, con el nombre de su
organismo), el campo Organismo se renderiza como texto fijo no editable, en
lugar del select-con-opción-"crear nuevo" actual. Cuando no está presente
(caso `super_admin`), el comportamiento es el de hoy, sin cambios.

### Chats y Trámites — listas y detalle

Sin cambios de UI. El filtrado ya llega aplicado desde el backend según
quién está logueado; un admin de organismo simplemente ve menos filas.

### Página nueva `/admin/usuarios`

Mismo patrón visual que `/admin/tramites` (tabla + acción que abre un
formulario), solo alcanzable por `super_admin`:

- Tabla: email, rol, organismo, activo, acción "Editar".
- Formulario alta/edición: email, password (obligatorio en alta; en edición,
  "dejar en blanco para no cambiar"), rol (select), organismo (select,
  habilitado/visible solo si rol = admin de organismo), activo (checkbox,
  solo visible en edición — no aplica al alta, que siempre nace activo).
- Bloque **"Nuevo organismo"** (input + botón) arriba de la tabla de
  usuarios, en vez de una página/nav-item propios — es una sola acción
  simple.
- Si alguien no-`super_admin` fuerza la URL, la página igual intenta el
  fetch a `/admin/usuarios`, que devuelve `403`; la página muestra un
  mensaje de error en vez de datos (no depende únicamente de ocultar el link
  del nav para la seguridad real, que vive en el backend).

### `lib/admin-api.ts`

- `login` y el fetch de `/admin/me` devuelven/parsean también `rol` y
  `organismo`.
- Tipos y funciones nuevas: `AdminUsuario` (`id`, `email`, `rol`, `organismo`,
  `activo`), `obtenerUsuarios()`, `crearUsuario(datos)`,
  `editarUsuario(id, datos)`, `crearOrganismo(nombre)`.

## 5. Migración de datos

- Los `ALTER TABLE`/`CREATE TYPE` de la sección 1 van al final de
  `backend/db/schema.sql`. Se aplican igual que cualquier cambio de schema
  anterior: `psql "<connection-string>" -f backend/db/schema.sql`, tanto
  local como en producción, según ya documenta `docs/deploy-dokploy.md`.
  `init_test_db.sql` corre el mismo `schema.sql`, así que la base de tests
  recibe el cambio automáticamente.
- El `UPDATE admins SET rol = 'super_admin' WHERE email = 'admin@macacha.gob.ar'`
  **no** va en `schema.sql` (es un dato específico de este despliegue, no un
  cambio de estructura). Se agrega como paso manual nuevo en
  `docs/deploy-dokploy.md`, a ejecutar una sola vez después de aplicar el
  schema actualizado.
- `agent/admin/create_admin.py` se simplifica: ya no es la vía normal de alta
  (eso pasa a la UI), pero se mantiene para el *bootstrapping* del primer
  `super_admin` en una base nueva (sin el cual nadie podría entrar a
  `/admin/usuarios` para crear al resto). Se actualiza para crear siempre
  con `rol='super_admin'` y sin pedir organismo.

## 6. Testing

### Backend (pytest)

- `admin_repository.crear_admin` / `obtener_admin_por_email` /
  `obtener_admin_por_id`: extendidos para `rol`, `organismo_id`, `activo`.
  Tests directos del repository para las nuevas columnas.
- El helper de test `_crear_admin` (usado en `test_admin_api.py` y
  `test_admin_tramites_api.py`, ~20 usos) pasa a aceptar
  `rol="super_admin"` **por default**, para que los tests existentes —que
  asumen acceso total— sigan pasando sin modificarlos uno por uno. Se agrega
  un helper hermano `_crear_admin_organismo(conn, organismo_id, ...)` para
  los tests nuevos de filtrado.
- Casos nuevos a cubrir:
  - Login con `activo=false` → `401`.
  - Login exitoso incluye `rol`/`organismo` en la respuesta.
  - `GET /admin/sesiones` como `admin_organismo`: solo devuelve sesiones con
    algún trámite citado de su organismo; `total` refleja el conteo
    filtrado, no el global.
  - `GET /admin/sesiones/{id}` como `admin_organismo` sobre una sesión sin
    trámites de su organismo → `404`.
  - `GET /admin/tramites` como `admin_organismo`: solo trámites de su
    organismo.
  - `GET/PUT /admin/tramites/{id}` como `admin_organismo` sobre un trámite
    de otro organismo → `404`.
  - `PUT`/`POST /admin/tramites` como `admin_organismo` con
    `payload.organismo` distinto al propio → `400`.
  - `GET/POST/PUT /admin/usuarios` y `POST /admin/organismos` como
    `admin_organismo` → `403`; como `super_admin` → éxito, incluyendo
    validación de consistencia rol/organismo_id (`400`) y email duplicado
    (`409`).

### Frontend (vitest)

No se agregan tests nuevos. El patrón actual del repo (`lib/admin-chats.test.ts`,
los hooks) testea funciones puras de transformación de datos, no fetch
wrappers ni componentes de página — las funciones nuevas de
`lib/admin-api.ts` son CRUD simple sin lógica propia, consistente con lo que
ya queda sin testear ahí hoy (`login`, `obtenerSesiones`, etc.).

## Fuera de alcance

- Rol de solo-lectura por organismo.
- Admins asignados a más de un organismo.
- Tabla de denormalización `sesion_tramites_citados` para paginar el
  filtrado 100% en SQL — solo se justifica si el volumen de chats crece
  mucho; no forma parte de este trabajo.
- Auditoría de cambios (quién editó qué trámite y cuándo).
- Recuperación de contraseña self-service para admins.
