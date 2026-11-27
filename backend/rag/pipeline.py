import hashlib
import json
import os
from typing import List, Dict, Any
import numpy as np
from config import settings
from rag import db as ragdb

# ── Semantic Embedding ─────────────────────────────────────────────────────────
# Provider: settings.EMBEDDING_PROVIDER
#   "openrouter" (default) → OpenRouter /embeddings API, no model weights in the server
#   "local"                → sentence-transformers in-process (bake-offs; requirements-local.txt)
# Model: settings.EMBEDDING_MODEL (switchable without code changes):
#   baai/bge-m3 (OpenRouter) / BAAI/bge-m3   → 1024 dims, no prefixes
#   intfloat/multilingual-e5-large-instruct  → 1024 dims, instruction on queries
#   intfloat/multilingual-e5-*               → "query: " / "passage: " prefixes
#   paraphrase-multilingual-MiniLM-L12-v2    → 384 dims (previous default)
# Fallback: keyword-frequency vector         → 192 dims (no extra deps)

E5_INSTRUCT_TASK = "Given a clinical question about a child, retrieve relevant clinical guideline passages"


def _prefix(text: str, kind: str) -> str:
    """Model-specific input prefix. kind is "query" (search text) or "passage" (a document)."""
    name = (settings.EMBEDDING_MODEL or "").lower()
    if "e5" not in name:
        return text                                  # bge-m3 / MiniLM: no prefixes
    if "instruct" in name:                           # e5-*-instruct: instruction on queries only
        return f"Instruct: {E5_INSTRUCT_TASK}\nQuery: {text}" if kind == "query" else text
    return f"{kind}: {text}"                         # classic e5: "query: " / "passage: "

_st_model = None          # the active embedder (OpenRouter API client or sentence-transformers model)
_st_checked = False
_st_available = False
_DOC_EMBEDDINGS_CACHE: Dict[str, Any] = {}


class OpenRouterEmbedder:
    """Embeddings over the OpenRouter API (OpenAI-compatible /embeddings endpoint).
    Mirrors the small part of the SentenceTransformer interface the pipeline uses, so no model
    weights (and no torch) are needed in the serving process."""

    def __init__(self, model: str, api_key: str, url: str, timeout: float = 20.0):
        self.model, self.api_key, self.url, self.timeout = model, api_key, url, timeout
        self._dim = None

    def encode(self, texts, batch_size: int = 64, normalize_embeddings: bool = True, show_progress_bar: bool = False):
        import requests
        single = isinstance(texts, str)
        items = [texts] if single else list(texts)
        out = []
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            resp = requests.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": batch},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
            if len(data) != len(batch):
                raise RuntimeError(f"OpenRouter returned {len(data)} embeddings for {len(batch)} inputs")
            out.extend(d["embedding"] for d in data)
        arr = np.array(out, dtype=float)
        if normalize_embeddings:
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr = arr / np.where(norms == 0, 1.0, norms)
        return arr[0] if single else arr

    def get_embedding_dimension(self) -> int:
        if self._dim is None:
            self._dim = int(self.encode("probe").shape[0])
        return self._dim


def _try_load_st():
    """Load the configured embedder once. Returns it, or None (keyword fallback)."""
    global _st_model, _st_checked, _st_available
    if _st_checked:
        return _st_model
    _st_checked = True
    model_name = settings.EMBEDDING_MODEL
    try:
        if settings.EMBEDDING_PROVIDER == "openrouter":
            if not settings.OPENROUTER_API_KEY:
                raise RuntimeError("OPENROUTER_API_KEY is not set")
            _st_model = OpenRouterEmbedder(model_name, settings.OPENROUTER_API_KEY, settings.OPENROUTER_EMBEDDINGS_URL)
            print(f"[RAG] Embeddings via OpenRouter API: {model_name}")
        else:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer(model_name)
            getter = getattr(_st_model, "get_embedding_dimension", None) or getattr(_st_model, "get_sentence_embedding_dimension", None)
            print(f"[RAG] Local sentence-transformers embedding: {model_name} ({getter() if getter else '?'} dims)")
        _st_available = True
    except Exception as e:
        print(f"[RAG] Embedding model unavailable -> keyword/full-text fallback. ({e})")
        _st_model = None
        _st_available = False
    return _st_model


def get_embedding_dim() -> int:
    model = _try_load_st()
    if not model:
        return 192
    getter = getattr(model, "get_embedding_dimension", None) or getattr(model, "get_sentence_embedding_dimension", None)
    return getter() if getter else 384


