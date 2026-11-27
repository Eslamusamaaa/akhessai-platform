"""Load rag/corpus.jsonl into Postgres + pgvector (rag_documents). Offline only:
run it locally or in CI, never inside a request.

    cd backend
    python -m rag.ingest --init-schema        # create extension/table/indexes if missing, then load
    python -m rag.ingest                      # idempotent re-load: unchanged rows are skipped
    python -m rag.ingest --dry-run            # validate + chunk + report, touch nothing

Steps: validate -> chunk (> ~400 tokens) -> embed changed chunks with the active model
-> upsert ON CONFLICT (doc_key, chunk_index, embedding_model). There is no DELETE, DROP
or table wipe anywhere: re-running with an unchanged corpus reports 0 changed rows.
"""
import argparse
import collections
import hashlib
import json
import re
import sys
from typing import Any, Dict, List, Optional

from config import settings
from rag import db as ragdb
from rag import validate_corpus
from rag.pipeline import (CORPUS_PATH, _try_load_st, document_text, get_embedding_dim,
                          get_text_embeddings, semantic_model_available)

CHUNK_TRIGGER_TOKENS = 400   # documents longer than this are chunked
CHUNK_TARGET_TOKENS = 400    # chunks land in the 300-500 token range
CHUNK_OVERLAP = 0.15

META_FIELDS = ("specialty_tag", "domain_tag", "age_band", "category", "audience", "language",
               "dialect_examples", "source_name", "source_url", "license", "accessed_at",
               "legacy")
_SENTENCE_RE = re.compile(r"(?<=[\.!\?؟؛])\s+|\n+")


# ── Chunking ───────────────────────────────────────────────────────────────────

def _token_counter():
    """Token counter of the active model's tokenizer; whitespace words as a fallback."""
    model = _try_load_st()
    tok = getattr(model, "tokenizer", None) if model else None
    if tok is not None:
        return lambda text: len(tok.tokenize(text))
    return lambda text: len(text.split())


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s and s.strip()]


def chunk_text(text: str, count_tokens, target: int = CHUNK_TARGET_TOKENS,
               trigger: int = CHUNK_TRIGGER_TOKENS, overlap: float = CHUNK_OVERLAP) -> List[str]:
    """Split on Arabic sentence boundaries into ~target-token chunks with ~15% overlap.
    Text at or under `trigger` tokens is returned as a single chunk, unchanged."""
    if count_tokens(text) <= trigger:
        return [text]
    sentences = split_sentences(text)
    sizes = [count_tokens(s) for s in sentences]
    chunks, start = [], 0
    while start < len(sentences):
        end, total = start, 0
        while end < len(sentences) and (total + sizes[end] <= target or end == start):
            total += sizes[end]
            end += 1
        chunks.append(" ".join(sentences[start:end]))
        if end >= len(sentences):
            break
        # step back so the next chunk re-reads ~15% of this one
        back, kept = end, 0
        while back - 1 > start and kept + sizes[back - 1] <= overlap * total:
            back -= 1
            kept += sizes[back]
        start = back
    return chunks


# ── Rows ───────────────────────────────────────────────────────────────────────

def build_rows(records: List[Dict[str, Any]], embedding_model: str, count_tokens) -> List[Dict[str, Any]]:
    rows = []
    for rec in records:
        for idx, chunk in enumerate(chunk_text(rec["content"], count_tokens)):
            row = {
                "doc_key": rec["doc_key"], "doc_id": rec["id"], "chunk_index": idx,
                "title": rec["title"], "content": chunk,
                **{k: rec.get(k) for k in META_FIELDS},
                "embedding_model": embedding_model,
            }
            row["legacy"] = bool(row["legacy"])
            row["audience"] = row["audience"] or "all"
            row["language"] = row["language"] or "ar"
            row["content_hash"] = hashlib.sha256(
                json.dumps({k: row[k] for k in sorted(row)}, ensure_ascii=False, default=str).encode("utf-8")
            ).hexdigest()
            rows.append(row)
    return rows


_COLUMNS = ("doc_key", "doc_id", "chunk_index", "title", "content") + META_FIELDS + (
    "content_hash", "embedding_model", "embedding")

_UPSERT_SQL = """
INSERT INTO {table} ({cols})
VALUES ({vals})
ON CONFLICT (doc_key, chunk_index, embedding_model) DO UPDATE SET
    {updates}, updated_at = now()
WHERE {table}.content_hash IS DISTINCT FROM EXCLUDED.content_hash
RETURNING (xmax = 0) AS inserted
"""


def upsert_sql(table: str) -> str:
    vals = ", ".join("%({})s::vector".format(c) if c == "embedding" else "%({})s".format(c) for c in _COLUMNS)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS
                        if c not in ("doc_key", "chunk_index", "embedding_model"))
    return _UPSERT_SQL.format(table=ragdb.safe_table(table), cols=", ".join(_COLUMNS), vals=vals, updates=updates)


