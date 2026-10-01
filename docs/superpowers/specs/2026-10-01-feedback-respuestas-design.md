# Feedback de respuestas (pulgar arriba / abajo) — Diseño

Fecha: 2026-10-01

## Objetivo

Recolectar feedback de las personas que usan el chat sobre cada respuesta del asistente, para
alimentar el Área 3 del Informe Parcial N° 2 (feedback ciudadano) y detectar dónde falla el
asistente. Debajo de cada respuesta aparece "¿Te sirvió esta respuesta?" con **Sí** y **No**. Si la
persona elige **No**, puede indicar un motivo (lista cerrada) y dejar un comentario opcional.

El feedback se consulta desde el panel admin: en el detalle de cada chat y en una pantalla de
métricas.

## Alcance

Incluido:

- Tabla nueva, endpoint público para votar, componente de feedback en el chat.
- Exposición del `id` de cada respuesta del asistente (streaming e historial).
- Feedback visible en el detalle y el listado de chats del panel admin.
- Pantalla "Feedback" con métricas, respetando el filtro por organismo de cada rol.

Fuera de alcance (decisión explícita):

- Limitación de frecuencia de votos. El endpoint es público, igual que el chat y `/contacto`; la
  única credencial es el UUID de sesión.
- Ofrecer "Hablar con una persona" después de un voto negativo.
- Exportación de feedback a CSV o gráficos con librerías externas.

## Datos

### Tabla `feedback_respuestas`

Se agrega a `backend/db/schema.sql` con `CREATE TABLE IF NOT EXISTS`, como el resto.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `mensaje_id` | UUID NOT NULL UNIQUE | FK a `mensajes(id)`. Una fila por respuesta; cambiar el voto actualiza la fila |
| `session_id` | UUID NOT NULL | FK a `sesiones(id)`; permite filtrar por sesión sin join |
| `util` | BOOLEAN NOT NULL | `true` = Sí, `false` = No |
| `motivo` | TEXT NULL | Solo con `util = false`. Valores de la lista cerrada |
| `comentario` | TEXT NULL | Máximo 500 caracteres. Solo con `util = false` |
| `created_at` | TIMESTAMPTZ NOT NULL | `now()` |
| `updated_at` | TIMESTAMPTZ NOT NULL | `now()`; se actualiza al cambiar el voto |

Índice por `session_id`. Si el voto cambia a `util = true`, `motivo` y `comentario` se ponen en
`NULL`.

### Motivos (lista cerrada)

Valores almacenados → texto mostrado:

- `no_respondio` → No respondió mi pregunta
- `info_incorrecta` → La información era incorrecta
- `faltaba_info` → Faltaba información
- `otro_tramite` → Me mostró otro trámite
- `desactualizada` → La información estaba desactualizada
- `poco_clara` → La respuesta no fue clara
- `otro` → Otro

La lista se define una vez en el backend (validación con `Literal`) y una vez en el frontend
(textos). Un test de frontend verifica que ambas listas coincidan.

## Backend

### Identificar la respuesta votable

- `sessions.guardar_mensaje` pasa a devolver el `id` del mensaje insertado (`RETURNING id`).
- El evento `fin` del orquestador incluye `mensaje_id` (el de la respuesta final del turno). El
  caso "iteraciones agotadas" también guarda el mensaje y debe incluirlo.
- `sessions.obtener_mensajes_visibles` devuelve, además, `id`, `votable` (`true` solo para
  mensajes del asistente sin `tool_calls`, es decir, respuestas finales) y `feedback`
  (`{util, motivo, comentario}` o `null`).

### `POST /feedback` (público)

Cuerpo: `session_id`, `mensaje_id`, `util`, `motivo` (opcional), `comentario` (opcional).

- Valida que el mensaje exista, pertenezca a esa sesión y sea del asistente sin `tool_calls`. Si
  no, responde 404.
- `motivo` y `comentario` solo se aceptan con `util = false`; si llegan con `util = true`, 422.
- Hace upsert por `mensaje_id`. Un voto sin motivo es válido: el "No" cuenta aunque la persona no
  explique nada. El motivo y el comentario llegan después como una segunda llamada que actualiza
  la misma fila.
- Un voto posterior sin `motivo`/`comentario` no borra los ya guardados mientras `util` siga en
  `false`; solo cambiar a `true` los limpia.

### Panel admin

