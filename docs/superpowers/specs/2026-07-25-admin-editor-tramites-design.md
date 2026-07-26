# Macacha — Panel de admin: editor de trámites (alta + edición)

## Contexto

Segunda sección del panel de admin, después del esqueleto de login + chats
(`2026-07-24-admin-panel-chats-design.md`). Hoy los trámites solo se crean o
actualizan vía el pipeline de ingesta por CLI (`python -m ingest.load
<archivo.json>`), que lee un JSON con formato "raw_tramite" y versiona cada
trámite en `tramite_versiones`. Este documento agrega una UI de admin para
crear y editar trámites directamente, sin pasar por un archivo JSON.

**Todas las herramientas de lookup directo del agente** (`obtener_requisitos`,
`obtener_costos_modalidad`, `obtener_pasos`, `obtener_normativa`,
`obtener_formularios_enlaces`, `obtener_problemas_frecuentes`, en
`agent/tools.py`) leen únicamente del `snapshot` JSONB de la versión
vigente — no de los chunks de búsqueda. Esto es lo que hace viable un editor
sin tocar el pipeline de ingesta completo: editar el snapshot alcanza para
que el agente responda con los datos nuevos en cualquier lookup directo.

**Nota sobre el estado de los datos**: al agregar la tabla `admins` en la
sección anterior hizo falta recrear el volumen de Postgres
(`docker compose down -v`), lo cual borró los 32 trámites reales que
estaban cargados en el entorno local. Esto es una consecuencia documentada
del cambio de schema (ver README), no algo que este documento deba
resolver — pero significa que, hasta que se vuelvan a ingerir desde el JSON
fuente, el editor va a operar sobre una base con pocos o ningún trámite
real.

## Campos editables

Todos los campos de contenido del snapshot, más organismo/categoría/nombre
oficial:

- `organismo` (selector de existentes + opción de crear uno nuevo)
- `categoria`, `nombre_oficial`
- `descripcion`, `objetivo`
- `requisitos`, `pasos`, `problemas_frecuentes` (listas de texto)
- `costo`, `modalidad`, `duracion`
- `telefono_contacto`, `email_contacto`
- `sinonimos`, `keywords` (listas de texto)
- `enlaces_oficiales` (lista de URLs)
- `preguntas_frecuentes` (lista de pares pregunta/respuesta)

**No editables**: `id` (identidad del trámite, ver más abajo),
`veces_consultado` (contador de uso, no contenido), `created_at`.

**`faq_generadas_automaticamente`**: el editor siempre lo setea en `false`
en el snapshot que guarda — a diferencia del pipeline de ingesta por CLI,
el editor nunca dispara la generación automática de FAQ por LLM;
`preguntas_frecuentes` es siempre lo que el admin escribió en el form
(puede quedar vacío si el admin no cargó ninguna).

## Generación de ID al crear

Solo aplica a la creación de un trámite nuevo — el `id` de un trámite
existente nunca se regenera al editarlo, ni siquiera si se le cambia el
organismo (ver "Comportamiento explícito" más abajo).

1. Si el organismo elegido **ya tiene** trámites, se reutiliza el prefijo
   del primero de ellos (la parte antes del `-`) y se calcula el siguiente
   correlativo con 4 dígitos (`RC-0032` → `RC-0033`).
2. Si el organismo **es nuevo** (sin trámites todavía), el prefijo se arma
   con las iniciales en mayúsculas de cada palabra significativa del
   nombre del organismo (ej. "Dirección de Rentas" → `DR`), arrancando en
   `0001`.
3. Si el prefijo derivado en el paso 2 ya está en uso por **otro**
   organismo (colisión de iniciales), se le agrega un dígito extra (`DR2`,
   `DR3`, …) hasta encontrar uno libre, con un tope de 9 intentos — si se
   agota, `500` con mensaje explícito en vez de loop infinito (caso
   extremo, no alcanzable con el volumen actual de organismos).

El backend calcula el ID final al guardar; el form no lo muestra como
editable antes de confirmar. Se valida además que el ID calculado no
colisione con uno ya existente (defensivo).