def get_text_embedding(text: str, kind: str = "query") -> List[float]:
    model = _try_load_st()
    if model:
        vec = model.encode(_prefix(text, kind), normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()
    return _keyword_embedding(text)


def get_text_embeddings(texts: List[str], batch_size: int = 32, kind: str = "passage") -> List[List[float]]:
    """Batch form of get_text_embedding (used by ingestion and evaluation)."""
    model = _try_load_st()
    if model:
        raw = model.encode([_prefix(t, kind) for t in texts], batch_size=batch_size, normalize_embeddings=True,
                           show_progress_bar=len(texts) > batch_size)
        return [v.tolist() for v in raw]
    return [_keyword_embedding(t) for t in texts]


def semantic_model_available() -> bool:
    """True when an embedding model is configured and loaded (not the keyword fallback)."""
    return _try_load_st() is not None


def document_text(doc: Dict[str, Any]) -> str:
    """The text a document (or chunk) is embedded from: title + content, as before."""
    return f"{doc['title']} {doc['content']}"


# ── Keyword Fallback (192-dim) ─────────────────────────────────────────────────

_KEYWORDS = [
    "توحد", "طيف", "تواصل", "اجتماعي", "بصري", "تفاعل", "مشترك", "مبادرة", "إيماءة", "إشارة",
    "انتباه_مشترك", "تقليد", "تخيلي", "رمزي", "إيكولاليا", "تكرار", "روتين", "صلابة", "مقاومة",
    "اهتمامات_محدودة", "نمطي", "حركات_نمطية", "رفرفة", "دوران", "مشي_أطراف", "مثابرة",
    "انتباه", "تركيز", "فرط", "نشاط", "تشتت", "اندفاعية", "مهمة", "تنظيم", "ذاكرة_عاملة",
    "تنفيذي", "تخطيط", "مرونة", "مبادرة", "مثابرة", "تنظيم_ذاتي", "انتظار", "دور",
    "نطق", "لغة", "كلام", "تعبير", "استقبال", "تأخر", "مفردات", "مخارج", "حروف", "صعوبة",
    "تلعثم", "طلاقة", "براغماتي", "سردي", "قصة", "حوار", "تناوب", "سياق", "تواصل_اجتماعي",
    "قراءة", "كتابة", "رياضيات", "حساب", "تهجئة", "عسر_قراءة", "خط", "رموز", "تحليل",
    "تعليم", "مدرسة", "صف", "أكاديمي", "تحصيل", "مناهج", "تعلم", "ذكاء",
    "حسي", "تكامل", "سمع", "بصر", "لمس", "توازن", "دهليزي", "عمق", "إحساس", "حساسية",
    "ألم", "جسدي", "عضلي", "تعديل_حسي", "دايت_حسي", "انزعاج", "فرط_حساسية", "نقص_حساسية",
    "بحث_حسي", "تجنب_حسي", "أكل", "ملمس", "ضوء", "تكامل_حسي",
    "سلوك", "غضب", "قلق", "خوف", "عاطفي", "احباط", "هدوء", "بكاء", "عدوان", "ضرب",
    "تنظيم_انفعالي", "مشاعر", "تهدئة", "ضغط", "أزمة", "انسحاب", "اكتئاب", "خطر",
    "هدف", "تدخل", "علاج", "إحالة", "طبيب", "أخصائي", "تقييم", "خطة", "برنامج",
    "تخاطب", "وظيفي", "نفسي", "سلوكي", "تعديل", "جلسة", "تدريب", "دعم", "توصية",
    "والدين", "معلم", "مدرسة", "منزل", "بيئة", "ملاحظة", "تقرير", "استبيان",
    "معايير", "تشخيص", "DSM", "ICD", "مستوى", "شدة", "اضطراب", "نمو", "تطور",
    "مصاحب", "مزدوج", "ADHD_توحد", "لغة_توحد", "حسي_توحد",
]


def _keyword_embedding(text: str) -> List[float]:
    vec = [0.0] * 192
    text_lower = text.lower()
    for idx, kw in enumerate(_KEYWORDS[:160]):
        count = text_lower.count(kw.replace("_", " "))
        vec[idx] = float(count) * 2.0
    h = hashlib.md5(text.encode("utf-8")).digest()
    for i in range(32):
        vec[160 + i] = float(h[i % len(h)]) / 255.0
    arr = np.array(vec, dtype=float)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


# ── Seed Documents (loaded from rag_data/documents/corpus.jsonl) ───────────────
# The corpus is versioned data, not code: one JSON record per line in
# backend/rag_data/documents/corpus.jsonl. Precomputed document vectors live next to it in
# backend/rag_data/embeddings/<embedding tag>.jsonl (written by `python -m rag.ingest`).
# SEED_DOCUMENTS keeps its original name and record shape
# (id, title, specialty_tag, domain_tag, age_band, category, content, ...).

RAG_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rag_data")
CORPUS_PATH = os.path.join(RAG_DATA_DIR, "documents", "corpus.jsonl")
EMBEDDINGS_DIR = os.path.join(RAG_DATA_DIR, "embeddings")


def embeddings_path(tag: str = None) -> str:
    """File holding precomputed vectors for an embedding tag (e.g. openrouter:baai/bge-m3)."""
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in (tag or settings.EMBEDDING_VERSION))
    return os.path.join(EMBEDDINGS_DIR, f"{safe}.jsonl")


