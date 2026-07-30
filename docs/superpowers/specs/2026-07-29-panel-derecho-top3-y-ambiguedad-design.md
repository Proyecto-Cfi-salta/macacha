# Macacha — Panel derecho: top 3 al inicio y candidatos ambiguos

## Contexto

Desde `2026-07-22-paneles-laterales-design.md` el panel derecho
(`TramiteInfoPanel`) solo tiene dos estados: vacío ("La info del trámite va
a aparecer acá") o el detalle completo de un trámite ya identificado. El
panel izquierdo de trámites más consultados (`TramitesFrecuentesPanel`,
acotado al organismo del trámite actual) se sacó de la UI en
`2026-07-29` (commit `ae3619b`) porque no convencía como columna aparte,
pero el componente y su hook (`useTramitesFrecuentes`) se dejaron sin usar
en el repo.

Este documento agrega dos estados intermedios al panel derecho para
mejorar la experiencia mientras no hay un trámite identificado:

1. **Al cargar la página** (o mientras la charla no identificó ningún
   trámite todavía): en vez de quedar vacío, muestra el top 3 de trámites
   más consultados **de forma global** (no acotado a un organismo, porque
   todavía no hay ningún trámite en contexto).
2. **Durante la charla, cuando hay ambigüedad**: si `buscar_tramite`
   devuelve varios candidatos y el modelo no se decidió por ninguno en su
   respuesta, el panel muestra nombre y descripción de esos candidatos
   (hasta 3) en vez de quedar vacío. Cuando la charla se resuelve a un
   único trámite, el panel pasa a mostrar la info completa de siempre.

Esto también retoma algo que el documento de `2026-07-22` había dejado
explícitamente fuera de alcance ("un endpoint para listar el ranking
global"): acá sí se agrega, porque ahora hace falta para el estado inicial
sin trámite en contexto.

## Backend

### Ranking global de trámites más consultados

Nueva función en `backend/ingest/repository.py`:

```python
def obtener_top_tramites(conn, limite: int = 3) -> list[dict]:
```

Mismo criterio que `obtener_tramites_frecuentes` (ordena por
`veces_consultado` descendente, excluye los que tienen `veces_consultado =
0`) pero sin el `WHERE o.nombre = %s` — es un ranking de todos los
organismos.

Nuevo endpoint en `backend/agent/api.py`:

```
GET /tramites-frecuentes
```

Devuelve el top 3 (mismo shape que el endpoint existente por organismo):

```json
[{"tramite_id": "RC-0001", "nombre_oficial": "...", "veces_consultado": 12}]
```

Si todavía no hay ningún trámite consultado, devuelve `[]`.

El endpoint existente `GET /organismos/{organismo}/tramites-frecuentes` no
se toca (queda sin uso desde el frontend, igual que antes de este
documento).

### Candidatos ambiguos en el evento `"fin"` del chat

En `backend/agent/orchestrator.py`, al final de `procesar_turno`: hoy,
cuando el turno termina sin tool calls, se llama a
`_citar_candidatos_mencionados` y se arma `fuentes` a partir de
`tramites_citados`. Se agrega, en el mismo punto, una segunda lista:

```python
candidatos_ambiguos = (
    _armar_candidatos_ambiguos(conn, candidatos_buscados, tramites_citados)
    if not tramites_citados
    else []
)
```

`_armar_candidatos_ambiguos` recorre `candidatos_buscados` (dict
`{tramite_id: nombre_oficial}`, en el orden en que `buscar_tramite` los
devolvió — ya vienen rankeados por relevancia) y arma, para hasta los
primeros 3, un dict `{tramite_id, nombre_oficial, descripcion}` leyendo
`descripcion` del snapshot vigente (`obtener_snapshot_vigente`, mismo
helper que ya usa `_armar_fuentes`).

Es decir: si el turno terminó con `tramites_citados` no vacío (se resolvió
a uno o más trámites), `candidatos_ambiguos` va vacío. Si terminó sin
citar ninguno pero hubo candidatos buscados, `candidatos_ambiguos` trae
esos candidatos. Nunca se llenan los dos a la vez.

El evento `"fin"` pasa a tener esta forma:

```python
{"tipo": "fin", "fuentes": [...], "candidatos_ambiguos": [...]}
```

`agent/api.py` no necesita cambios: ya reenvía el evento tal cual llega
de `procesar_turno`, y solo usa `evento["fuentes"]` para incrementar
`veces_consultado` (los candidatos ambiguos, al no estar confirmados, no
incrementan el contador de nadie).

## Frontend

### Tipos nuevos

En `lib/api.ts`:

```ts
export async function obtenerTopTramites(): Promise<TramiteFrecuente[]>
// GET /tramites-frecuentes
```

En `hooks/useChatStream.ts`:

```ts
export type CandidatoAmbiguo = {
  tramite_id: string;
  nombre_oficial: string;
  descripcion: string;
};
```

`Fuente` no cambia. `Mensaje` agrega `candidatosAmbiguos?: CandidatoAmbiguo[]`.
`EventoSSE` (caso `"fin"`) agrega `candidatos_ambiguos: CandidatoAmbiguo[]`.
`aplicarEvento` copia ese campo al mensaje igual que ya hace con `fuentes`.

### Estado del panel derecho

Se reemplaza `hooks/useTramiteActual.ts` por `hooks/usePanelTramite.ts`
(mismo rol — recibe `mensajes` — pero ahora expone un estado con 4 formas
en vez de un `tramite | null`):

```ts
type VistaPanel =
  | { tipo: "cargando" }
  | { tipo: "top3"; tramites: TramiteFrecuente[] }
  | { tipo: "ambiguo"; candidatos: CandidatoAmbiguo[] }
  | { tipo: "tramite"; tramite: TramiteDetalle };
```

Lógica: recorre `mensajes` de atrás para adelante buscando el primer
mensaje (empezando por el más nuevo) que tenga `fuentes.length > 0` o
`candidatosAmbiguos.length > 0`.

- Si encuentra `fuentes` primero: toma el último `tramite_id` de esa
  lista (mismo criterio que `obtenerUltimoTramiteId` hoy), pide el detalle
  con `obtenerTramite` y expone `{tipo: "tramite", tramite}` cuando
  resuelve.
- Si encuentra `candidatosAmbiguos` primero: expone
  `{tipo: "ambiguo", candidatos: candidatosAmbiguos}` directamente, sin
  pedir nada más (ya viene con nombre y descripción).
- Si no encuentra ninguno de los dos en ningún mensaje: pide el top 3
  global una sola vez (al montar) y expone `{tipo: "top3", tramites}`.
  Mientras esa carga inicial está en curso, expone `{tipo: "cargando"}`.

Como el recorrido es de atrás para adelante y se detiene en el primer
match, una vez que la charla se resuelve a un trámite puntual, mensajes
ambiguos anteriores en la misma charla dejan de tener efecto — el panel
muestra la info completa y no vuelve a la ambigüedad vieja.

### Componentes

- `components/TramiteInfoPanel.tsx`: sin cambios, se usa para
  `tipo: "tramite"`.
- Nuevo `components/TramitesAmbiguosPanel.tsx`: título "¿Cuál de estos
  trámites te interesa?", lista de candidatos (nombre en negrita +
  descripción abajo), cada uno como botón clickeable. Al hacer click llama
  a `onPreguntar(`Quiero información sobre ${nombre_oficial}`)`, mismo
  patrón que `BotonDuda` en `TramiteInfoPanel`.
- `components/TramitesFrecuentesPanel.tsx` (hoy sin uso): se reactiva para
  `tipo: "top3"`. Se le agrega la misma interacción clickeable que al
  panel de ambiguos: cada ítem de la lista, al hacer click, llama a
  `onPreguntar(`Quiero información sobre ${nombre_oficial}`)`. Requiere
  agregarle las props `onPreguntar` y `preguntarDeshabilitado` (mismo
  contrato que ya usa `TramiteInfoPanel`).
- `hooks/useTramitesFrecuentes.ts` (el acotado por organismo) sigue sin
  uso, no se toca.

En `app/page.tsx`, el `<aside>` derecho pasa de renderizar siempre
`TramiteInfoPanel` a elegir el componente según `vista.tipo`:

```tsx
{vista.tipo === "tramite" && <TramiteInfoPanel tramite={vista.tramite} ... />}
{vista.tipo === "ambiguo" && <TramitesAmbiguosPanel candidatos={vista.candidatos} ... />}
{vista.tipo === "top3" && <TramitesFrecuentesPanel tramites={vista.tramites} ... />}
{vista.tipo === "cargando" && null}
```

`preguntarSobre` (ya existe en `page.tsx`) se pasa como `onPreguntar` a
los tres.

## Testing

**Backend:**

- `tests/test_repository.py`: tests de `obtener_top_tramites` — ranking
  global mezclando organismos, respeta `limite`, excluye
  `veces_consultado = 0` (mismo estilo que los tests ya existentes de
  `obtener_tramites_frecuentes`).
- `tests/test_api.py`: test de `GET /tramites-frecuentes` devolviendo el
  ranking global; test de lista vacía sin consultas.
- `tests/test_orchestrator.py`: extender el test existente
  `test_procesar_turno_busqueda_ambigua_sin_nombre_en_el_texto_no_cita_fuentes`
  (o agregar uno nuevo) para verificar que `candidatos_ambiguos` trae los 2
  candidatos con `nombre_oficial` y `descripcion`; agregar un test donde,
  al resolverse a un único trámite, `candidatos_ambiguos` es `[]`.

**Frontend:**

- `hooks/useChatStream.test.ts`: extender para verificar que un evento
  `"fin"` con `candidatos_ambiguos` se refleja en `candidatosAmbiguos` del
  mensaje.
- Nuevo `hooks/usePanelTramite.test.ts`: casos para los 4 estados —
  ninguna fuente ni ambigüedad (→ pide top 3), candidatos ambiguos en el
  último mensaje relevante (→ `tipo: "ambiguo"` sin fetch), fuentes en el
  último mensaje relevante (→ `tipo: "tramite"`, con fetch), y el caso de
  ambigüedad seguida de resolución en un mensaje posterior (→ `tipo:
  "tramite"`, no vuelve a mostrar los candidatos viejos).
- Verificación manual end-to-end: recargar la página sin charla y ver el
  top 3; preguntar "hola como hago una denuncia" y ver los candidatos
  ambiguos con descripción; hacer click en uno y ver que el panel pasa a
  mostrar la info completa de ese trámite.

## Fuera de alcance

- Reconstruir `candidatosAmbiguos` o `fuentes` a partir del historial al
  recargar la página a mitad de una charla (`GET
  /sesiones/{id}/mensajes` sigue sin devolver esos campos de turnos
  pasados — limitación ya documentada en `2026-07-22`). Consecuencia
  esperada: si se recarga la página a mitad de una charla ya resuelta, el
  panel vuelve a mostrar el top 3 hasta el próximo turno, no el trámite
  que ya se había identificado.
- Cachear el top 3 entre sesiones o refrescarlo sin recargar la página.
- Cambiar el criterio de qué cuenta como "ambiguo" (eso ya lo resuelve
  `_citar_candidatos_mencionados`, sin cambios en este documento salvo
  exponer los candidatos que ya calculaba).
- Tocar el endpoint por organismo o `useTramitesFrecuentes` (quedan sin
  uso, como ya estaban).

## Criterios de aceptación

- Al abrir la página sin ninguna charla previa, el panel derecho muestra
  el top 3 global de trámites más consultados (o queda vacío si todavía
  no hay ninguno consultado).
- Al preguntar "hola como hago una denuncia" (con trámites de más de un
  organismo que matchean "denuncia"), el panel derecho muestra nombre y
  descripción de hasta 3 candidatos, sin repetir esa info en el texto del
  chat.
- Al hacer click en uno de esos candidatos (o preguntar algo que lo
  desambigüe), el panel pasa a mostrar la info completa de ese trámite.
- El contador `veces_consultado` no se incrementa para los candidatos
  ambiguos que no se llegaron a confirmar.
