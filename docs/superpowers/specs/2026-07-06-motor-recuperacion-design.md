# Macacha — Motor de recuperación (búsqueda híbrida + re-ranking)

## Contexto general del sistema

Este es el **segundo** de los cuatro subsistemas de Macacha, el asistente virtual
de trámites de la administración pública de la Provincia de Salta:

1. **Núcleo de datos** (implementado): esquema Postgres+pgvector con versionado
   de trámites y pipeline de ingesta. Produce `tramite_chunks` con embeddings
   (`vector(1536)`, `text-embedding-3-small`) y una columna `tsv` (tsvector en
   español) generada automáticamente, filtrables siempre por
   `tramite_versiones.es_vigente = true`.
2. **Motor de recuperación** (este documento): búsqueda híbrida (vectorial +
   full-text search) fusionada con Reciprocal Rank Fusion (RRF), y re-ranking
   final vía LLM.
3. **Agente conversacional** (próxima etapa): tool-calling nativo de OpenAI,
   con herramientas separadas (buscar trámite, requisitos, costos/modalidad,
   pasos, normativa, formularios/enlaces, problemas frecuentes) que usan este
   motor de recuperación como su función de búsqueda subyacente. Orquestado en
   FastAPI, con historial de conversación persistente en Postgres.
4. **Frontend** (última etapa): chat en Next.js + Tailwind con streaming SSE.

Este documento cubre **solo el subsistema 2**. No introduce FastAPI ni ningún
servicio HTTP: es una librería Python pura, invocada en proceso, que el
subsistema 3 usará desde sus herramientas del agente.

## Alcance

Un módulo `backend/retrieval/` que expone una única función pública,
`buscar_chunks`, capaz de:

1. Buscar por similitud vectorial (coseno) en `tramite_chunks.embedding`.
2. Buscar por texto completo en `tramite_chunks.tsv` (español).
3. Fusionar ambos rankings con Reciprocal Rank Fusion (RRF), sin necesidad de
   normalizar o comparar escalas de score incompatibles entre sí.
4. Re-ordenar los candidatos fusionados con un modelo de lenguaje (re-ranking),
   devolviendo únicamente los `top_k` fragmentos finales.

Todas las consultas filtran siempre por `tramite_versiones.es_vigente = true`
(vía `JOIN`), de modo que solo se recuperan fragmentos de la versión vigente
de cada trámite — el historial de versiones queda excluido de la búsqueda,
consistente con el diseño del núcleo de datos.

## Estructura de archivos

```
backend/retrieval/
  __init__.py
  vector_search.py     # búsqueda por similitud coseno
  fulltext_search.py   # búsqueda de texto completo (FTS)
  fusion.py            # fusión RRF de ambos rankings
  hybrid_search.py      # orquestación: buscar_chunks()
```

Se extiende también `backend/ingest/openai_client.py` (la clase `OpenAIClient`
ya existente, usada para embeddings y generación de FAQs) con un tercer
método, `rerank`, para mantener un único cliente OpenAI inyectable en todo el
backend en vez de duplicar la lógica de construcción del cliente real.

## Forma de los resultados

Todas las funciones de búsqueda (vectorial, textual, fusión, y el resultado
final de `buscar_chunks`) devuelven una lista de dicts con esta forma:

```python
{
    "chunk_id": str,        # uuid del chunk, como string
    "tramite_id": str,       # ej. "RC-0001"
    "nombre_oficial": str,
    "categoria": str,
    "organismo": str,
    "tipo_chunk": str,       # descripcion/requisitos/pasos/costo_modalidad/problemas_frecuentes/faq/enlaces_oficiales
    "texto": str,
    "fuente_url": str | None,
}
```

## Componentes

### `vector_search.buscar_por_similitud(conn, query_embedding: list[float], top_n: int = 20) -> list[dict]`

```sql
SELECT tc.id, t.id AS tramite_id, t.nombre_oficial, t.categoria, o.nombre AS organismo,
       tc.tipo_chunk, tc.texto, tc.fuente_url
FROM tramite_chunks tc
JOIN tramite_versiones tv ON tv.id = tc.version_id AND tv.es_vigente = true
JOIN tramites t ON t.id = tv.tramite_id
JOIN organismos o ON o.id = t.organismo_id
ORDER BY tc.embedding <=> %s
LIMIT %s
```

Ordena por distancia coseno (`<=>`, operador de pgvector) ascendente (menor
distancia = más similar). `query_embedding` ya viene calculado por el llamador
(no genera el embedding internamente — eso es responsabilidad de `embed_fn`,
inyectado por quien orquesta la búsqueda). La fila resultante se mapea 1:1 a
la forma de resultado especificada arriba (`chunk_id`, `tramite_id`,
`nombre_oficial`, `categoria`, `organismo`, `tipo_chunk`, `texto`,
`fuente_url`).

### `fulltext_search.buscar_por_texto(conn, query: str, top_n: int = 20) -> list[dict]`

```sql
SELECT tc.id, t.id AS tramite_id, t.nombre_oficial, t.categoria, o.nombre AS organismo,
       tc.tipo_chunk, tc.texto, tc.fuente_url
FROM tramite_chunks tc
JOIN tramite_versiones tv ON tv.id = tc.version_id AND tv.es_vigente = true
JOIN tramites t ON t.id = tv.tramite_id
JOIN organismos o ON o.id = t.organismo_id
WHERE tc.tsv @@ websearch_to_tsquery('spanish', %s)
ORDER BY ts_rank(tc.tsv, websearch_to_tsquery('spanish', %s)) DESC
LIMIT %s
```