def document_vectors() -> Dict[str, Any]:
    """doc_key -> normalised vector for every SEED_DOCUMENT with the active model.
    Uses the committed embeddings file when present, embeds only what is missing (one batch)."""
    cache = _DOC_EMBEDDINGS_CACHE.setdefault("model", {})
    if not cache:
        cache.update(load_precomputed_vectors())
    missing = [d for d in SEED_DOCUMENTS if d["doc_key"] not in cache]
    if missing:
        vecs = get_text_embeddings([document_text(d) for d in missing], kind="passage")
        cache.update({d["doc_key"]: np.array(v, dtype=float) for d, v in zip(missing, vecs)})
    return cache


def load_precomputed_vectors(tag: str = None) -> Dict[str, Any]:
    """doc_key -> vector (chunk 0) from the committed embeddings file, if present."""
    path = embeddings_path(tag)
    out: Dict[str, Any] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    if r.get("chunk_index", 0) == 0:
                        out[r["doc_key"]] = np.array(r["embedding"], dtype=float)
    return out


def load_corpus(path: str = CORPUS_PATH) -> List[Dict[str, Any]]:
    """Read corpus.jsonl into a list of document dicts (blank lines ignored)."""
    docs: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


SEED_DOCUMENTS: List[Dict[str, Any]] = load_corpus()


# ── Vector Store Client ────────────────────────────────────────────────────────

_RESULT_FIELDS = ("title", "specialty_tag", "domain_tag", "age_band", "category", "content")

# One query against rag_documents. It reproduces _search_in_memory exactly:
#   - specialty_tag in specialties; age_band is the child's band or 'any';
#     domain_tag in domains only when domains is non-empty;
#   - score = cosine similarity (1 - cosine distance) + 0.05 for goals/strategy;
#   - highest score first, ties broken by corpus order (doc_id), top `limit`.
# Rows are restricted to the active embedding model. If a document was chunked at
# ingestion, only its best-scoring chunk is kept so one document fills one slot.
# The boost inside ORDER BY means the HNSW index is not used for this ranking: the
# filtered set is scanned exactly, which is what keeps results identical to the
# in-memory path (and is cheap at a few thousand rows).
_VECTOR_SQL = """
SELECT doc_id, title, specialty_tag, domain_tag, age_band, category, content, score
FROM (
    SELECT DISTINCT ON (doc_key)
           doc_key, doc_id, title, specialty_tag, domain_tag, age_band, category, content,
           (1 - (embedding <=> %(q)s::vector))
             + CASE WHEN category IN ('goals', 'strategy') THEN 0.05 ELSE 0 END AS score
    FROM {table}
    WHERE embedding_model = %(model)s
      AND specialty_tag = ANY(%(specialties)s)
      AND age_band IN (%(age_band)s, 'any')
      AND (cardinality(%(domains)s::text[]) = 0 OR domain_tag = ANY(%(domains)s))
    ORDER BY doc_key, score DESC, chunk_index
) best
ORDER BY score DESC, doc_id
LIMIT %(limit)s
"""

# Hybrid fallback when no embedding model can be loaded at query time: Postgres
# full-text search (Arabic config) instead of the 192-dim keyword vector. Same
# filters, same +0.05 goals/strategy boost; query terms are OR-ed so a long
# natural-language query still matches.
_FTS_SQL = """
SELECT doc_id, title, specialty_tag, domain_tag, age_band, category, content, score
FROM (
    SELECT DISTINCT ON (doc_key)
           doc_key, doc_id, title, specialty_tag, domain_tag, age_band, category, content,
           ts_rank_cd(tsv, websearch_to_tsquery('arabic', %(q)s))
             + CASE WHEN category IN ('goals', 'strategy') THEN 0.05 ELSE 0 END AS score
    FROM {table}
    WHERE embedding_model = %(model)s
      AND specialty_tag = ANY(%(specialties)s)
      AND age_band IN (%(age_band)s, 'any')
      AND (cardinality(%(domains)s::text[]) = 0 OR domain_tag = ANY(%(domains)s))
      AND tsv @@ websearch_to_tsquery('arabic', %(q)s)
    ORDER BY doc_key, score DESC, chunk_index
) best
ORDER BY score DESC, doc_id
LIMIT %(limit)s
"""


