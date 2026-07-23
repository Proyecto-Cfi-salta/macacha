# Macacha — Paneles laterales (info del trámite + ranking de frecuentes)

## Contexto

El frontend actual (ver `2026-07-09-frontend-design.md`) es una única pantalla
de chat centrada. Este documento agrega una estructura de tres columnas:

- **Centro**: el chat (sin cambios de comportamiento).
- **Derecha**: información del trámite que se está identificando en la
  charla (requisitos, teléfono, mail de contacto).
- **Izquierda**: ranking de los trámites más consultados del organismo del
  trámite identificado.

## Cambios de datos en el backend

### Contacto por trámite

Se agregan dos campos al snapshot de cada trámite (mismo lugar donde ya
viven `costo`, `modalidad`, `duracion`): `telefono_contacto` y
`email_contacto`, ambos `string`, default `""` si no vienen en la fuente de
ingesta.

- `backend/ingest/snapshot_builder.py`: agregar ambas claves al dict que
  arma `build_snapshot`, leyendo `raw_tramite.get("telefono_contacto", "")`
  y `raw_tramite.get("email_contacto", "")`.
- No requiere cambio de `schema.sql` (van dentro de la columna `snapshot
  JSONB` existente en `tramite_versiones`).
- Los 32 trámites ya cargados no van a tener estos campos poblados hasta que
  se re-ingesten con datos reales que los incluyan — la carga de esos datos
  reales queda **fuera de alcance** de este documento.

### Contador de consultas (`veces_consultado`)

Se agrega una columna nueva a la tabla `tramites`:

```sql
ALTER TABLE tramites ADD COLUMN IF NOT EXISTS veces_consultado INTEGER NOT NULL DEFAULT 0;
```

Esta columna vive fuera del versionado de `tramite_versiones` a propósito:
la frecuencia de uso no debe generar una nueva versión del trámite ni
afectar `content_hash`.

**Incremento**: en `agent/api.py`, dentro del endpoint `POST /chat`, después
de que `procesar_turno` termina de generar los eventos y antes del
`conn.commit()`, se incrementa `veces_consultado` en 1 para cada
`tramite_id` distinto presente en el evento `"fin"` (es decir, una vez por
turno por trámite, no una vez por cada tool call — coherente con que
`fuentes` ya deduplica por trámite). Si el turno termina en error (no hay
evento `"fin"`), no se incrementa nada.

## Endpoints nuevos

### `GET /tramites/{tramite_id}`

Devuelve el detalle de un trámite para el panel derecho:

```json
{
  "tramite_id": "RC-0001",
  "nombre_oficial": "...",
  "organismo": "...",
  "categoria": "...",
  "requisitos": ["..."],
  "telefono_contacto": "...",
  "email_contacto": "..."
}
```

404 si el trámite no existe o no tiene versión vigente (mismo criterio que
usa hoy `obtener_snapshot_vigente`).

### `GET /organismos/{organismo}/tramites-frecuentes`

`{organismo}` es el nombre del organismo (mismo string que ya devuelve
`buscar_tramite` en el campo `organismo`), no un ID interno.

Devuelve el top 5 trámites de ese organismo ordenados por
`veces_consultado` descendente:

```json
[
  {"tramite_id": "RC-0001", "nombre_oficial": "...", "veces_consultado": 12}
]
```

Si el organismo no tiene trámites consultados aún, devuelve `[]` (no
error) — esto es lo esperado al arrancar una sesión nueva, no un caso de
error.

## Frontend

### Estructura de la página

`app/page.tsx` pasa de un layout de una columna a un grid de tres columnas
en desktop:

- Centro: el chat existente (`ChatMessage` + `ChatInput`), mismo
  comportamiento y ancho máximo que ya tiene.
