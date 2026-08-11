# Contacto humano desde el chat

**Fecha:** 2026-08-11
**Estado:** Aprobado, pendiente de implementación

## Contexto y objetivo

Hoy el chat de Macacha solo puede responder con la información que tiene
cargada de los trámites — no hay ninguna vía para que una persona pida
ayuda humana cuando el asistente no le alcanza, ni forma de que esa
consulta llegue a alguien responsable. Tampoco existe ninguna integración
de email en el proyecto.

El objetivo es agregar un formulario de contacto humano accesible desde el
chat (nombre, email, teléfono/WhatsApp, consulta), que la solicitud llegue
al admin del organismo dueño del trámite en cuestión (por mail y en una
sección nueva del panel admin, junto con la conversación completa), y que
el admin pueda marcarla como resuelta.

### Decisiones de alcance (confirmadas con el usuario)

- El formulario se ofrece de dos formas: un botón fijo siempre visible en
  el chat, y el propio asistente lo sugiere cuando no puede resolver la
  consulta (vía una tool nueva que el LLM invoca con criterio, más el caso
  ya existente de agotar los reintentos de tool-calling).
- El formulario pide confirmar sobre qué trámite es la consulta (selector
  si el chat citó varios, fijo si citó uno, aviso + sin trámite si no citó
  ninguno) — de ahí se deriva el organismo destinatario.
- Si el organismo no tiene ningún admin asignado (o no se identificó
  trámite/organismo), la solicitud igual se guarda y se notifica a todos
  los `super_admin` en su lugar — nunca se pierde ni se bloquea al usuario.
- Sin integración de proveedor SaaS nuevo: SMTP genérico por variables de
  entorno, mismo patrón que `OPENAI_API_KEY`.
- Nueva sección "Contacto" en el panel admin, visible para ambos roles
  (a diferencia de "Usuarios", que es solo `super_admin`), con estado
  pendiente/resuelto por solicitud.
- Sin confirmación por mail al usuario que llena el formulario — el mail
  sale solo hacia el/los admin(s), con la conversación completa del chat
  embebida en el cuerpo (no solo un link al panel).
- Los 4 campos del formulario (nombre, email, teléfono, consulta) son
  obligatorios.
- El envío de mail es best-effort: si falla, la solicitud ya quedó
  guardada y visible en `/admin/contacto` — no rompe la respuesta al
  usuario ni se pierde el dato.

## 1. Modelo de datos

Tabla nueva, agregada al final de `backend/db/schema.sql` con el mismo
estilo idempotente que ya usa el archivo:

