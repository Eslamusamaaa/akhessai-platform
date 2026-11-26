"""RAG corpus / ingestion / retrieval tests. Run from backend/:

    python -m pytest rag/test_rag.py
    TEST_RAG_DATABASE_URL=postgresql://... python -m pytest rag/test_rag.py   # + pgvector integration

Unit tests force the keyword embedder so they need no model download and no database.
Integration tests need a Postgres with pgvector and a loadable sentence-transformers model;
they use a throwaway table (rag_test_<pid>) and never touch rag_documents.
"""
import json
import os
import pathlib
import re

import pytest

from rag import db as ragdb
from rag import ingest as ragingest
from rag import pipeline
from rag import validate_corpus as vc
from rag.parity_check import main_query, sample_inputs
from rag import evaluate as ev
from rag import coverage_report as cov
from rag import dedup_check as dd
from rag import demand_report as dr

BACKEND = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def keyword_embedder(monkeypatch):
    monkeypatch.setattr(pipeline, "_st_checked", True)
    monkeypatch.setattr(pipeline, "_st_model", None)
    monkeypatch.setattr(pipeline, "_DOC_EMBEDDINGS_CACHE", {})


# ── Corpus file ────────────────────────────────────────────────────────────────

def test_corpus_has_all_120_legacy_docs():
    lines = [l for l in open(pipeline.CORPUS_PATH, encoding="utf-8") if l.strip()]
    recs = [json.loads(l) for l in lines]
    assert len(recs) == 120
    assert sorted(r["id"] for r in recs) == list(range(1, 121))
    assert len(pipeline.SEED_DOCUMENTS) == 120
    assert len({r["doc_key"] for r in recs}) == 120


def test_corpus_validates():
    valid, failures = vc.validate(vc.load_jsonl(pipeline.CORPUS_PATH))
    assert failures == []
    assert len(valid) == 120


def test_validator_rejects_bad_records():
    good = dict(pipeline.SEED_DOCUMENTS[0])
    cases = {
        "specialty_tag": "dyslexia",
        "domain_tag": "reading",
        "age_band": "3-5",
        "category": "research",
        "audience": "nurse",
        "content": "English only, no Arabic here",
    }
    for field, bad in cases.items():
        assert vc.check_record({**good, field: bad}), field
    assert vc.check_record({k: v for k, v in good.items() if k != "title"})
    _, failures = vc.validate([good, dict(good)])
    assert any("duplicate" in p for _, p in failures)


# ── Chunking ───────────────────────────────────────────────────────────────────

def test_short_text_is_one_unchanged_chunk():
    text = pipeline.SEED_DOCUMENTS[0]["content"]
    assert ragingest.chunk_text(text, lambda t: len(t.split())) == [text]


def test_long_text_is_chunked_with_overlap():
    sentences = [f"هذه الجملة رقم {i} عن التواصل الاجتماعي واللغة التعبيرية لدى الطفل." for i in range(120)]
    text = " ".join(sentences)
    count = lambda t: len(t.split())  # noqa: E731
    chunks = ragingest.chunk_text(text, count)
    assert len(chunks) > 1
    assert all(count(c) <= ragingest.CHUNK_TARGET_TOKENS + 15 for c in chunks)
    for a, b in zip(chunks, chunks[1:]):          # consecutive chunks share sentences
        assert ragingest.split_sentences(b)[0] in ragingest.split_sentences(a)
    covered = {s for c in chunks for s in ragingest.split_sentences(c)}
    assert covered == set(sentences)


def test_row_hash_is_stable_and_content_sensitive():
    rec = vc.load_jsonl(pipeline.CORPUS_PATH)[0]
    count = lambda t: len(t.split())  # noqa: E731
    h1 = ragingest.build_rows([rec], "m", count)[0]["content_hash"]
    h2 = ragingest.build_rows([dict(rec)], "m", count)[0]["content_hash"]
    h3 = ragingest.build_rows([{**rec, "content": rec["content"] + " ."}], "m", count)[0]["content_hash"]
    assert h1 == h2 != h3


# ── In-memory retrieval (unchanged behaviour) ──────────────────────────────────

RESULT_KEYS = {"id", "title", "specialty_tag", "domain_tag", "age_band", "category", "content", "score"}


def test_in_memory_search_shape_filters_and_boost(keyword_embedder):
    client = pipeline.VectorStoreClient()
    docs = client._search_in_memory(["autism"], [], "0-6", "أهداف وتوصيات وخطط علاجية لـ autism", 6)
    assert len(docs) == 6
    assert all(set(d) == RESULT_KEYS for d in docs)
    assert all(d["specialty_tag"] == "autism" and d["age_band"] in ("0-6", "any") for d in docs)
    assert [d["score"] for d in docs] == sorted((d["score"] for d in docs), reverse=True)

    only = client._search_in_memory(["adhd"], ["attention"], "6-18", "انتباه", 50)
    assert only and all(d["domain_tag"] == "attention" for d in only)
    assert client._search_in_memory([], [], "0-6", "x", 6) == []


