# Macacha — Núcleo de datos (esquema + versionado + ingesta)

## Contexto general del sistema

Macacha es un asistente virtual que orienta a los ciudadanos sobre trámites de la
administración pública de la Provincia de Salta. El sistema completo se compone de
cuatro subsistemas, construidos en este orden:

1. **Núcleo de datos** (este documento): esquema Postgres + pgvector, versionado de
   trámites y pipeline de ingesta desde archivos JSON fuente hacia objetos
   enriquecidos con embeddings.
2. **Motor de recuperación**: búsqueda híbrida (vectorial + full-text search) con
   fusión por Reciprocal Rank Fusion (RRF), y re-ranking final vía LLM (OpenAI).
3. **Agente conversacional**: tool-calling nativo de OpenAI con herramientas
   separadas (buscar trámite, requisitos, costos/modalidad, pasos, normativa,
   formularios/enlaces, problemas frecuentes), orquestado en FastAPI, con
   historial de conversación persistente en Postgres e identidad de sesión
   anónima (uuid en localStorage, sin login).
4. **Frontend**: chat en Next.js + Tailwind, con streaming de respuestas vía SSE
   y visualización de fuentes oficiales citadas.

Este documento cubre **solo el subsistema 1**. Los subsistemas 2-4 se
diseñarán y planificarán en etapas separadas, una vez que el núcleo de datos
esté implementado y funcionando.

### Dataset de origen

Fuente inicial: `/home/seba/Descargas/entidades_tramites_registro_civil.json`,
32 trámites del organismo "Registro Civil" de Salta, en 8 categorías (Actas,
Nacimiento, Matrimonio, Defunción, Unión Convivencial, Identidad de Género,
DNI/Pasaporte, Asesoría Legal). Cada objeto del JSON ya trae, por trámite:
`id`, `organismo`, `categoria`, `tramite` (nombre oficial), `descripcion`,
`objetivo`, `intenciones`, `sinonimos`, `keywords`, `requisitos`,
`documentacion` (en la práctica, duplica `requisitos`), `pasos`, `costo`,
`duracion`, `modalidad`, `problemas_frecuentes`, `preguntas_frecuentes`
(pregunta + respuesta), `chunks` (fragmentos ya segmentados con `chunk_id` y
`fuente` URL), y un `embedding_text` precalculado (no se usa: generamos
embeddings por chunk, no por trámite completo).

El esquema se diseña para ser **agnóstico del organismo**: aunque hoy solo hay
datos de Registro Civil, `organismos` es una tabla propia para poder sumar
otros organismos de la provincia sin cambios estructurales.

## Modelo de datos

### `organismos`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | serial PK | |
| `nombre` | text unique | ej. "Registro Civil" |

### `tramites`
Identidad estable de un trámite, independiente de sus versiones de contenido.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | text PK | clave natural del origen, ej. `RC-0001` |
| `organismo_id` | int FK → organismos | |
| `categoria` | text | ej. "Actas" |
| `nombre_oficial` | text | ej. "Actas Regulares (...)" |
| `created_at` | timestamptz default now() | |