## Backend — módulos nuevos

### `backend/agent/admin/tramites_repository.py`

Funciones de solo lectura sobre `tramites`/`tramite_versiones`/`organismos`,
más una de lectura de chunks con embedding (necesaria para el "carry-over"
al editar):

- `listar_tramites(conn) -> list[dict]`: `id`, `nombre_oficial`,
  `organismo`, `categoria`, `veces_consultado`, `numero_version` (de la
  versión vigente), ordenado por `id`. Sin paginar — volumen bajo.
- `listar_organismos(conn) -> list[str]`: nombres de `organismos`, para el
  selector del form.
- `obtener_tramite_admin(conn, tramite_id) -> dict | None`: snapshot
  completo de la versión vigente (todos los campos editables), o `None` si
  no existe.
- `obtener_chunks_por_version(conn, version_id) -> list[dict]`: `tipo_chunk`,
  `texto`, `fuente_url`, `embedding` de todos los chunks de esa versión.

### `backend/agent/admin/tramite_editor.py`

Lógica de guardado, reutilizando lo existente en `ingest/` en vez de
duplicarlo: `ingest.hashing.compute_content_hash`,
`ingest.repository.upsert_organismo`, `.upsert_tramite`,
`.get_vigente_version`, `.close_version`, `.insert_version_with_chunks`.

**`editar_tramite(conn, tramite_id, payload: dict, embed_fn) -> dict`**

1. Arma el snapshot nuevo a partir de `payload` (los campos editables de
   arriba) + `id: tramite_id` + `faq_generadas_automaticamente: false`.
2. Calcula `content_hash = compute_content_hash(snapshot)`. Si coincide con
   el de la versión vigente: no hace nada, devuelve la versión vigente sin
   cambios (sin nueva versión, sin llamar a `embed_fn`) — mismo criterio
   idempotente que el CLI.
3. Si cambió: trae los chunks de la versión vigente
   (`obtener_chunks_por_version`) y los separa en:
   - **Preservados**: `tipo_chunk` en `requisitos`, `pasos`,
     `costo_modalidad`, `problemas_frecuentes`, `descripcion` (los
     narrativos, originados en documentos fuente reales) — viajan con su
     `texto`/`fuente_url`/`embedding` sin cambios.
   - **Recalculados**: se descartan los `tipo_chunk` `faq` y
     `enlaces_oficiales` existentes, y se reconstruyen desde el snapshot
     nuevo con la misma lógica que `ingest.chunk_builder.build_chunks` usa
     para esos dos tipos (un chunk por FAQ, un chunk de enlaces si
     `enlaces_oficiales` no está vacío).
4. Llama a `embed_fn` **solo** con los textos de los chunks recalculados.
   Si `embed_fn` lanza una excepción: `conn.rollback()`, no se llega a
   cerrar la versión vigente ni a insertar nada — se propaga como error de
   guardado (ver "Manejo de errores").
5. `close_version` sobre la vigente, `insert_version_with_chunks` con la
   unión de chunks preservados + recalculados y sus embeddings
   correspondientes, `upsert_tramite` para reflejar
   organismo/categoría/nombre en la tabla `tramites`.
6. Devuelve `{"tramite_id": ..., "numero_version": ..., "cambios": bool}`
   (`cambios: false` en el caso idempotente del paso 2).

**`crear_tramite(conn, payload: dict, embed_fn) -> dict`**

1. Resuelve/crea el organismo (`upsert_organismo`), calcula el `id` nuevo
   (regla de la sección anterior), da de alta en `tramites`
   (`upsert_tramite`).
2. Arma el snapshot y el `content_hash` igual que en `editar_tramite`.
3. Como no hay chunks previos: arma un chunk `tipo_chunk="descripcion"`
   automático con el texto `"{nombre_oficial}. {descripcion}"` (o solo
   `nombre_oficial` si `descripcion` viene vacía), más los chunks de FAQ y
   enlaces si corresponde (misma lógica que en editar).
4. `embed_fn` sobre todos esos chunks (son todos nuevos). Mismo manejo de
   error que en `editar_tramite` si falla.
