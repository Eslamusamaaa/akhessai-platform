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
