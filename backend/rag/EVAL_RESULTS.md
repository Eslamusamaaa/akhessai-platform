# RAG retrieval bake-off — embedding models

Date: 2026-11-27 · Corpus: the 120 legacy documents (`rag_data/documents/corpus.jsonl`) · Eval set: 48 Arabic
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

## Corpus batch 1 (160 docs) — accepted small regression

Batch 1 adds 40 sourced documents (safety cluster, 0-6 gaps, first teacher/specialist
documents). Eval labels were extended only where a new document directly answers the query,
and Recall@6 now counts only labelled docs present in the corpus with the denominator capped
at 6.

| Model | Recall@6 (120 docs) | Recall@6 (160 docs) | MRR (120) | MRR (160) |
|---|---|---|---|---|
| MiniLM (default) | 0.8608 | 0.8378 | 0.8507 | **0.8924** |
| bge-m3 | 0.9024 | 0.8583 | 0.8819 | 0.8715 |

Recall@6 dropped 2.3 points with MiniLM (MRR rose 4.2 points): a few broad new documents
(mainly autism-035, the diagnosis overview) outrank more specific legacy ones on 4 queries.
The owner accepted this regression on 2026-11-27 in exchange for the new coverage, and
`eval_baseline.json` was re-recorded at 160 docs; later batches are gated against it.

## Corpus batch 2 (190 docs)

Batch 2 adds 30 sourced documents (NICHD learning disabilities, NIMH warning signs and ADHD,
CDC ADHD presentations and movement milestones, NIDCD autism communication, AAP sensory
integration). Labels extended only where a new document directly answers the query.

| Model | Recall@6 (160) | Recall@6 (190) | MRR (160) | MRR (190) |
|---|---|---|---|---|
| MiniLM (default) | 0.8378 | 0.8208 | 0.8924 | **0.9184** |
| bge-m3 | 0.8583 | 0.8566 | 0.8715 | 0.9028 |

Recall@6 dipped 1.7 points with MiniLM while MRR rose 2.6 points; accepted under the owner's
"accept small regressions" decision of 2026-11-27, baseline re-recorded at 190 docs.

## Decision: bge-m3 through the OpenRouter API (2026-11-27)

The owner chose bge-m3 and asked to drop in-process models from the Vercel function. Production
now embeds with `baai/bge-m3` via the OpenRouter embeddings API (`EMBEDDING_PROVIDER=openrouter`,
tag `openrouter:baai/bge-m3`); `sentence-transformers` and `torch` moved to
`requirements-local.txt` for offline experiments only.

Measured on Neon (production branch, pgvector) after loading 190 documents with
`openrouter:baai/bge-m3`: Recall@6 0.8566, MRR 0.9010 (MiniLM on the same corpus: 0.8208 / 0.9184).
OpenRouter's bge-m3 vectors match local BAAI/bge-m3 (cosine 1.000 on test sentences); parity
pgvector vs in-memory 52/52. `eval_baseline.json` re-recorded for this model.

## Corpus batch 3 (217 docs)

27 Arabic documents from live sources read 2026-11-27: NIMH autism publication (older children, screening schedule, family tips) and ADHD in children and teens (symptoms, diagnosis requirements, school supports, treatment options); ASHA Practice Portal speech sound disorders (incl. dialect is not a disorder) and spoken language disorders (school-age comprehension, assessment of bilingual/dialect speakers, language screening in behavior referrals). Eval (openrouter:baai/bge-m3, labels extended only where a new document directly
answers the query): `overall n=48 Recall@6=0.8517 MRR=0.9115`. Baseline re-recorded. Coverage: Gap list (37 touched cells under 8 docs; questions, docs). Dedicated audience docs: all=123 (57%), parent=48 (22%), specialist=21 (10%), teacher=25 (12%).

## Corpus batch 4 (232 docs)

15 Arabic documents from live sources read 2026-11-27: Berkshire Healthcare NHS FT vestibular and proprioception guidance (signs, home and classroom movement / heavy-work activities), AAP temper tantrums (why, prevention, during a tantrum), CDC preschool parenting and safety, NIMH anxiety disorders. Eval (openrouter:baai/bge-m3, labels extended only where a new document directly
answers the query): `overall n=48 Recall@6=0.8434 MRR=0.9010`. Baseline re-recorded. Coverage: Gap list (37 touched cells under 8 docs; questions, docs). Dedicated audience docs: all=124 (53%), parent=59 (25%), specialist=21 (9%), teacher=28 (12%).

