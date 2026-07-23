CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS organismos (
    id SERIAL PRIMARY KEY,
    nombre TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS tramites (
    id TEXT PRIMARY KEY,
    organismo_id INTEGER NOT NULL REFERENCES organismos(id),
    categoria TEXT NOT NULL,
    nombre_oficial TEXT NOT NULL,
    veces_consultado INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tramite_versiones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tramite_id TEXT NOT NULL REFERENCES tramites(id),
    numero_version INTEGER NOT NULL,
    es_vigente BOOLEAN NOT NULL DEFAULT true,
    vigente_desde TIMESTAMPTZ NOT NULL DEFAULT now(),
    vigente_hasta TIMESTAMPTZ,
    content_hash TEXT NOT NULL,
    snapshot JSONB NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS tramite_versiones_vigente_unica
    ON tramite_versiones (tramite_id)
    WHERE es_vigente = true;

CREATE TABLE IF NOT EXISTS tramite_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL REFERENCES tramite_versiones(id),
    tipo_chunk TEXT NOT NULL,
    texto TEXT NOT NULL,
    fuente_url TEXT,
    embedding vector(1536),
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED
);

CREATE INDEX IF NOT EXISTS tramite_chunks_version_idx ON tramite_chunks (version_id);
CREATE INDEX IF NOT EXISTS tramite_chunks_tsv_idx ON tramite_chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS tramite_chunks_embedding_idx ON tramite_chunks
    USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS sesiones (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mensajes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    orden BIGSERIAL,
    session_id UUID NOT NULL REFERENCES sesiones(id),
    rol TEXT NOT NULL,
    contenido TEXT,
    tool_calls JSONB,
    tool_call_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE mensajes ADD COLUMN IF NOT EXISTS orden BIGSERIAL;

ALTER TABLE tramites ADD COLUMN IF NOT EXISTS veces_consultado INTEGER NOT NULL DEFAULT 0;

DROP INDEX IF EXISTS mensajes_session_idx;
CREATE INDEX IF NOT EXISTS mensajes_session_orden_idx ON mensajes (session_id, orden);