def test_non_postgres_url_selects_memory_store(monkeypatch):
    monkeypatch.setattr(pipeline.settings, "RAG_DATABASE_URL", "sqlite:///x.db")
    monkeypatch.setattr(pipeline.settings, "RAG_STORE", "pgvector")
    assert pipeline.VectorStoreClient().store == "memory"


def test_pgvector_failure_falls_back_to_memory(keyword_embedder, monkeypatch):
    client = pipeline.VectorStoreClient()
    client.store = "pgvector"

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(client, "_search_pgvector", boom)
    docs = client.search_guidelines(["autism"], [], "0-6", "تواصل", 6)
    assert len(docs) == 6 and all(set(d) == RESULT_KEYS for d in docs)


# ── Safety: nothing drops or wipes the vector table ────────────────────────────

def test_no_code_path_drops_or_deletes_rag_documents():
    pattern = re.compile(r"\b(DROP\s+TABLE|TRUNCATE|DELETE\s+FROM)\b", re.I)
    for path in list((BACKEND / "rag").glob("*.py")) + [BACKEND / "rag" / "schema.sql", BACKEND / "seed.py"]:
        if path.name == "test_rag.py":
            continue
        assert not pattern.search(path.read_text(encoding="utf-8")), path


def test_render_schema_substitutes_table_and_dim():
    sql = ragdb.render_schema("rag_bake_e5", 384)
    assert "VECTOR(384)" in sql and "rag_documents" not in sql and "rag_bake_e5_tsv" in sql
    with pytest.raises(ValueError):
        ragdb.render_schema("x; DROP TABLE y", 384)


# ── pgvector integration (opt-in) ──────────────────────────────────────────────

PG_URL = os.getenv("TEST_RAG_DATABASE_URL")
needs_pg = pytest.mark.skipif(not PG_URL, reason="set TEST_RAG_DATABASE_URL to a Postgres with pgvector")


@pytest.fixture
def pg_table(monkeypatch):
    if not pipeline.semantic_model_available():
        pytest.skip("no sentence-transformers model available")
    table = f"rag_test_{os.getpid()}"
    monkeypatch.setattr(pipeline.settings, "RAG_DATABASE_URL", PG_URL)
    monkeypatch.setattr(pipeline.settings, "RAG_TABLE", table)
    monkeypatch.setattr(ragdb, "_pool", None)
    yield table
    conn = ragdb.connect(PG_URL)  # test-only cleanup of the throwaway table
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {ragdb.safe_table(table)}")
    conn.commit()
    conn.close()
    monkeypatch.setattr(ragdb, "_pool", None)


@needs_pg
def test_ingest_is_idempotent_and_matches_memory(pg_table):
    first = ragingest.ingest(pipeline.CORPUS_PATH, pg_table, init_schema=True, url=PG_URL)
    assert first["inserted"] == 120
    second = ragingest.ingest(pipeline.CORPUS_PATH, pg_table, url=PG_URL)
    assert second["inserted"] == second["updated"] == 0 and second["unchanged"] == 120

    client = pipeline.VectorStoreClient()
    assert client.store == "pgvector" and client.table == pg_table
    for c in sample_inputs():
        q = main_query(c["specialties"])
        pg = client._search_pgvector(c["specialties"], c["domains"], c["age_band"], q, 6)
        mem = client._search_in_memory(c["specialties"], c["domains"], c["age_band"], q, 6)
        assert [d["id"] for d in pg] == [d["id"] for d in mem], c
        assert all(set(d) == RESULT_KEYS for d in pg)


# ── Evaluation metrics ─────────────────────────────────────────────────────────

def test_eval_metrics_and_set_integrity():

    assert ev.score(["a", "b", "c"], ["c", "x"]) == {"recall": 0.5, "rr": 1 / 3}
    assert ev.score(["a"], ["x"]) == {"recall": 0.0, "rr": 0.0}
    keys = {d["doc_key"] for d in pipeline.SEED_DOCUMENTS}
    items = ev.load_eval()
    assert 40 <= len(items) <= 60
    assert all(set(e["relevant"]) <= keys and e["relevant"] for e in items)
    base = {"overall": {"recall@6": 0.8, "mrr": 0.8}, "by_kind": {"domain": {"recall@6": 0.9, "mrr": 0.9}}}
    cur = {"overall": {"recall@6": 0.8, "mrr": 0.8}, "by_kind": {"domain": {"recall@6": 0.85, "mrr": 0.9}}}
    assert ev.regressions(cur, base) == ["kind=domain recall@6: 0.8500 < baseline 0.9000"]


# ── Corpus tooling: validation, dedup, coverage, demand ────────────────────────