5. `insert_version_with_chunks` con `numero_version=1`.
6. Devuelve `{"tramite_id": id_generado, "numero_version": 1}`.

## Backend — endpoints nuevos

Todos bajo `requiere_admin` (misma dependencia del esqueleto de admin).

- `GET /admin/tramites` → `listar_tramites`.
- `GET /admin/organismos` → `listar_organismos`.
- `GET /admin/tramites/{tramite_id}` → `obtener_tramite_admin`; `404` si no
  existe.
- `PUT /admin/tramites/{tramite_id}` → valida el body con un modelo
  Pydantic (`organismo` y `nombre_oficial` requeridos no vacíos, el resto
  opcional/lista vacía por defecto), `404` si el trámite no existe, llama a
  `editar_tramite`.
- `POST /admin/tramites` → mismo modelo Pydantic sin `tramite_id`, llama a
  `crear_tramite`.

Los dependency-injected `obtener_pool` y `obtener_openai_client` ya existen
en `agent/api.py` (usados por `/chat`); estos endpoints nuevos los
reutilizan para obtener `embed_fn = openai_client.generate_embeddings`.

## Frontend

```
app/admin/tramites/
  page.tsx              → lista de trámites + botón "Nuevo trámite"
  nuevo/page.tsx          → formulario de alta (vacío)
  [id]/page.tsx           → formulario de edición (precargado)
components/
  TramiteForm.tsx          → formulario compartido entre alta y edición
  ListaTextos.tsx           → editor de listas de strings (agregar/quitar
                              filas): requisitos, pasos,
                              problemas_frecuentes, sinonimos, keywords,
                              enlaces_oficiales
  ListaFAQ.tsx              → editor de pares pregunta/respuesta
lib/
  admin-tramites-api.ts     → tipos + cliente fetch (listarTramites,
                              listarOrganismos, obtenerTramiteAdmin,
                              crearTramite, editarTramite)
```

**`TramiteForm`**: recibe valores iniciales (vacíos para alta, precargados
para edición) y un callback `onGuardar`. Organismo es un `<select>` con los
existentes (vía `listarOrganismos`) más una opción "Otro…" que revela un
input de texto libre. Valida client-side que `organismo` y `nombre_oficial`
no estén vacíos antes de habilitar el submit (la validación autoritativa
es la del backend).

