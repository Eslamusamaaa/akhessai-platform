"""Postgres + pgvector plumbing shared by the retrieval path (pipeline.py) and the
offline scripts (ingest.py, evaluate.py). Uses psycopg2, already a backend dependency.
Vectors are passed as pgvector text literals ('[0.1,0.2,...]'::vector), so no extra
Python package is needed."""
import os
import re
import threading
from typing import Iterable, Optional

from config import settings

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

_pool = None
_pool_lock = threading.Lock()


def is_postgres_url(url: Optional[str]) -> bool:
    return bool(url) and url.split(":", 1)[0].split("+", 1)[0] in ("postgres", "postgresql")


def to_psycopg_dsn(url: str) -> str:
    """Accept SQLAlchemy-style URLs (postgresql+psycopg2://) as well as plain ones."""
    scheme, rest = url.split(":", 1)
    return "postgresql:" + rest if scheme.split("+", 1)[0] in ("postgres", "postgresql") else url


def safe_table(name: str) -> str:
    """Table names are interpolated into SQL, so only allow plain identifiers."""
    if not _TABLE_RE.match(name or ""):
        raise ValueError(f"Invalid RAG table name: {name!r}")
    return name


def vector_literal(vec: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(x):.8g}" for x in vec) + "]"


def connect(url: Optional[str] = None):
    """A standalone connection (scripts). Caller closes it."""
    import psycopg2
    return psycopg2.connect(to_psycopg_dsn(url or settings.RAG_DATABASE_URL), connect_timeout=5)


def get_pool():
    """Small per-process pool for request-time retrieval (FastAPI sync routes run in threads)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg2.pool import ThreadedConnectionPool
                _pool = ThreadedConnectionPool(
                    1, int(os.getenv("RAG_POOL_MAX", "5")),
                    dsn=to_psycopg_dsn(settings.RAG_DATABASE_URL), connect_timeout=5,
                )
    return _pool


class pooled:
    """`with pooled() as conn:` borrows a pooled connection; a broken one is discarded."""

    def __enter__(self):
        self.pool = get_pool()
        self.conn = self.pool.getconn()
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        broken = exc_type is not None and getattr(self.conn, "closed", 0)
        try:
            if not broken:
                self.conn.rollback()  # read-only use: end the transaction, keep the connection
        finally:
            self.pool.putconn(self.conn, close=bool(broken))
        return False


def render_schema(table: str = "rag_documents", dim: int = 1024) -> str:
    """schema.sql with the table name and vector dimension substituted (never padded)."""
    table = safe_table(table)
    sql = open(SCHEMA_PATH, encoding="utf-8").read()
    sql = sql.replace("VECTOR(1024)", f"VECTOR({int(dim)})")
    sql = sql.replace("rag_docs_", f"{table}_").replace("rag_documents", table)
    return sql


def table_vector_dim(conn, table: str) -> Optional[int]:
    """Dimension of <table>.embedding, or None if the table does not exist."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT a.atttypmod FROM pg_attribute a
               JOIN pg_class c ON c.oid = a.attrelid
               WHERE c.relname = %s AND a.attname = 'embedding' AND NOT a.attisdropped""",
            (safe_table(table),),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None
