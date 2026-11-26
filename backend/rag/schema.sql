-- RAG guideline store: Neon Postgres + pgvector.
-- Run once per database (e.g. on a Neon branch):   psql "$RAG_DATABASE_URL" -f rag/schema.sql
-- or let the ingestion script create it:             python -m rag.ingest --init-schema
--
-- The embedding dimension is tied to the active model: 1024 for BAAI/bge-m3 and
-- intfloat/multilingual-e5-large-instruct, 384 for paraphrase-multilingual-MiniLM-L12-v2.
-- Vectors are never padded. `python -m rag.ingest --init-schema` renders this file with the
-- active model's dimension (and, with --table, a separate table name for bake-offs).
-- Rows are tagged with the model that produced them (embedding_model), so re-embedding with
-- a new model inserts new rows next to the old ones; nothing here ever deletes or drops.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id               BIGSERIAL PRIMARY KEY,
    doc_key          TEXT NOT NULL,
    doc_id           INT  NOT NULL,                -- numeric corpus id (returned to callers as "id")
    chunk_index      INT  NOT NULL DEFAULT 0,
    title            TEXT NOT NULL,
    content          TEXT NOT NULL,
    specialty_tag    TEXT NOT NULL,
    domain_tag       TEXT NOT NULL,
    age_band         TEXT NOT NULL,                -- '0-6' | '6-18' | 'any'
    category         TEXT NOT NULL,                -- glossary|strategy|goals|referral
    audience         TEXT NOT NULL DEFAULT 'all',  -- parent|teacher|specialist|all
    language         TEXT NOT NULL DEFAULT 'ar',
    dialect_examples TEXT,                         -- msa|egy|gulf|null
    source_name      TEXT,
    source_url       TEXT,
    license          TEXT,
    accessed_at      DATE,
    legacy           BOOLEAN NOT NULL DEFAULT false,
    content_hash     TEXT NOT NULL,                -- sha256 of the record; unchanged hash = no-op upsert
    embedding_model  TEXT NOT NULL,
    embedding        VECTOR(1024) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_key, chunk_index, embedding_model)
);

CREATE INDEX IF NOT EXISTS rag_documents_hnsw ON rag_documents
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS rag_docs_filters
    ON rag_documents (specialty_tag, age_band, domain_tag);

ALTER TABLE rag_documents
    ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('arabic', title || ' ' || content)) STORED;
CREATE INDEX IF NOT EXISTS rag_docs_tsv ON rag_documents USING gin (tsv);