**`/admin/tramites`**: tabla sin paginar (columnas id, nombre, organismo,
categoría, veces consultado, versión vigente), cada fila linkea a
`/admin/tramites/{id}`. Botón "Nuevo trámite" → `/admin/tramites/nuevo`.
Estados: loading, error con "Reintentar", vacío ("Todavía no hay trámites
cargados").

**Guardado**: botón deshabilitado + "Guardando…" mientras está en vuelo
(el paso de embeddings puede tardar). Si falla, se muestra el mensaje de
error del backend sin perder lo tipeado en el form. Al guardar con éxito:
en edición, mensaje de confirmación con el número de versión nueva; en
alta, redirige a `/admin/tramites/{id-generado}`.

## Manejo de errores

- `GET /admin/tramites/{id}` / `PUT /admin/tramites/{id}` con id
  inexistente → `404`.
- `organismo` o `nombre_oficial` vacíos → `422`.
- Falla de `embed_fn` (ej. `OPENAI_API_KEY` inválida): `rollback()`
  completo — ni `close_version` ni la versión nueva quedan escritas — y
  `502` con `{"detail": "No se pudieron generar los embeddings. Verificá
  la configuración de OpenAI."}`.
- Colisión de prefijo de ID agotando los 9 reintentos → `500` con mensaje
  explícito.
- Frontend: mismos patrones de loading/error/vacío ya establecidos en la
  sección de chats.

**Comportamiento explícito no obvio**: editar el organismo de un trámite
existente **no regenera su `id`** (ej. sigue siendo `RC-0001` aunque pase a
pertenecer a otro organismo) — regenerarlo rompería referencias externas
(citas en el historial de chats, links). Solo cambia `organismo_id` en
`tramites`.

**Comportamiento explícito no obvio (2)**: `compute_content_hash` se
calcula sobre el snapshot editado por el admin, mientras que el CLI de
ingesta (`ingest.loader.ingest_tramite`) lo calcula sobre el
`raw_tramite` del archivo JSON — son dos formas distintas, no comparables
entre sí, del mismo hash. Consecuencia: si más adelante se vuelve a correr
el CLI sobre un trámite que fue editado desde el admin, el CLI casi
seguro va a detectar "cambio" (aunque el contenido sea equivalente) y va a
crear una nueva versión que pisa la edición manual con los datos del
archivo fuente. Es el comportamiento esperado — el archivo fuente es la
autoridad para el CLI — pero vale dejarlo escrito para que no se lea como
un bug.

## Testing

- **Backend** (`pytest`, DB real de test, mismo patrón que el resto del
  proyecto):
  - `tramites_repository.py`: `listar_tramites`, `listar_organismos`,
    `obtener_chunks_por_version` (incluyendo que devuelve el `embedding`).
  - `tramite_editor.py`:
    - `editar_tramite` sin cambios en el payload → no crea versión nueva,
      no llama a `embed_fn`.
    - `editar_tramite` con cambios → cierra la vigente, crea una nueva;
      verificar que `embed_fn` fake se llamó únicamente con los textos de
      FAQ/enlaces (no con los narrativos preservados), y que los chunks
      preservados llegan a la nueva versión con el mismo `embedding` que
      tenían.
    - `crear_tramite`: ID correcto para organismo existente (siguiente
      correlativo) y para organismo nuevo (iniciales); colisión de
      prefijo resuelta con dígito extra; chunk de descripción automático
      generado cuando no hay FAQ/enlaces.
  - Endpoints `/admin/tramites*` y `/admin/organismos`: `401` sin sesión,
    `404` en id inexistente, `422` en payload inválido, éxito end-to-end
    con un `embed_fn` fake (mismo patrón que `_FakeOpenAIClient` en
    `test_api.py`), y el caso de `embed_fn` que lanza una excepción →
    `502` + verificar que no quedó nada escrito (el `content_hash`/versión
    vigente siguen siendo los de antes del intento fallido).
- **Frontend**: sin tests automatizados de UI (mismo criterio que el resto
  del panel de admin — no hay `jsdom`/`@testing-library` instalado).
  Verificación manual: crear un trámite nuevo, editarlo, confirmar que
  aparece actualizado en la lista; si hay una `OPENAI_API_KEY` válida
  disponible, confirmar además que el chat público lo encuentra por
  búsqueda y responde con los datos editados.

## Fuera de alcance

- Carga de fuentes/documentos reales (los chunks narrativos siguen
  viniendo del pipeline CLI o de una futura sección de "carga de
  fuentes").
- Historial de versiones visible en la UI (ver diffs entre versiones
  anteriores de un trámite).
- Borrar o deshabilitar un trámite.
- Locking optimista ante ediciones concurrentes del mismo trámite (última
  escritura gana; cada guardado exitoso crea su propia versión nueva).
- Visor/editor del prompt del agente del chat (sección futura separada).

## Criterios de aceptación

- Con el backend y el frontend corriendo, y una `OPENAI_API_KEY` válida,
  entrar a `/admin/tramites` muestra la lista de trámites existentes (o el
  estado vacío si no hay ninguno).
- Crear un trámite nuevo eligiendo un organismo existente genera un ID con
  el prefijo de ese organismo y el siguiente correlativo; crear uno para
  un organismo nuevo genera un prefijo a partir de sus iniciales en
  `0001`.
- Editar un trámite existente sin cambiar nada no genera una versión
  nueva (verificable con `numero_version` sin cambios).
- Editar un trámite cambiando `requisitos` genera una versión nueva; el
  chat público, al preguntar por ese trámite usando `obtener_requisitos`,
  devuelve la lista editada.
- Si `OPENAI_API_KEY` es inválida, intentar guardar una edición o un alta
  muestra un mensaje de error claro en el form, sin perder los datos
  tipeados, y no crea una versión nueva a medias en la base.
