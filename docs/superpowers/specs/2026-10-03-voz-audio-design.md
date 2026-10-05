# Consulta por voz y headers de seguridad — Diseño

Fecha: 2026-10-03

## Objetivo

Permitir que la persona **dicte su consulta con el micrófono** en el chat, y endurecer el frontend con
headers de seguridad. Es la parte de voz del paquete `macacha-v4` (trabajo de otro integrante del equipo),
integrada con el diseño y el código actuales.

## Origen y alcance

El paquete `macacha-v4` es una copia completa del proyecto que partió del commit `e0d43e5` (9/9/2026). Se
analizó antes de decidir qué traer (ver la conversación del 2026-10-02/03).

**Se trae:**

- `backend/agent/audio_transcription.py` (transcripción con dos modelos y consenso).
- `POST /audio/transcribe`, con endurecimiento propio (ver Backend).
- `frontend/hooks/useMicrophoneRecorder.ts` y `frontend/lib/audio-api.ts`.
- El micrófono dentro de nuestro `ChatInput`, con los estilos actuales y conservando el botón "Ficha".
- Headers de seguridad en `frontend/next.config.ts`.

**No se trae:** el feedback de v4 (duplica el nuestro, que ya está en producción), el rediseño visual
(`globals.css` con clases `macacha-*`, `page.tsx`, paneles) ni el cambio de versión de Next (los
`package*.json` tienen cambios sin commitear ajenos a este trabajo; queda como seguimiento).

## Decisiones tomadas

1. **Límite de uso por IP**, en memoria del proceso y configurable.
2. **Dos modelos con consenso por defecto** (`gpt-4o-transcribe` y `gpt-4o-mini-transcribe`), como certificó
   el equipo de v4. Configurables por variable de entorno; si se configura el mismo modelo dos veces, se usa uno.
3. La transcripción **nunca se envía sola**: queda en el campo de texto y la persona decide.

## Backend

### `agent/audio_transcription.py`

Se incorpora el módulo de v4 sin cambios de comportamiento: limpieza de la transcripción (descarta las
frases que el modelo inventa con audio vacío, como "Amara.org" o "gracias por ver el video", y los textos
en otro idioma), puntaje de consenso entre las dos lecturas, detección de conflicto de intención (costo,
ubicación, requisitos, horarios, trámite) y resultado `TranscriptionResult` con `review_required`,
`alternative_text` y `consensus_reason`. Usa `OPENAI_API_KEY`. No escribe el audio a disco.

### `POST /audio/transcribe`

Cuerpo binario con el audio; `Content-Type` del audio; `?filename=` opcional.

Orden de validaciones, de lo más barato a lo más caro:

1. **Límite de uso por IP** → `429` con encabezado `Retry-After` y el mensaje "Hiciste muchas consultas por
   voz seguidas. Probá de nuevo en un minuto."
2. **Formato**: `Content-Type` en la lista permitida (flac, mpeg/mp3, mp4, m4a, ogg, wav, webm). Se **quita**
   `application/octet-stream`. Un `Content-Type` ausente se trata como `audio/webm`. No permitido → `415`.
3. **Tamaño**: si `Content-Length` supera el máximo → `413` sin leer el cuerpo. Además el cuerpo se lee **por
   partes** y se corta apenas supera el máximo (aunque no venga `Content-Length`) → `413`. Nunca se acumula
   en memoria más que el máximo.
4. Audio vacío → `400`.
5. Transcripción: sin `OPENAI_API_KEY` → `503`; sin texto confiable → `422`; falla del proveedor → `502`.

Éxito: `200` con `TranscriptionResult.to_dict()`.

Los logs registran errores y la IP, **nunca el contenido** del audio ni de la transcripción.

### Límite de uso

Clase `LimitadorPorIP` (ventana deslizante de 60 segundos, en memoria, con un candado), con reloj
inyectable para poder probarla. Poda las IP inactivas para no crecer sin límite.

**IP del cliente:** detrás del proxy de Dokploy, `request.client.host` es la IP del proxy y todos compartirían
un solo límite. Por eso se toma la IP de `X-Forwarded-For` contando desde la derecha: con
`AUDIO_PROXY_HOPS` proxies de confianza (por defecto 1) se usa la entrada `[-AUDIO_PROXY_HOPS]`, la que agregó
el proxy más cercano y que el cliente no puede falsificar. Si el encabezado no existe, se usa
`request.client.host`.

### Variables de entorno (todas opcionales)

| Variable | Por defecto | Efecto |
|---|---|---|
| `AUDIO_TRANSCRIPTION_MODEL` | `gpt-4o-transcribe` | Modelo principal |
| `AUDIO_TRANSCRIPTION_SECONDARY_MODEL` | `gpt-4o-mini-transcribe` | Segundo modelo para el consenso |
| `AUDIO_TRANSCRIPTION_CONSENSUS_THRESHOLD` | `0.66` | Puntaje mínimo de consenso |
| `AUDIO_MAX_BYTES` | `4194304` (4 MiB) | Tamaño máximo del audio (el frontend corta la grabación a los 2 minutos) |
| `AUDIO_RATE_LIMIT_PER_MINUTE` | `6` | Audios por minuto y por IP; `0` desactiva el límite |
| `AUDIO_PROXY_HOPS` | `1` | Cantidad de proxies de confianza delante del backend |