def _new_doc(**over):
    base = {
        "id": 9001, "doc_key": "autism-9001", "title": "عنوان تجريبي", "content": "نص عربي بلا أرقام عن التواصل",
        "specialty_tag": "autism", "domain_tag": "social_communication", "age_band": "0-6",
        "category": "strategy", "audience": "parent", "language": "ar", "dialect_examples": None,
        "source_name": "CDC", "source_url": "https://www.cdc.gov/act-early/milestones/index.html",
        "license": "US public domain (attribution)", "accessed_at": "2026-11-27", "legacy": False,
    }
    return {**base, **over}


def test_validator_source_and_number_rules():
    assert vc.check_record(_new_doc()) == []
    assert any("source_url" in e for e in vc.check_record(_new_doc(source_url=None)))
    assert any("accessed_at" in e for e in vc.check_record(_new_doc(accessed_at="yesterday")))
    unsourced_number = _new_doc(content="يصيب الاضطراب 7% من الأطفال", source_url=None)
    assert "contains a number but has no source_url" in vc.check_record(unsourced_number)
    legacy = {**_new_doc(source_url=None, source_name=None, license=None, accessed_at=None), "legacy": True,
              "content": "نسبة 5% بلا مصدر"}
    assert vc.check_record(legacy) == [] and vc.legacy_warnings([legacy]) == ["autism-9001"]


def test_validator_per_source_cap():
    docs = [_new_doc(id=9000 + i, doc_key=f"autism-{9000 + i}") for i in range(3)]
    docs += [_new_doc(id=9100 + i, doc_key=f"autism-{9100 + i}", source_url=f"https://example{i}.org/x")
             for i in range(17)]
    _, failures = vc.validate(docs)          # cdc.gov: 3/20 = 15% -> allowed
    assert not any("cap" in p for _, p in failures)
    docs.append(_new_doc(id=9999, doc_key="autism-9999"))
    _, failures = vc.validate(docs)          # cdc.gov: 4/21 = 19% -> over the cap
    assert any(k == "cdc.gov" and "cap" in p for k, p in failures)


def test_dedup_thresholds_with_given_vectors():
    import numpy as np
    recs = [_new_doc(id=1, doc_key="autism-0001"), _new_doc(id=2, doc_key="autism-0002"),
            _new_doc(id=3, doc_key="autism-0003")]
    a = np.array([1.0, 0.0, 0.0])
    near = np.array([0.95, (1 - 0.95 ** 2) ** 0.5, 0.0])        # cos 0.95 with a -> review
    dup = np.array([0.99, (1 - 0.99 ** 2) ** 0.5, 0.0])         # cos 0.99 with a -> reject newer
    rejects, review = dd.check(recs, vectors=np.stack([a, dup, np.array([0.0, 0.0, 1.0])]), resolved=set())
    assert [r["reject"] for r in rejects] == ["autism-0002"] and review == []
    rejects, review = dd.check(recs, vectors=np.stack([a, near, np.array([0.0, 0.0, 1.0])]), resolved=set())
    assert rejects == [] and [(r["a"], r["b"]) for r in review] == [("autism-0001", "autism-0002")]
    _, review = dd.check(recs, vectors=np.stack([a, near, np.array([0.0, 0.0, 1.0])]),
                         resolved={dd.pair_key("autism-0002", "autism-0001")})
    assert review == []


def test_dedup_flags_handmade_near_duplicate_with_real_model():
    if not pipeline.semantic_model_available():
        pytest.skip("no sentence-transformers model available")
    src = pipeline.SEED_DOCUMENTS[1]
    copy = {**src, "id": 999, "doc_key": "autism-999", "content": src["content"].replace("الطفل", "طفلك", 1)}
    rejects, review = dd.check([src, copy], resolved=set())
    assert rejects or review


def test_coverage_report_lists_known_gaps():
    recs, bank = vc.load_jsonl(pipeline.CORPUS_PATH), cov.load_bank()
    gap_cells = {(d, b, a) for (d, b, a), _, _ in cov.gaps(recs, bank)}
    for dom in ("receptive_language", "impulsivity", "hyperactivity", "articulation",
                "vestibular", "proprioceptive", "externalizing"):
        assert any(d == dom for d, _, _ in gap_cells), dom
    assert ("executive_function", "0-6", "parent") in gap_cells
    assert cov.dedicated_audience_counts(recs) == {"all": 120}   # no teacher/specialist docs yet


def test_demand_report_is_read_only_and_ranked():
    import hashlib
    paths = [cov.BANK_PATH, dr.RULES_PATH]
    before = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in paths]
    assert dr.main([]) == 0
    assert before == [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in paths]
    bank, triggers = cov.load_bank(), dr.load_triggers()
    dem = dr.demand(bank, triggers)
    assert dem["totals"]["informants"] == {"parent": 53, "teacher": 18, "specialist": 9}
    assert dem["totals"]["age_bands"] == {"0-6": 52, "6-18": 75}
    assert dem["per_specialty"]["autism"] == 20
    q = dr.writing_queue(vc.load_jsonl(pipeline.CORPUS_PATH), bank, triggers)
    assert [c["questions"] for c in q] == sorted((c["questions"] for c in q), reverse=True)
