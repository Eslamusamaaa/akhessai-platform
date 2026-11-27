# RAG data

Everything the retrieval system knows lives here, as versioned data — no code.

```
rag_data/
├── documents/
│   └── corpus.jsonl          # the guideline corpus: one Arabic document per line (text + metadata)
└── embeddings/
    └── <embedding tag>.jsonl # one vector per document chunk, written by `python -m rag.ingest`
```

## `documents/corpus.jsonl` — the text (no vectors)

One JSON object per line. Fields:

| Field | Meaning |
|---|---|
| `id`, `doc_key` | numeric id (returned to callers) and stable key, `<specialty>-NNN` |
| `title`, `content` | Arabic (MSA) text; example utterances may be Gulf or Egyptian (`dialect_examples`) |
| `specialty_tag` | autism, speech_language, adhd, learning_disabilities, sensory_processing, behavior_emotional |
| `domain_tag` | one of the 17 question-bank domains |
| `age_band` | `0-6`, `6-18` or `any` |
| `category` | glossary, strategy, goals, referral |
| `audience` | parent, teacher, specialist, all |
| `source_name`, `source_url`, `license`, `accessed_at` | where every fact comes from (required for every non-legacy doc) |
| `legacy` | `true` for the original 120 documents (sources still to be added) |

Every new document is written as original Arabic from a source read live on `accessed_at`;
any number in it must come from that source. Before a document is added it must pass
`python -m rag.validate_corpus` (schema, sources, 15% per-source cap), `python -m rag.dedup_check`
(no near-duplicates) and `python -m rag.evaluate --check` (retrieval quality).

## `embeddings/<tag>.jsonl` — the vectors

Written by `python -m rag.ingest` from what was stored in Postgres, so it always matches the
`rag_documents` table. The tag is the embedding provider and model, e.g.
`openrouter_baai_bge-m3.jsonl` for `openrouter:baai/bge-m3` (1024 dims, L2-normalised, rounded to
6 decimals). Each line: `doc_key`, `chunk_index`, `embedding_model`, `content_hash`, `embedding`.

The production search reads vectors from Neon (pgvector). This file is the versioned copy, and the
in-memory fallback uses it so it never has to re-embed the whole corpus through the API.

## Updating

```bash
cd backend
python -m rag.ingest --init-schema   # validate, dedup, embed changed docs, upsert to Neon, re-export vectors
python -m rag.coverage_report        # what is still thin
python -m rag.demand_report          # ranked writing queue from the question bank
```