### `tramite_versiones`
Cada fila es una "foto" completa del contenido enriquecido de un trámite en un
momento dado. Permite conservar el historial y controlar vigencia sin afectar
la búsqueda activa.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tramite_id` | text FK → tramites | |
| `numero_version` | int | 1, 2, 3... por trámite |
| `es_vigente` | boolean | solo una versión vigente por trámite |
| `vigente_desde` | timestamptz | |
| `vigente_hasta` | timestamptz null | null si es la vigente |
| `content_hash` | text | sha256 de los campos enriquecidos, para detectar cambios reales entre ingestas |
| `snapshot` | jsonb | objeto completo enriquecido (ver "Objeto enriquecido" abajo) |

Índice único parcial: `(tramite_id) WHERE es_vigente = true` para garantizar
una sola versión vigente por trámite.

### `tramite_chunks`
Fragmentos optimizados para embeddings, atados a una versión específica.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `version_id` | uuid FK → tramite_versiones | |
| `tipo_chunk` | text | `descripcion` / `requisitos` / `pasos` / `costo_modalidad` / `problemas_frecuentes` / `faq` / `enlaces_oficiales` |
| `texto` | text | contenido del fragmento |
| `fuente_url` | text null | URL oficial de donde sale el fragmento |
| `embedding` | vector(1536) | `text-embedding-3-small` |
| `tsv` | tsvector generado | `to_tsvector('spanish', texto)`, columna generada `STORED` |

Índices: `ivfflat`/`hnsw` sobre `embedding` (cosine), GIN sobre `tsv`, btree
sobre `version_id`.

La búsqueda (subsistema 2) siempre hace `JOIN tramite_versiones ON es_vigente
= true`, así el historial queda auditable pero nunca interfiere con las
respuestas del agente.

### Objeto enriquecido (`snapshot` jsonb)

Estructura exacta que se guarda en `tramite_versiones.snapshot` y que se
expone tal cual vía API en subsistemas futuros:

```json
{
  "id": "RC-0001",
  "organismo": "Registro Civil",
  "categoria": "Actas",
  "nombre_oficial": "Actas Regulares (...)",
  "sinonimos": ["..."],
  "keywords": ["..."],
  "descripcion": "...",
  "objetivo": "...",
  "requisitos": ["..."],
  "pasos": ["..."],
  "costo": "$6000",
  "modalidad": "Online",
  "duracion": "10 días hábiles",
  "problemas_frecuentes": ["..."],
  "preguntas_frecuentes": [{"pregunta": "...", "respuesta": "..."}],
  "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/..."],
  "faq_generadas_automaticamente": false
}
```

`enlaces_oficiales` se arma extrayendo por regex todas las URLs presentes en
`pasos` y en `chunks[].fuente` del JSON original, deduplicadas.

`faq_generadas_automaticamente` queda en `false` para todo el dataset actual
(ya trae FAQs). Se deja el campo para cuando se ingesten trámites de otros
organismos sin FAQs propias (ver siguiente sección).

## Pipeline de ingesta

Script CLI: `python -m ingest.load <archivo.json>` (idempotente, se puede
correr las veces que haga falta con el mismo u otro archivo).

1. Parsear el JSON (lista de objetos trámite).
2. Por cada objeto:
   a. Upsert en `organismos` (por nombre) y en `tramites` (por `id` natural),
      actualizando `categoria`/`nombre_oficial` si cambiaron.
   b. Armar el objeto enriquecido (snapshot) según la estructura de arriba.
   c. Si el trámite no trae `preguntas_frecuentes`, generar 2-3 FAQs vía LLM
      (OpenAI, prompt simple con descripción/requisitos/pasos como contexto) y
      marcar `faq_generadas_automaticamente: true`.
   d. Calcular `content_hash` (sha256 del snapshot serializado de forma
      determinística).
   e. Buscar la versión vigente actual de ese trámite:
      - Si no existe → crear versión 1, vigente.
      - Si existe y el hash es igual → no hacer nada (sin nueva versión, sin
        re-embeddings).
      - Si existe y el hash cambió → cerrar la versión anterior
        (`es_vigente=false`, `vigente_hasta=now()`) y crear la nueva versión
        vigente con `numero_version` incrementado.
   f. Si se creó una versión nueva, generar sus chunks:
      - Reutilizar los `chunks` del JSON original tal cual (ya vienen
        segmentados por descripción/requisitos/pasos/costo/problemas), como
        chunks de tipo correspondiente.
      - Agregar un chunk de tipo `faq` por cada pregunta frecuente (texto:
        pregunta + respuesta concatenadas).
      - Agregar un chunk de tipo `enlaces_oficiales` con la lista de URLs.
   g. Generar embeddings en batch (una sola llamada a la API de OpenAI por
      trámite, con todos sus chunks nuevos) usando `text-embedding-3-small`.
   h. Insertar todo (versión + chunks) en una transacción.
3. Reportar por consola un resumen: trámites nuevos, trámites sin cambios,
   trámites con nueva versión, FAQs auto-generadas.

### Configuración

- `OPENAI_API_KEY` vía variable de entorno (no se gestiona en código ni se
  versiona).
- `DATABASE_URL` vía variable de entorno, apuntando al Postgres de
  `docker-compose` (pgvector incluido en la imagen).
- `docker-compose.yml` con un servicio `postgres` (imagen `pgvector/pgvector`)
  para desarrollo local. Sin configuración de despliegue a producción por
  ahora.

## Fuera de alcance de este documento

- Endpoints HTTP para consultar trámites (llega con el subsistema 2/3).
- Búsqueda híbrida y re-ranking (subsistema 2).
- Lógica del agente y sesiones de chat (subsistema 3).
- Frontend (subsistema 4).
- Despliegue a producción / CI-CD.
- Autenticación de usuarios.

## Criterios de aceptación

- Correr el pipeline de ingesta sobre el JSON de Registro Civil deja 32
  trámites, cada uno con exactamente una versión vigente y sus chunks con
  embeddings generados.
- Volver a correr el pipeline sin cambios en el JSON no crea versiones nuevas
  ni regenera embeddings.
- Modificar un campo de un trámite en el JSON (ej. el costo) y volver a correr
  el pipeline cierra la versión anterior y crea una nueva, conservando la
  anterior con su `vigente_hasta` seteado.
- Un trámite sin `preguntas_frecuentes` en el JSON de entrada termina con FAQs
  generadas automáticamente y `faq_generadas_automaticamente: true`.
