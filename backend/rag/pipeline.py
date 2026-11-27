import hashlib
import json
import os
from typing import List, Dict, Any
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from config import settings

# ── Semantic Embedding (sentence-transformers) ─────────────────────────────────
# Primary: paraphrase-multilingual-MiniLM-L12-v2  → 384 dims, supports Arabic
# Fallback: keyword-frequency vector              → 192 dims (no extra deps)

_st_model = None
_st_checked = False
_st_available = False
_DOC_EMBEDDINGS_CACHE: Dict[str, Any] = {}


def _try_load_st():
    """Load sentence-transformers model once. Returns model or None."""
    global _st_model, _st_checked, _st_available
    if _st_checked:
        return _st_model
    _st_checked = True
    try:
        from sentence_transformers import SentenceTransformer
        model_name = settings.EMBEDDING_MODEL
        _st_model = SentenceTransformer(model_name)
        _st_available = True
        # resolve dim without triggering the deprecated method name
        getter = getattr(_st_model, "get_embedding_dimension", None) or getattr(_st_model, "get_sentence_embedding_dimension", None)
        dim = getter() if getter else 384
        print(f"[RAG] Semantic embedding active: {model_name} ({dim} dims)")
    except Exception as e:
        print(f"[RAG] sentence-transformers not available -> keyword fallback. ({e})")
        _st_model = None
        _st_available = False
    return _st_model


def get_embedding_dim() -> int:
    model = _try_load_st()
    if not model:
        return 192
    # get_embedding_dimension is the current name; fall back to old name if needed
    getter = getattr(model, "get_embedding_dimension", None) or getattr(model, "get_sentence_embedding_dimension", None)
    return getter() if getter else 384


def get_text_embedding(text: str) -> List[float]:
    model = _try_load_st()
    if model:
        vec = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()
    return _keyword_embedding(text)


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


# ── Seed Documents (120 clinical guidelines, loaded from corpus.jsonl) ────────
# The corpus is versioned data, not code: one JSON record per line in
# rag/corpus.jsonl. SEED_DOCUMENTS keeps its original name and record shape
# (id, title, specialty_tag, domain_tag, age_band, category, content, ...).

CORPUS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus.jsonl")


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

class VectorStoreClient:
    """
    Qdrant-backed vector store with in-memory cosine-similarity fallback.
    Vector dimensionality is determined at runtime from the active embedding model.
    """

    # collection name bumped so old 192-dim collection is never reused
    COLLECTION_NAME = "clinical_guidelines_v4"

    def __init__(self):
        self.is_connected = False
        self._vector_size: int | None = None

        try:
            # Short timeout: on serverless cold starts with no Qdrant configured,
            # fail fast into the in-memory fallback instead of stalling the request.
            self.client = QdrantClient(url=settings.QDRANT_URL, timeout=1.5)
            self.client.get_collections()
            self.is_connected = True
        except Exception as e:
            print(f"[RAG] Qdrant connection failed (in-memory fallback active): {e}")
            self.client = None

    @property
    def vector_size(self) -> int:
        if self._vector_size is None:
            self._vector_size = get_embedding_dim()
        return self._vector_size

    def initialize_collection(self) -> bool:
        """Drop & recreate collection, then seed all SEED_DOCUMENTS (120)."""
        if not self.is_connected or not self.client:
            print("[RAG] Qdrant not connected - skipping collection init.")
            return False
        try:
            existing = [c.name for c in self.client.get_collections().collections]
            if self.COLLECTION_NAME in existing:
                self.client.delete_collection(self.COLLECTION_NAME)

            self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=qmodels.VectorParams(
                    size=self.vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )

            # Batch-encode all documents (one model.encode() call = much faster)
            texts = [f"{d['title']} {d['content']}" for d in SEED_DOCUMENTS]
            model = _try_load_st()
            if model:
                print(f"[RAG] Encoding {len(texts)} documents with sentence-transformers...")
                raw = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
                vecs = [v.tolist() for v in raw]
                method = f"sentence-transformers ({self.vector_size} dims)"
            else:
                vecs = [_keyword_embedding(t) for t in texts]
                method = f"keyword-fallback ({self.vector_size} dims)"

            points = [
                qmodels.PointStruct(
                    id=doc["id"],
                    vector=vec,
                    payload={k: v for k, v in doc.items() if k != "id"},
                )
                for doc, vec in zip(SEED_DOCUMENTS, vecs)
            ]
            self.client.upsert(collection_name=self.COLLECTION_NAME, points=points)
            print(f"[RAG] Seeded {len(points)} documents using {method}.")
            return True

        except Exception as e:
            print(f"[RAG] Error initializing Qdrant collection: {e}")
            return False

    def search_guidelines(
        self,
        specialties: List[str],
        domains: List[str],
        age_band: str,
        query: str,
        limit: int = 6,
    ) -> List[Dict[str, Any]]:
        """Return top-k relevant guidelines; falls back to in-memory on Qdrant failure."""
        if self.is_connected and self.client:
            try:
                must_filters = [
                    qmodels.FieldCondition(
                        key="specialty_tag",
                        match=qmodels.MatchAny(any=specialties),
                    ),
                    qmodels.FieldCondition(
                        key="age_band",
                        match=qmodels.MatchAny(any=[age_band, "any"]),
                    ),
                ]
                if domains:
                    must_filters.append(
                        qmodels.FieldCondition(
                            key="domain_tag",
                            match=qmodels.MatchAny(any=domains),
                        )
                    )

                hits = self.client.search(
                    collection_name=self.COLLECTION_NAME,
                    query_vector=get_text_embedding(query),
                    query_filter=qmodels.Filter(must=must_filters),
                    limit=limit,
                )
                return [
                    {
                        "id": h.id,
                        "title": h.payload["title"],
                        "specialty_tag": h.payload["specialty_tag"],
                        "domain_tag": h.payload["domain_tag"],
                        "age_band": h.payload["age_band"],
                        "category": h.payload["category"],
                        "content": h.payload["content"],
                        "score": h.score,
                    }
                    for h in hits
                ]
            except Exception as e:
                print(f"[RAG] Qdrant search failed -> in-memory: {e}")

        return self._search_in_memory(specialties, domains, age_band, query, limit)

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
        """
        q_vec = np.array(get_text_embedding(query), dtype=float)
        scored = []

        for doc in SEED_DOCUMENTS:
            if doc["specialty_tag"] not in specialties:
                continue
            if doc["age_band"] != "any" and doc["age_band"] != age_band:
                continue
            if domains and doc["domain_tag"] not in domains:
                continue

            doc_id = doc["id"]
            if doc_id not in _DOC_EMBEDDINGS_CACHE:
                _DOC_EMBEDDINGS_CACHE[doc_id] = np.array(
                    get_text_embedding(f"{doc['title']} {doc['content']}"), dtype=float
                )
            d_vec = _DOC_EMBEDDINGS_CACHE[doc_id]
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