`websearch_to_tsquery` interpreta la consulta en lenguaje natural (soporta
frases entre comillas, `-` para exclusión, etc.), apropiado para preguntas de
usuario reales en vez de sintaxis de operadores de `to_tsquery`.

### `fusion.fusionar_rrf(ranking_vectorial: list[dict], ranking_textual: list[dict], k: int = 60) -> list[dict]`

Reciprocal Rank Fusion: cada chunk recibe un score
`1 / (k + posición_en_ranking)` por cada ranking en el que aparece (posición
1-indexada), sumando sus scores si aparece en ambos. `k=60` es la constante
estándar de la literatura de RRF (suaviza el peso de las posiciones más
bajas). El resultado es la lista de chunks (deduplicados por `chunk_id`)
ordenada por score RRF descendente. No requiere normalizar similitud coseno
contra `ts_rank` — RRF solo usa la posición ordinal en cada ranking, nunca el
valor de score original.

### `hybrid_search.buscar_chunks(query: str, conn, embed_fn, rerank_fn, top_k: int = 5) -> list[dict]`

1. `query_embedding = embed_fn([query])[0]` (reutiliza
   `OpenAIClient.generate_embeddings`, ya existente).
2. `ranking_vectorial = vector_search.buscar_por_similitud(conn, query_embedding, top_n=20)`.
3. `ranking_textual = fulltext_search.buscar_por_texto(conn, query, top_n=20)`.
4. `fusionados = fusion.fusionar_rrf(ranking_vectorial, ranking_textual)`.
5. `orden = rerank_fn(query, fusionados)` (reutiliza `OpenAIClient.rerank`,
   nuevo método — ver abajo). Devuelve una lista de índices sobre
   `fusionados`, ordenados por relevancia real a `query` según el LLM.
6. Reordena `fusionados` según `orden` y devuelve los primeros `top_k`.

### `OpenAIClient.rerank(self, query: str, candidatos: list[dict]) -> list[int]` (en `backend/ingest/openai_client.py`)

Nuevo método de la clase ya existente (mismo patrón que `generate_faqs`):
arma un prompt con la pregunta del usuario y el texto de cada candidato
(numerados), le pide al modelo `gpt-4o-mini` que devuelva el orden de
relevancia como JSON (`response_format={"type": "json_object"}`,
`{"orden": [2, 0, 4, 1, 3]}`), y devuelve `data["orden"]` como
`list[int]` (índices 0-based sobre `candidatos`, en el orden nuevo).

## Testing

Todos los tests son de integración contra el Postgres real (fixtures
`db_conn`/`clean_db` ya existentes en `backend/tests/conftest.py`), sin
llamadas reales a OpenAI:

- **`vector_search`**: insertar manualmente 3-4 chunks con embeddings de
  prueba fijos (vectores de baja dimensión conceptual, ej. variaciones de
  `[1,0,0,...]` vs `[0,1,0,...]`) y verificar que `buscar_por_similitud`
  devuelve el orden esperado por cercanía coseno a un vector de consulta
  conocido.
- **`fulltext_search`**: insertar chunks con texto real en español y verificar
  que una consulta en lenguaje natural devuelve los chunks relevantes en el
  orden esperado por `ts_rank`.
- **`fusion`**: probar `fusionar_rrf` con rankings sintéticos simples (listas
  de dicts con `chunk_id` fijos), verificando el cálculo de score y el orden
  resultante — sin necesidad de Postgres.
- **`hybrid_search`**: test de integración con `embed_fn` y `rerank_fn` falsos
  (inyectados), insertando chunks reales en Postgres y verificando que
  `buscar_chunks` devuelve exactamente `top_k` resultados con la forma
  especificada, en el orden que dicta el `rerank_fn` falso.
- **`OpenAIClient.rerank`**: mismo patrón que los tests existentes de
  `generate_embeddings`/`generate_faqs` — fake SDK stub que devuelve una
  respuesta JSON fija, verificando que se parsea correctamente a
  `list[int]`.

No se agrega un CLI de prueba manual para este subsistema — la verificación
end-to-end con datos reales queda para cuando el agente (subsistema 3) lo
consuma a través de sus herramientas.

## Fuera de alcance de este documento

- Cualquier endpoint HTTP o servicio FastAPI (llega con el subsistema 3).
- Las herramientas del agente (buscar trámite, requisitos, costos, normativa,
  formularios, problemas frecuentes) — este motor es la función de búsqueda
  subyacente que esas herramientas van a invocar, pero las herramientas en sí
  se diseñan en el subsistema 3.
- Sesiones de chat, historial de conversación, streaming.
- Frontend.
- Despliegue a producción / CI-CD.

## Criterios de aceptación

- `buscar_chunks("cómo saco un acta de nacimiento", conn, embed_fn_real, rerank_fn_real)`
  contra los 32 trámites reales del núcleo de datos devuelve como primer
  resultado un chunk perteneciente a un trámite de la categoría "Actas" o
  "Nacimiento" (verificación manual, no automatizada, cuando el subsistema 3
  integre este motor).
- Todos los tests automatizados (contra Postgres real, sin red a OpenAI)
  pasan de forma determinística y repetible.
- Ningún test ni código de este subsistema hace una llamada real a la API de
  OpenAI.