def _or_query(query: str) -> str:
    return " or ".join(w for w in query.replace('"', " ").split() if w and w.lower() != "or")


class VectorStoreClient:
    """
    Guideline retrieval over Neon Postgres + pgvector (table rag_documents, filled offline
    by `python -m rag.ingest`). RAG_STORE=memory selects the in-memory cosine path over
    SEED_DOCUMENTS, which also serves as the fallback when the database is unreachable or
    not configured (e.g. local SQLite), so retrieval never fails a report.
    """

    def __init__(self):
        self.store = settings.RAG_STORE
        self.table = ragdb.safe_table(settings.RAG_TABLE)
        self.embedding_model = settings.EMBEDDING_VERSION
        self.is_connected = False  # set after the first successful pgvector query
        if self.store == "pgvector" and not ragdb.is_postgres_url(settings.RAG_DATABASE_URL):
            print("[RAG] RAG_DATABASE_URL is not a Postgres URL -> in-memory retrieval.")
            self.store = "memory"

    def search_guidelines(
        self,
        specialties: List[str],
        domains: List[str],
        age_band: str,
        query: str,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        """Return top-k relevant guidelines; falls back to in-memory if pgvector fails."""
        if self.store == "pgvector":
            try:
                return self._search_pgvector(specialties, domains, age_band, query, limit)
            except Exception as e:
                print(f"[RAG] pgvector search failed -> in-memory: {e}")
        return self._search_in_memory(specialties, domains, age_band, query, limit)

    def _search_pgvector(
        self,
        specialties: List[str],
        domains: List[str],
        age_band: str,
        query: str,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        params = {
            "model": self.embedding_model,
            "specialties": list(specialties or []),
            "domains": list(domains or []),
            "age_band": age_band,
            "limit": limit,
        }
        q_vec = None
        if semantic_model_available():
            try:
                q_vec = get_text_embedding(query)
            except Exception as e:  # e.g. the embeddings API is down or slow
                print(f"[RAG] Query embedding failed ({e}) -> Postgres full-text fallback.")
        if q_vec is not None:
            sql = _VECTOR_SQL.format(table=self.table)
            params["q"] = ragdb.vector_literal(q_vec)
        else:
            if not semantic_model_available():
                print("[RAG] Embedding model unavailable -> Postgres full-text fallback.")
            sql = _FTS_SQL.format(table=self.table)
            params["q"] = _or_query(query)

        with ragdb.pooled() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        self.is_connected = True
        return [
            {"id": r[0], **dict(zip(_RESULT_FIELDS, r[1:7])), "score": float(r[7])}
            for r in rows
        ]

    def _search_in_memory(
        self,
        specialties: List[str],
        domains: List[str],
        age_band: str,
        query: str,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Cosine similarity over SEED_DOCUMENTS using the active embedding model.
        Both query and doc vectors are L2-normalised, so dot-product = cosine.
        Selected with RAG_STORE=memory (tests) and used as the fallback path.
        """
        use_model = semantic_model_available()
        try:
            q_vec = np.array(get_text_embedding(query), dtype=float)
        except Exception as e:  # embeddings API down: degrade to the keyword vector for query and docs
            print(f"[RAG] Query embedding failed ({e}) -> keyword fallback in memory.")
            use_model = False
            q_vec = np.array(_keyword_embedding(query), dtype=float)
        if use_model:
            try:
                cache = document_vectors()              # committed vectors: no per-doc API calls
            except Exception as e:
                print(f"[RAG] Document embeddings unavailable ({e}) -> keyword fallback in memory.")
                use_model = False
                q_vec = np.array(_keyword_embedding(query), dtype=float)
        if not use_model:
            cache = _DOC_EMBEDDINGS_CACHE.setdefault("keyword", {})
        scored = []

        for doc in SEED_DOCUMENTS:
            if doc["specialty_tag"] not in specialties:
                continue
            if doc["age_band"] != "any" and doc["age_band"] != age_band:
                continue
            if domains and doc["domain_tag"] not in domains:
                continue

            key = doc["doc_key"]
            if key not in cache:
                cache[key] = np.array(
                    get_text_embedding(document_text(doc), kind="passage") if use_model
                    else _keyword_embedding(document_text(doc)), dtype=float
                )
            d_vec = cache[key]
            score = float(np.dot(q_vec, d_vec))
            if doc["category"] in ("goals", "strategy"):
                score += 0.05          # small actionability boost
            scored.append((doc, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {
                "id": d["id"],
                "title": d["title"],
                "specialty_tag": d["specialty_tag"],
                "domain_tag": d["domain_tag"],
                "age_band": d["age_band"],
                "category": d["category"],
                "content": d["content"],
                "score": float(s),
            }
            for d, s in scored[:limit]
        ]


rag_client = VectorStoreClient()