```sql
CREATE TABLE IF NOT EXISTS solicitudes_contacto (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sesiones(id),
    tramite_id TEXT REFERENCES tramites(id),
    organismo_id INTEGER REFERENCES organismos(id),
    nombre TEXT NOT NULL,
    email TEXT NOT NULL,
    telefono TEXT NOT NULL,
    consulta TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- `tramite_id`/`organismo_id` quedan `NULL` cuando el chat no identificó
  ningún trámite. `organismo_id` se guarda denormalizado (copiado del
  trámite elegido en el momento de creación) para poder filtrar por
  organismo con el mismo patrón que ya usan `sesiones`/`tramites` — evita
  resolverlo con un JOIN en cada listado, y es estable en el tiempo (no
  cambia si el trámite se reasigna de organismo después).
- `estado`: `'pendiente'` | `'resuelto'`, validado en código con
  `Literal` en el payload de la API, no con un `CHECK` ni un `ENUM` en la
  base (a diferencia de `admins.rol`, que sí usa un `ENUM` porque además
  se lee directo en SQL en varios lugares — acá `estado` solo se escribe
  y lee a través de la API, así que la validación en código alcanza sin
  sumar un tipo nuevo a la base por dos valores).

## 2. Backend — tool del asistente, endpoint público y envío de mail

### Nueva tool `ofrecer_contacto_humano`

En `backend/agent/tools.py`, agregada a `TOOL_SCHEMAS`:

```python
{
    "type": "function",
    "function": {
        "name": "ofrecer_contacto_humano",
        "description": (
            "Usala cuando no puedas resolver la consulta de la persona — no "
            "encontrás el trámite, la información no alcanza, o la persona te "
            "dice explícitamente que la respuesta no le sirve o que necesita "
            "hablar con alguien. No la uses como primera opción: intentá "
            "resolver la consulta primero."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
},
```

No tiene función Python asociada en `ejecutar_tool` con efecto de datos —
es una señal pura. Se agrega una línea al `SYSTEM_PROMPT` en
`orchestrator.py` mencionando que esta herramienta existe y cuándo usarla
(resumen de la description de arriba).

### `orchestrator.py` — señal `sugerir_contacto`

`procesar_turno` ya arma el evento `"fin"` con `fuentes` y
`candidatos_ambiguos`. Se agrega una tercera clave, `sugerir_contacto:
bool`, en los dos puntos donde hoy se emite ese evento:

- Cuando el turno termina sin más tool calls (flujo normal): `True` si
  `"ofrecer_contacto_humano"` fue uno de los `tool_calls` de ese turno (se
  puede chequear sobre los tool_calls ya guardados en ese turno antes de
  salir del loop), `False` en cualquier otro caso.
- Cuando se agotan `MAX_ITERACIONES_TOOLS` (el mensaje ya existente "No
  pude resolver tu consulta en este momento..."): siempre `True` — este
  caso ya es, por definición, uno donde el asistente no pudo resolver la
  consulta.

### `agent/mail.py` (módulo nuevo)

`smtplib` de la librería estándar, sin dependencia nueva. Variables de
entorno nuevas en `.env`/`.env.example`, mismo patrón que
`OPENAI_API_KEY`:

```
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=notificaciones@macacha.gob.ar
```

```python
def enviar_mail(destinatarios: list[str], asunto: str, cuerpo_texto: str) -> None:
    ...  # smtplib.SMTP(host, port) + starttls() + login() + send_message()
```

Lee las variables con `os.environ[...]` en el momento de la llamada (no a
nivel de import, para no romper el arranque del backend si no están
seteadas y nadie mandó un mail todavía — a diferencia de
`ADMIN_JWT_SECRET`, que si falta rompe TODO el arranque porque se usa en
cada request de admin).

### `agent/admin/contacto_repository.py` (módulo nuevo)

Sigue el patrón de `chats_repository.py` / `tramites_repository.py`
(cada función recibe `conn` primero):

```python
def crear_solicitud(conn, session_id, tramite_id, organismo_id, nombre, email, telefono, consulta) -> str: ...

def resolver_destinatarios(conn, organismo_id: int | None) -> list[str]:
    """Emails de admins activos del organismo; si no hay organismo o
    esa lista queda vacía, emails de todos los super_admin activos."""

def listar_solicitudes(conn, organismo_id: int | None) -> list[dict]: ...

def obtener_solicitud(conn, solicitud_id: str) -> dict | None: ...

def actualizar_estado(conn, solicitud_id: str, estado: str) -> None: ...
```

### `POST /contacto` (endpoint público, sin auth)

```python
class ContactoPayload(BaseModel):
    session_id: uuid.UUID
    tramite_id: str | None = None
    nombre: str = Field(min_length=1)
    email: str = Field(min_length=1)
    telefono: str = Field(min_length=1)
    consulta: str = Field(min_length=1)


@app.post("/contacto")
def crear_solicitud_contacto(request: ContactoPayload, pool=Depends(obtener_pool)):
    with pool.connection() as conn:
        organismo_id = (
            admin_tramites_repository.obtener_organismo_id_de_tramite(conn, request.tramite_id)
            if request.tramite_id else None
        )
        solicitud_id = contacto_repository.crear_solicitud(
            conn, request.session_id, request.tramite_id, organismo_id,
            request.nombre, request.email, request.telefono, request.consulta,
        )
        conn.commit()

        destinatarios = contacto_repository.resolver_destinatarios(conn, organismo_id)
        mensajes = sessions.obtener_mensajes_visibles(conn, str(request.session_id))

    try:
        mail.enviar_mail(
            destinatarios,
            asunto=f"Nueva consulta de {request.nombre}",
            cuerpo_texto=_armar_cuerpo_mail(request, mensajes),
        )
    except Exception:
        pass  # best-effort: la solicitud ya está guardada y visible en /admin/contacto

    return {"ok": True}
```

`_armar_cuerpo_mail` arma un texto plano con los datos del formulario
seguidos de la conversación completa (rol + contenido de cada mensaje
`user`/`assistant`, mismo filtro que ya usa `sessions.obtener_mensajes_visibles`).

## 3. Endpoints de administración

Mismo patrón de filtrado/404 cross-organismo que ya se usa para
`/admin/sesiones*` y `/admin/tramites*`:

| Endpoint | Comportamiento |
|---|---|
| `GET /admin/contacto` | `admin_organismo`: filtra por su `organismo_id` (nunca ve las de `organismo_id = NULL`, esas son solo de `super_admin`). `super_admin`: todas, sin filtro. |
| `GET /admin/contacto/{id}` | `404` si no existe o (`admin_organismo` y `organismo_id` de la solicitud no coincide con el suyo) — mismo criterio de "no distinguir no-existe de es-de-otro-organismo" ya aplicado a trámites y sesiones. Incluye los mensajes completos de la sesión asociada (reutiliza `chats_repository.obtener_mensajes_completos`). |
| `PUT /admin/contacto/{id}` | Cambia `estado` (`Literal["pendiente", "resuelto"]`). Mismo chequeo de propiedad que el GET de detalle → `404`. |

`GET /admin/contacto` no requiere `requiere_super_admin` — ambos roles lo
usan, cada uno ve lo suyo (o todo, si es `super_admin`).

## 4. Frontend

### Extracción de `ConversacionChat`

El bloque que hoy renderiza la conversación en
`app/admin/chats/[id]/page.tsx` (el `.map` sobre mensajes visibles con
`BurbujaMensaje` + el componente interno `DetalleTecnico`) se mueve a
`components/ConversacionChat.tsx`, recibiendo `mensajes: MensajeAdmin[]`.
`SesionDetallePage` pasa a usarlo (refactor puro, sin cambio de
comportamiento) y la nueva página de detalle de Contacto lo reusa tal
cual — evita duplicar la lógica de renderizado de burbujas/detalle
técnico en dos lugares.

### Botón fijo + CTA sugerido en el chat

- Un link/botón fijo "¿Necesitás hablar con una persona?" en el header
  del chat (`app/page.tsx`), siempre visible, abre un modal con el
  formulario.
- `useChatStream`'s `Mensaje` type gana `sugerirContacto?: boolean`,
  poblado desde `evento.sugerir_contacto` en el evento `"fin"` (mismo
  mecanismo que ya usan `fuentes`/`candidatosAmbiguos`).
- Cuando un mensaje del asistente trae `sugerirContacto: true`,
  `ChatMessage` muestra un link inline debajo de ese mensaje puntual
  ("¿Querés que te ayude una persona? Completá este formulario") que abre
  el mismo modal.

### `ContactoHumanoModal` (componente nuevo)

Campos: nombre, email, teléfono, consulta (los 4 obligatorios,
deshabilita el envío hasta completarlos). Selección de trámite:
- Un trámite citado → fijo/no editable, mismo patrón visual que
  `organismoFijo` en `TramiteForm`.
- Varios citados → `<select>`.
- Ninguno citado → aviso ("no identificamos un trámite en esta
  conversación — tu consulta la recibe el equipo general") y se envía sin
  `tramite_id`.

La lógica de "qué mostrar según los trámites citados" (fijo / select /
aviso) se extrae a una función pura testeable — mismo criterio que ya
siguen `usePanelTramite`/`useChecklist` en este proyecto — en vez de
quedar como condicionales inline dentro del componente.

`lib/contacto-api.ts` (nuevo): `enviarSolicitudContacto(datos)` → `POST
/contacto`. Sin `credentials: "include"` — es un endpoint público, no
requiere sesión de admin.

### Sección "Contacto" en admin

- Nuevo link "Contacto" en `AdminLayout`, visible para **ambos roles**
  (a diferencia de "Usuarios", que sigue siendo solo `super_admin`).
- `app/admin/contacto/page.tsx`: tabla (Fecha, Nombre, Trámite,
  Organismo, Estado) + link a detalle. Mismo patrón de
  carga/error/reintentar que `/admin/tramites` y `/admin/chats`.
- `app/admin/contacto/[id]/page.tsx`: datos del formulario arriba, un
  control para cambiar `estado` (pendiente ⇄ resuelto), y
  `<ConversacionChat mensajes={...}>` debajo con la conversación
  completa.
- `lib/admin-contacto-api.ts` (nuevo): `listarSolicitudesContacto()`,
  `obtenerSolicitudContacto(id)`, `editarEstadoContacto(id, estado)` —
  estas sí con `credentials: "include"` (requieren sesión de admin).

## 5. Testing

### Backend (pytest)

- `agent/mail.py`: test con `smtplib.SMTP` mockeado — confirma que se
  llama con host/puerto/credenciales del entorno y con los
  destinatarios/asunto/cuerpo correctos. Sin mandar mail real.
- `agent/admin/contacto_repository.py`: `crear_solicitud`,
  `listar_solicitudes` (filtrado por organismo), `obtener_solicitud`,
  `actualizar_estado`, y los 3 casos de `resolver_destinatarios`:
  organismo con admin(s) activos, organismo sin ningún admin (→
  super_admins), `organismo_id=None` (→ super_admins).
- `POST /contacto`: crea la solicitud aunque `mail.enviar_mail` lance
  excepción (mockeada) — la solicitud debe quedar igual en la DB;
  resuelve `organismo_id` correctamente a partir de `tramite_id`; `422`
  si falta algún campo obligatorio.
- `/admin/contacto*`: mismo patrón de tests de filtrado/404
  cross-organismo ya usado para sesiones y trámites; cambio de estado.
- `orchestrator.py`: la tool `ofrecer_contacto_humano` invocada por un
  chat client fake produce `sugerir_contacto: true` en el evento `"fin"`;
  agotar `MAX_ITERACIONES_TOOLS` también lo produce; un turno normal sin
  esa tool produce `sugerir_contacto: false`.

### Frontend (vitest)

Solo la función pura de selección de trámite en `ContactoHumanoModal`
(fijo / select / aviso según la cantidad de trámites citados) — mismo
criterio que el resto del proyecto: no se testean componentes ni fetch
wrappers, solo lógica de decisión no trivial extraída a funciones puras.

## Fuera de alcance

- Confirmación por mail al usuario que llena el formulario.
- Reintento/reenvío automático de mail si el SMTP falla — queda solo en
  la base, visible en el panel; el reintento manual sería "el admin llama
  o escribe directamente con los datos de contacto que ya tiene".
- Notificaciones en tiempo real en el panel admin (websockets/polling) —
  el admin ve las solicitudes nuevas al recargar `/admin/contacto`.