def existing_hashes(conn, table: str, embedding_model: str) -> Dict[tuple, str]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT doc_key, chunk_index, content_hash FROM {ragdb.safe_table(table)} "
                    "WHERE embedding_model = %s", (embedding_model,))
        return {(k, i): h for k, i, h in cur.fetchall()}


# ── Report ─────────────────────────────────────────────────────────────────────

def load_report(records: List[Dict[str, Any]]) -> str:
    """Counts per specialty x category x age_band x audience, to spot balance regressions."""
    counts = collections.Counter(
        (r["specialty_tag"], r["category"], r["age_band"], r.get("audience") or "all") for r in records)
    lines = [f"{'specialty':<22}{'category':<10}{'age':<6}{'audience':<11}docs"]
    lines += [f"{s:<22}{c:<10}{a:<6}{u:<11}{n}" for (s, c, a, u), n in sorted(counts.items())]
    for field in ("specialty_tag", "category", "age_band", "audience"):
        tot = collections.Counter(r.get(field) or "all" for r in records)
        lines.append(f"  by {field}: " + ", ".join(f"{k}={v}" for k, v in sorted(tot.items())))
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def ingest(corpus_path: str, table: str, init_schema: bool = False, dry_run: bool = False,
           batch_size: int = 32, url: Optional[str] = None) -> Dict[str, int]:
    records = validate_corpus.load_jsonl(corpus_path)
    valid, failures = validate_corpus.validate(records)
    for key, problem in failures:
        print(f"[ingest] REJECTED {key}: {problem}")

    if not dry_run and not semantic_model_available():
        raise SystemExit("[ingest] No sentence-transformers model could be loaded "
                         f"({settings.EMBEDDING_MODEL}); refusing to store keyword-fallback vectors.")
    model_tag = settings.EMBEDDING_VERSION
    rows = build_rows(valid, model_tag, _token_counter())
    print(f"[ingest] {len(records)} records, {len(valid)} valid, {len(failures)} rejected, "
          f"{len(rows)} chunks, model={model_tag}")
    print(load_report(valid))
    stats = {"records": len(records), "valid": len(valid), "rejected": len(failures),
             "chunks": len(rows), "inserted": 0, "updated": 0, "unchanged": 0}
    if dry_run:
        return stats

    dim = get_embedding_dim()
    conn = ragdb.connect(url)
    try:
        current_dim = ragdb.table_vector_dim(conn, table)
        if current_dim is None:
            if not init_schema:
                raise SystemExit(f"[ingest] Table {table} does not exist; run with --init-schema.")
            with conn.cursor() as cur:
                cur.execute(ragdb.render_schema(table, dim))
            conn.commit()
            print(f"[ingest] Created {table} (VECTOR({dim})).")
        elif current_dim != dim:
            raise SystemExit(f"[ingest] {table}.embedding is VECTOR({current_dim}) but {model_tag} "
                             f"produces {dim} dims. Use a separate --table for this model; vectors are never padded.")

        have = existing_hashes(conn, table, model_tag)
        todo = [r for r in rows if have.get((r["doc_key"], r["chunk_index"])) != r["content_hash"]]
        stats["unchanged"] = len(rows) - len(todo)
        sql = upsert_sql(table)
        for i in range(0, len(todo), batch_size):
            batch = todo[i:i + batch_size]
            vecs = get_text_embeddings([document_text(r) for r in batch], batch_size=batch_size)
            with conn.cursor() as cur:
                for row, vec in zip(batch, vecs):
                    cur.execute(sql, {**row, "embedding": ragdb.vector_literal(vec)})
                    res = cur.fetchone()
                    if res is None:
                        stats["unchanged"] += 1
                    elif res[0]:
                        stats["inserted"] += 1
                    else:
                        stats["updated"] += 1
            conn.commit()
    finally:
        conn.close()

    changed = stats["inserted"] + stats["updated"]
    print(f"[ingest] {table}: {changed} changed rows "
          f"({stats['inserted']} inserted, {stats['updated']} updated), {stats['unchanged']} unchanged.")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=CORPUS_PATH)
    ap.add_argument("--table", default=settings.RAG_TABLE)
    ap.add_argument("--init-schema", action="store_true", help="create the table/indexes if missing")
    ap.add_argument("--dry-run", action="store_true", help="validate and report only")
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args(argv)
    if not args.dry_run and not ragdb.is_postgres_url(settings.RAG_DATABASE_URL):
        print("[ingest] RAG_DATABASE_URL (or DATABASE_URL) must be a Postgres URL.")
        return 2
    stats = ingest(args.corpus, args.table, args.init_schema, args.dry_run, args.batch_size)
    return 1 if stats["rejected"] else 0


if __name__ == "__main__":
    sys.exit(main())