- `GET /admin/sesiones/{id}`: cada mensaje del asistente incluye su `feedback` (o `null`).
- `GET /admin/sesiones`: cada sesión incluye `votos_positivos` y `votos_negativos`.
- `GET /admin/feedback/metricas`: totales, % útil, motivos más frecuentes, serie por día,
  últimos comentarios negativos y desglose por organismo.
- Permisos: `super_admin` ve todo; `admin_organismo` solo las sesiones que ya puede ver hoy
  (las que citan trámites de su organismo), reutilizando `sesion_pertenece_a_organismo` y la
  lógica de `_organismos_de_tramites`.

### Desglose por organismo

Los mensajes no registran a qué organismo corresponde cada uno, y una sesión puede citar trámites
de varios. Regla: el voto cuenta en **cada** organismo citado por su sesión; si la sesión no
citó ningún trámite, cuenta en "Sin trámite". Es una aproximación: un voto puede aparecer en más
de un organismo, y la pantalla lo aclara.

### Consistencia con el commit

La API emite `fin` antes del `commit` de la transacción del turno. El frontend solo muestra el
widget cuando el stream terminó por completo (el commit ya ocurrió), de modo que `POST /feedback`
no puede competir con la transacción del turno.

## Frontend (chat)

### `FeedbackRespuesta`

Componente nuevo, debajo de cada mensaje del asistente que cumpla: tiene `id`, es `votable`, no
tiene `error`, tiene contenido y el stream terminó. Estilo oscuro, siguiendo la captura de
referencia.

Estados:

1. **Inicial:** "¿Te sirvió esta respuesta?" con botones 👍 Sí y 👎 No.
2. **Sí:** guarda el voto y muestra "¡Gracias por tu opinión!".
3. **No:** guarda el voto y despliega el selector "¿Por qué no te sirvió?" y el campo "Comentario
   opcional", con la leyenda "No incluyas datos personales" y límite de 500 caracteres. Al enviar,
   actualiza la fila y muestra "Gracias, tu comentario nos ayuda a mejorar".
4. **Historial:** si el historial trae `feedback`, el componente arranca en el estado
   correspondiente (agradecimiento, o selector de motivo si el voto fue No).

La persona puede cambiar el voto (de Sí a No, o al revés) en cualquier momento; el voto se
actualiza sobre la misma fila.

### Errores

Si falla el envío, se muestra un aviso discreto con la opción de reintentar. Un error de feedback
nunca bloquea el chat ni el envío de mensajes.

### Tipos

`Mensaje` suma `id?`, `votable?` y `feedback?`. `EventoSSE` de tipo `fin` suma `mensaje_id`. El
hook asigna el `id` al último mensaje al recibir `fin`.

## Frontend (panel admin)

- **Detalle del chat:** bajo cada respuesta del asistente, el voto (👍/👎), el motivo y el
  comentario.
- **Listado de chats:** indicador de votos negativos por sesión.
- **Pantalla "Feedback"** (nueva entrada del menú): tarjetas con total de votos y % útil, barras
  simples (CSS) con los motivos más frecuentes, serie por día, lista de comentarios negativos
  recientes y tabla por organismo con la aclaración de la aproximación.

## Pruebas

- **pytest:** repositorio de feedback (upsert, limpieza al pasar a Sí, validaciones), endpoint
  `POST /feedback` (404 por mensaje ajeno o no votable, 422 por motivo con `util = true`),
  métricas y filtro por organismo para ambos roles, `guardar_mensaje` devolviendo el `id`,
  `mensaje_id` en `fin`, `votable` en el historial.
- **vitest:** coincidencia entre la lista de motivos del frontend y la del backend; lógica pura
  de estados del componente si se extrae.
- **Verificación visual:** capturas del componente en sus estados, en 390 px y en escritorio, y
  de la pantalla de métricas con datos de prueba.

## Despliegue

`schema.sql` se aplica a mano en producción (ver `docs/deploy-dokploy.md`). Al desplegar hay que
volver a correr `psql "<connection-string-de-produccion>" -f backend/db/schema.sql` para crear
`feedback_respuestas` antes de que el frontend nuevo esté en línea; si el frontend sale primero,
los votos fallarían con el aviso de error discreto.

## Riesgos y decisiones abiertas

- **Datos personales en comentarios:** el campo es texto libre. Se mitiga con la leyenda y el
  límite de caracteres; no hay filtrado automático.
- **Desglose por organismo aproximado:** descrito arriba.
- **Votos sin autenticación:** cualquiera con un UUID de sesión puede votar. Mismo modelo de
  amenaza que el resto del chat público.
