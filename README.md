# Macacha — Núcleo de datos

Asistente virtual de trámites de la administración pública de la Provincia de Salta.
Este repositorio contiene, por ahora, el núcleo de datos: esquema Postgres+pgvector
con versionado de trámites y el pipeline de ingesta.

## Requisitos

- Docker y Docker Compose
- Python 3.11+
- Una API key de OpenAI

## Puesta en marcha

1. Copiar `.env.example` a `.env` y completar `OPENAI_API_KEY`.
2. Levantar Postgres: `docker compose up -d postgres`
3. Instalar dependencias: `cd backend && pip install -r requirements.txt`
4. Correr los tests: `pytest`

Nota: si más adelante se modifica `backend/db/schema.sql`, el volumen nombrado de
Docker conserva el esquema viejo hasta que se recrea — hace falta `docker compose
down -v` antes de volver a levantar el servicio, no alcanza con reiniciar el
contenedor.

## Ingesta de trámites

```bash
cd backend
python -m ingest.load /ruta/al/archivo_de_tramites.json
```

El `.env` se carga automáticamente (el CLI llama a `load_dotenv()` internamente),
no hace falta exportar las variables a mano.

El comando es idempotente: si se vuelve a correr con el mismo contenido, no genera
nuevas versiones ni vuelve a llamar a la API de embeddings. Si algún campo de un
trámite cambió, cierra la versión vigente anterior y crea una nueva.