## Frontend

### Archivos

- `hooks/useMicrophoneRecorder.ts` y `lib/audio-api.ts`, tomados de v4 (sin dependencias externas).
- `components/ChatInput.tsx`: se reescribe sobre los estilos actuales (`campo-input`, `boton-primario`,
  `boton-neutro`), **conserva** el botón "Ficha" (`onAbrirFicha`) y suma el micrófono.
- Lógica pura en `lib/audio-ui.ts` (formato de duración, extensión por tipo MIME, texto de ayuda según el
  estado), con tests.

### Comportamiento del `ChatInput`

- **Botón de micrófono** junto a "Enviar". Si el navegador no soporta grabación (`MediaRecorder` o
  `getUserMedia` ausentes), el botón **no se muestra** y el chat funciona como hoy.
- **Estados:** inactivo → solicitando permiso → grabando (botón de detener, cancelar y contador `m:ss`) →
  transcribiendo → texto listo / texto para revisar / error.
- **Nunca envía solo.** El texto transcripto queda en el campo; si `review_required`, se muestra "La
  transcripción necesita revisión. Leé el texto antes de enviarlo." y, cuando difiere, "Otra lectura
  detectada: …".
- **Mientras graba o transcribe**, el campo y "Enviar" quedan deshabilitados.
- **Errores** con mensajes en voseo y un botón "Cerrar aviso"; si falló la transcripción y hay grabación,
  "Reintentar".
- **Privacidad:** al empezar a grabar se muestra "El audio se envía a un servicio externo para transcribirlo y
  no queda guardado en Macacha."
- **Accesibilidad:** `aria-label` y `title` por estado, `aria-live="polite"` para el estado, `role="alert"`
  en errores.
- **Estilos:** las animaciones usan las utilidades de Tailwind (`animate-pulse`, `animate-spin`); no se agrega
  CSS nuevo.
- Se mantiene `Enter` para enviar y `Shift+Enter` para salto de línea.

### Headers de seguridad (`next.config.ts`)

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`
y `Permissions-Policy: camera=(), geolocation=(), microphone=(self)`. El `microphone=(self)` es
imprescindible: sin él el navegador bloquearía el micrófono. El archivo se guarda sin BOM.

## Pruebas

- **pytest:** transcripción con un cliente de OpenAI falso (consenso, conflicto de intención, descarte de
  frases inventadas y de otro idioma, un solo modelo, falla de un modelo, sin clave); `LimitadorPorIP` con
  reloj falso; IP detrás de proxy (con y sin `X-Forwarded-For`, con 1 y 2 proxies, entrada falsificada a la
  izquierda); endpoint (200, 400, 413 por `Content-Length` y por cuerpo sin `Content-Length`, 415, 422, 429
  con `Retry-After`, 502, 503, sin escribir ni loguear el contenido).
- **vitest:** `lib/audio-ui.ts` (duración, extensión, texto de ayuda por estado).
- **Verificación en navegador** con Chromium y micrófono simulado (`--use-fake-device-for-media-stream`): el
  ciclo grabar → transcribir → revisar → enviar, el estado de error, el botón "Ficha" y que el micrófono no
  aparezca sin soporte. No hay sintetizador de voz disponible, así que una transcripción real de punta a punta
  queda para una prueba manual con micrófono.
- Suites completas de backend y frontend, y `tsc`.

## Despliegue

Sin cambios de base de datos. Orden: **backend y después frontend** (si el frontend sale antes, el botón
mostraría el error "No se pudo transcribir el audio"). Las variables `AUDIO_*` son opcionales; con
`OPENAI_API_KEY` ya cargada funciona. Se documenta en `docs/deploy-dokploy.md`, incluido el aviso de que los
audios se envían a OpenAI.

## Riesgos y decisiones abiertas

- **Costo:** cada audio hace dos llamadas de transcripción. El límite por IP lo acota, pero un atacante con
  muchas IP puede gastar créditos. Si hace falta, el siguiente paso sería exigir una sesión de chat existente
  o un límite global.
- **Límite en memoria del proceso:** si el backend corre con varios procesos, cada uno cuenta aparte (hoy es
  uno solo) y se reinicia con cada despliegue.
- **Privacidad:** los audios de la ciudadanía se envían a OpenAI. Es una decisión institucional a confirmar;
  el aviso en pantalla es un mínimo, no reemplaza una política de privacidad.
- **Idioma y ruido:** la transcripción está fijada en español; en ambientes ruidosos puede fallar y la
  persona verá un error o una transcripción para revisar.
- **Versión de Next:** v4 la fija en 15.5.27 (el lock actual tiene 15.5.20); queda como seguimiento.