- `components/TramiteInfoPanel.tsx` (derecha): estado vacío ("La info del
  trámite va a aparecer acá") hasta que se identifica un trámite. Cuando el
  evento `"fin"` de un turno trae `fuentes` no vacías, toma el **último**
  `tramite_id` de esa lista y llama a `GET /tramites/{id}` para poblar el
  panel (nombre oficial, requisitos, teléfono, mail). Si en un turno
  posterior se identifica un trámite distinto, el panel reemplaza su
  contenido (no acumula tarjetas de trámites anteriores).
- `components/TramitesFrecuentesPanel.tsx` (izquierda): mismo estado vacío
  inicial. Cuando `TramiteInfoPanel` resuelve el `organismo` del trámite
  actual, se dispara `GET /organismos/{organismo}/tramites-frecuentes` y se
  muestra la lista top 5 (nombre + cantidad de consultas). Si cambia el
  organismo del trámite identificado, se vuelve a pedir y se reemplaza la
  lista.

### Mobile (viewport angosto)

El diseño original es mobile-first y las tres columnas no entran en una
pantalla de celular. Se agregan tabs arriba de la pantalla: **Chat** / **Info
del trámite** / **Más consultados**, que muestran una sola sección a la vez
a pantalla completa. El tab "Chat" es el default al cargar la página.

### Hooks y flujo de datos

- `lib/api.ts`: se agregan `obtenerTramite(tramiteId): Promise<TramiteDetalle>`
  (→ `GET /tramites/{id}`) y `obtenerTramitesFrecuentes(organismo):
  Promise<TramiteFrecuente[]>` (→ `GET /organismos/{organismo}/tramites-frecuentes`).
- `hooks/useTramiteActual.ts`: recibe `mensajes` (el array que ya devuelve
  `useChatStream`). Busca el último mensaje del asistente con `fuentes` no
  vacías y toma el último `tramite_id` de esa lista. Cuando ese id cambia
  (respecto del anterior), llama a `obtenerTramite` y expone `{ tramite,
  cargando }`. Si no hay ningún trámite identificado todavía, `tramite` es
  `null`.
- `hooks/useTramitesFrecuentes.ts`: recibe `organismo: string | undefined`
  (viene de `tramite?.organismo` del hook anterior). Cuando cambia, llama a
  `obtenerTramitesFrecuentes` y expone `{ tramites, cargando }`. Si
  `organismo` es `undefined`, no hace ningún fetch y `tramites` es `[]`.
- `app/page.tsx` compone los tres: `useChatStream` → `useTramiteActual(mensajes)`
  → `useTramitesFrecuentes(tramite?.organismo)`, y pasa los datos resultantes
  a los paneles laterales como props.

## Testing

- Test unitario (Vitest) para `useTramiteActual`: dado un array de mensajes
  con distintas combinaciones de `fuentes` (sin fuentes, con una fuente, con
  varias, con el mismo `tramite_id` repetido en dos turnos, con un
  `tramite_id` distinto en un turno posterior), confirma que detecta el
  último `tramite_id` correcto y `null` cuando no hay fuentes en ningún
  mensaje.
- Verificación manual end-to-end (backend + frontend corriendo): preguntar
  por un trámite y ver que el panel derecho se puebla con sus requisitos y
  contacto; preguntar por un trámite de otro organismo y ver que el panel
  izquierdo cambia de ranking; recargar la página y confirmar que, como
  antes, se hidrata el historial de la charla (los paneles laterales
  arrancan vacíos hasta el próximo turno, ya que no se reconstruyen a partir
  del historial); probar en viewport mobile que los tabs alternan
  correctamente entre las 3 vistas.

## Fuera de alcance

- Carga de datos reales de `telefono_contacto` / `email_contacto` para los
  32 trámites ya ingeridos (los campos quedan vacíos hasta la próxima
  ingesta con esos datos).
- Reconstruir el panel derecho/izquierdo a partir del historial al recargar
  la página (hoy `GET /sesiones/{id}/mensajes` no devuelve `fuentes` de
  turnos pasados, y este documento no cambia ese contrato).
- Un endpoint para listar el ranking global (de todos los organismos); el
  ranking siempre está acotado al organismo del trámite identificado en la
  charla actual.
- Cachear o persistir en el cliente los resultados de `GET /tramites/{id}`
  o `GET /organismos/{organismo}/tramites-frecuentes` entre sesiones.

## Criterios de aceptación

- Con el backend y el frontend corriendo, al preguntar "¿qué necesito para
  sacar un acta de nacimiento?" el panel derecho pasa de su estado vacío a
  mostrar el nombre oficial, los requisitos y el contacto de ese trámite.
- El panel izquierdo muestra el top 5 de trámites más consultados del
  organismo de ese trámite, incluyendo el propio trámite consultado (con
  `veces_consultado` en al menos 1).
- Preguntar luego por un trámite de un organismo distinto actualiza ambos
  paneles (derecho con el nuevo trámite, izquierdo con el ranking del nuevo
  organismo).
- En un viewport de celular, los tabs permiten ver el chat, la info del
  trámite y el ranking, cada uno a pantalla completa.
