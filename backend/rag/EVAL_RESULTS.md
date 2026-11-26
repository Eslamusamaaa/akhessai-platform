# RAG retrieval bake-off — embedding models

Date: 2026-11-27 · Corpus: the 120 legacy documents (`rag/corpus.jsonl`) · Eval set: 48 Arabic
queries (`rag/eval_set.jsonl`) · Metric: Recall@6 and MRR through the shipped
`search_guidelines` path (metadata filter + cosine + 0.05 goals/strategy boost), on a local
Postgres 16 + pgvector (Docker), same corpus and same SQL for every model.

Reproduce:

```bash
cd backend
EMBEDDING_MODEL=BAAI/bge-m3 RAG_TABLE=rag_bake_1024 python -m rag.ingest --init-schema
EMBEDDING_MODEL=BAAI/bge-m3 RAG_TABLE=rag_bake_1024 python -m rag.evaluate --similarity-only
```

## Overall

| Model | Dims | Recall@6 | MRR | Ingest 120 docs (CPU) |
|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 (current) | 384 | 0.8608 | 0.8507 | ~10 s |
| **BAAI/bge-m3** | 1024 | **0.9024** | **0.8819** | ~60 s |
| intfloat/multilingual-e5-large-instruct | 1024 | 0.8330 | 0.8514 | ~385 s |

## By query kind (Recall@6 / MRR)

| Kind | n | MiniLM | bge-m3 | e5-large-instruct |
|---|---|---|---|---|
| domain (clinician phrasing) | 21 | 0.957 / 0.976 | 0.965 / 0.976 | 0.928 / 0.921 |
| specialist observation | 9 | 0.917 / 0.861 | 0.907 / 0.778 | 0.787 / 0.698 |
| child profile (main.py query string) | 13 | 0.639 / 0.660 | **0.786 / 0.833** | 0.724 / 0.789 |
| dialect (Egyptian / Gulf) | 5 | 0.933 / 0.800 | 0.933 / 0.800 | 0.800 / 1.000 |

The child-profile slice is what production actually sends (the fixed query string in
`main.py`), and it is where bge-m3 gains most.

## By domain (Recall@6)

| Domain | n | MiniLM | bge-m3 | e5 |
|---|---|---|---|---|
| academic_skills | 6 | 0.669 | 0.839 | 0.531 |
| articulation | 5 | 0.933 | 1.000 | 1.000 |
| attention | 6 | 0.778 | 0.811 | 0.778 |
| emotional_regulation | 4 | 0.917 | 1.000 | 1.000 |
| executive_function | 3 | 0.611 | 0.678 | 0.667 |
| expressive_language | 4 | 0.875 | 0.938 | 0.792 |
| externalizing | 2 | 0.833 | 1.000 | 1.000 |
| hyperactivity | 2 | 1.000 | 1.000 | 1.000 |
| impulsivity | 2 | 1.000 | 1.000 | 1.000 |
| internalizing | 3 | 0.833 | 0.833 | 0.833 |
| pragmatic_language | 4 | 0.817 | 0.900 | 0.900 |
| proprioceptive | 2 | 1.000 | 1.000 | 1.000 |
| receptive_language | 2 | 0.750 | 0.875 | 0.875 |
| restricted_repetitive | 2 | 0.700 | 0.900 | 0.800 |
| sensory_reactivity | 3 | **0.800** | **0.733** | 0.733 |
| social_communication | 8 | 0.692 | 0.725 | 0.567 |
| vestibular | 2 | 1.000 | 1.000 | 1.000 |

## Per-query differences, MiniLM → bge-m3

- Better recall on 8 queries: dom_social_communication, dom_academic_skills, obs_q_learning_s01,
  prof_autism_0_6, prof_speech_0_6, prof_speech_6_18, prof_ld_6_18, prof_behavior_6_18
  (prof_adhd_ld_6_18 also improves recall 0.2 → 0.4).
- Worse recall on 2 queries: dom_sensory_reactivity (1.0 → 0.8, one doc of five drops out of the
  top 6) and obs_q_autism_s01 (1.0 → 0.67).
- Same recall but the first relevant doc moves from rank 1 to rank 2–3 on 7 queries
  (lower MRR on the specialist-observation slice).

## Filter-first vs similarity-only (measurement only)

Ranking all 120 documents with no metadata filter gives Recall@6 0.45 (MiniLM), 0.48 (bge-m3),
0.38 (e5): the shipped specialty / age-band / domain filters roughly double recall. The one
relevant document the filter can never reach in this set is `behavior_emotional-012`
(self-injury, tagged `externalizing`) for the internalizing self-harm observation query; the
new safety cluster adds internalizing-tagged crisis documents so that path is covered. The
shipped filter behaviour is unchanged.

## Gate and decision

The gate in the task is: the winner must meet or beat MiniLM on every domain slice, not only on
average.

- **e5-large-instruct: rejected.** Lower overall Recall@6 than MiniLM, and lower on
  academic_skills, social_communication, expressive_language and the specialist slice. It is also
  ~6x slower to embed on CPU and needs query instructions.
- **bge-m3: best overall** (+4.2 points Recall@6, +3.1 MRR; +14.7 points on the child-profile slice
  that production uses), better or equal on 16 of 17 domains, but **below MiniLM on
  sensory_reactivity** (0.733 vs 0.800, a single document in a single query) and slightly below on
  the specialist-observation slice. Strictly, it does not pass the every-slice gate.

Status: the switch is configuration-only (`EMBEDDING_MODEL`, `EMBEDDING_VERSION`), the default
stays MiniLM until the owner decides. The slices are small (2–8 queries), so they will be
re-measured after corpus batch 1; the decision is recorded here when made.

Operational note: bge-m3 is a 568M-parameter model (~2.2 GB of weights). It runs on CPU, but on
Vercel it lengthens cold starts and needs the large-function allowance; if that is a problem, the
optional standalone retrieval service from the plan is the fallback.
