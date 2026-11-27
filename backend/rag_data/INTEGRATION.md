# Integrating the evaluator + RAG into another backend (C#/.NET, Flutter)

Everything needed to run the assessment → retrieval → report flow outside this Python service.
Nothing below depends on Vercel; all AI calls are plain HTTPS to OpenRouter.

## 1. What to copy

| Piece | Files | Notes |
|---|---|---|
| Questions | `backend/questions/bank.json` | 80 questions, options with `points`, `domain_tags`, `specialty_tags`, `informant`, `age_bands` |
| Scoring rules | `backend/rules/rules_config.yaml` | specialty triggers, severity bands, discrepancy and priority config |
| Scoring algorithm | `backend/rules/evaluator.py` | `evaluate_rules()`; port it (pure logic, ~300 lines) |
| Question order | `backend/questions/resolver.py` | `get_next_question()`; port it |
| Documents | `backend/rag_data/documents/corpus.jsonl` | one Arabic document per line (see `README.md` here) |
| Vectors | `backend/rag_data/embeddings/openrouter_baai_bge-m3.jsonl` | 1024-dim, L2-normalised, one per `doc_key` (+ `chunk_index`) |
| Report prompt | `backend/llm/client.py` | `_SYSTEM_TEMPLATE`, `build_prompt()`, JSON output keys |

## 2. Keys and models

| Purpose | Endpoint | Model |
|---|---|---|
| Embeddings | `POST https://openrouter.ai/api/v1/embeddings` | `baai/bge-m3` |
| Report LLM | `POST https://openrouter.ai/api/v1/chat/completions` | `google/gemini-2.5-flash` (`response_format: json_object`, `temperature: 0.15`) |

Both use the same OpenRouter key: `Authorization: Bearer <OPENROUTER_API_KEY>`.
Keep the key on the server; never ship it inside the Flutter app.

Embedding request / response:

```json
POST /api/v1/embeddings
{ "model": "baai/bge-m3", "input": ["أهداف وتوصيات وخطط علاجية لـ autism"] }

{ "data": [ { "index": 0, "embedding": [0.0123, -0.0456, ...] } ] }   // 1024 floats
```

L2-normalise the returned vector (divide by its length). The stored document vectors are already
normalised, so cosine similarity = dot product.

## 3. Retrieval algorithm (must stay identical)

Inputs come from the evaluator: `active_specialties`, `elevated_domains` (domains with severity
`level >= 3`), the session `age_band` (`0-6` / `6-18`), and the query text
`"أهداف وتوصيات وخطط علاجية لـ " + join(", ", active_specialties)`.

1. Keep documents where `specialty_tag ∈ active_specialties`, `age_band ∈ {age_band, "any"}`,
   and — only if `elevated_domains` is not empty — `domain_tag ∈ elevated_domains`.
2. `score = dot(query_vector, doc_vector) + (0.05 if category ∈ {goals, strategy} else 0)`.
3. Sort by score descending (ties: smaller `id` first) and take the top **6**.
4. Pass those 6 documents (title + content) to the report prompt as the reference guidelines.

With Postgres + pgvector, steps 1-3 are one query (see `backend/rag/pipeline.py`, `_VECTOR_SQL`):

```sql
SELECT doc_id, title, content, ...,
       (1 - (embedding <=> :q::vector)) + CASE WHEN category IN ('goals','strategy') THEN 0.05 ELSE 0 END AS score
FROM rag_documents
WHERE embedding_model = 'openrouter:baai/bge-m3'
  AND specialty_tag = ANY(:specialties)
  AND age_band IN (:age_band, 'any')
  AND (cardinality(:domains) = 0 OR domain_tag = ANY(:domains))
ORDER BY score DESC, doc_id
LIMIT 6;
```

Without a database, load `corpus.jsonl` + the embeddings file into memory and do the same in
code: ~1,000 documents × 1024 floats is a few MB and a brute-force scan takes milliseconds.

## 4. Hosting options

- **Postgres + pgvector (recommended):** run `backend/rag/schema.sql`, then load rows from the two
  files (join on `doc_key`). Or reuse the Python loader once: `python -m rag.ingest --init-schema`
  with `RAG_DATABASE_URL` pointing at your database.
- **In memory:** read both files at startup; no database needed.

When the corpus is updated in this repository, both files change together; re-load them (rows are
keyed by `doc_key` + `chunk_index`, so an upsert is enough).

## 5. Checking your port

`backend/rag/eval_set.jsonl` has 48 Arabic queries with the expected `doc_key`s. Run them through
your implementation and compare with `backend/rag/eval_baseline.json` (Recall@6 / MRR); the Python
reference is `python -m rag.evaluate`. `python -m rag.parity_check` shows the expected top-6 for
sample specialty / domain / age-band inputs.