## Precision@6 — what the report actually receives

Recall@6 is computed against relevance labels that keep growing as relevant documents are added,
so it can fall even when the top 6 get better (a query that had 4 relevant docs, all retrieved,
scores 1.0; after 3 more relevant docs are added, retrieving 5 of 7 scores 0.83). Precision@6
(relevant docs among the 6 returned) measures what the report generator receives. Same eval set,
openrouter:baai/bge-m3, labels as of batch 5:

| Corpus | Recall@6 | MRR | Precision@6 |
|---|---|---|---|
| 120 (legacy) | 0.902 | 0.882 | 0.497 |
| 160 | 0.866 | 0.872 | 0.569 |
| 190 | 0.857 | 0.903 | 0.622 |
| 217 | 0.852 | 0.912 | 0.649 |
| 232 | 0.842 | 0.903 | 0.660 |
| 248 | 0.815 | 0.901 | 0.667 |

Real regressions seen in batch 5 (a new, less relevant document outranking a relevant one): the
cluttering document in stuttering/articulation queries, the teacher depression document in the
anxiety query, and the typical-disfluency document in the intelligibility observation query.

## Corpus batch 5 (248 docs)

16 Arabic documents from live sources read 2026-11-27: ASHA childhood apraxia of speech and fluency disorders (stuttering, cluttering; parents, teachers, specialists), NIMH teen depression, WHO autism fact sheet (co-occurring conditions, causes and vaccines, caregiver training). Adds Precision@6 to evaluate.py (relevant docs among the 6 the report receives: 0.497 at 120 docs -> 0.667 at 248). Eval (openrouter:baai/bge-m3, labels extended only where a new document directly
answers the query): `overall n=48 Recall@6=0.8132 MRR=0.9010 Precision@6=0.6667`. Baseline re-recorded. Coverage: Gap list (37 touched cells under 8 docs; questions, docs). Dedicated audience docs: all=124 (50%), parent=68 (27%), specialist=26 (10%), teacher=30 (12%).

## Corpus batch 6 (260 docs)

12 Arabic documents from live sources read 2026-11-27: NHS ADHD living-with advice (day planning, instructions, rewards, diet and sleep, school SENCO), NHS autism help with behaviour (routines, change, stimming, meltdowns, where to get help), Berkshire Healthcare NHS FT touch/tactile system (signs, home and classroom strategies), CDC bullying (definition, forms, consequences, school prevention, family role). Eval (openrouter:baai/bge-m3, labels extended only where a new document directly
answers the query): `overall n=48 Recall@6=0.8090 MRR=0.9010 Precision@6=0.6701`. Baseline re-recorded. Coverage: Gap list (34 touched cells under 8 docs; questions, docs). Dedicated audience docs: all=124 (48%), parent=76 (29%), specialist=26 (10%), teacher=34 (13%).

## Corpus batch 7 (274 docs)

14 Arabic documents from live NHS pages read 2026-11-27: dyslexia (signs, assessment pathway, school and home support), selective mutism (what it is, parents' do's and don'ts, early-years staff, diagnosis and graded-exposure treatment, school-age difficulties), anxiety in children (signs by age, separation anxiety and common fears, triggers, home tools, school supports, anger as an anxiety sign). Eval (openrouter:baai/bge-m3, labels extended only where a new document directly
answers the query): `overall n=48 Recall@6=0.8063 MRR=0.9010 Precision@6=0.6771`. Baseline re-recorded. Coverage: Gap list (33 touched cells under 8 docs; questions, docs). Dedicated audience docs: all=124 (45%), parent=85 (31%), specialist=27 (10%), teacher=38 (14%).

## Corpus batch 8 (288 docs)

14 Arabic documents from live sources read 2026-11-27: NHS signs of autism in children (communication, behaviour and play, sensory and eating differences, older children, masking in girls), NHS temper tantrums (why toddlers hit or bite, nursery strategies, common mistakes), Child Mind Institute teacher's guide to ADHD (boys vs girls, daily report card, transitions), language disorder quick guide (signs, home talk, classroom tips) and auditory processing strategies. Eval (openrouter:baai/bge-m3, labels extended only where a new document directly
answers the query): `overall n=48 Recall@6=0.8076 MRR=0.9219 Precision@6=0.6875`. Baseline re-recorded. Coverage: Gap list (29 touched cells under 8 docs; questions, docs). Dedicated audience docs: all=124 (43%), parent=93 (32%), specialist=28 (10%), teacher=43 (15%).
