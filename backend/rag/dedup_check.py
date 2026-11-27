"""Near-duplicate detection over rag_data/documents/corpus.jsonl.

    python -m rag.dedup_check                  # report; writes rag/dedup_review.jsonl
    python -m rag.dedup_check --strict         # exit 1 on any reject or unresolved review pair

Every record is embedded with the active model (same text as retrieval: title + content);
all pairs are compared by cosine similarity:
  >= REJECT (0.97)  automatic reject — the newer record (higher id) must be removed/rewritten
  >= REVIEW (0.92)  queued in dedup_review.jsonl; a pair is resolved by listing it in
                    dedup_resolved.jsonl with a decision ("keep_both" + reason, or a fix)
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Set, Tuple

import numpy as np

from rag import validate_corpus as vc
from rag.pipeline import CORPUS_PATH, document_text, get_text_embeddings, semantic_model_available

_HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW_PATH = os.path.join(_HERE, "dedup_review.jsonl")
RESOLVED_PATH = os.path.join(_HERE, "dedup_resolved.jsonl")
REVIEW = 0.92
REJECT = 0.97


def pair_key(a: str, b: str) -> Tuple[str, str]:
    return tuple(sorted((a, b)))


def load_resolved(path: str = RESOLVED_PATH) -> Set[Tuple[str, str]]:
    if not os.path.exists(path):
        return set()
    return {pair_key(r["a"], r["b"]) for r in vc.load_jsonl(path)}


def similar_pairs(records: List[Dict[str, Any]], vectors: np.ndarray, threshold: float = REVIEW):
    """[(sim, rec_a, rec_b)] for every pair with cosine >= threshold, most similar first."""
    sims = vectors @ vectors.T
    out = []
    n = len(records)
    for i in range(n):
        for j in range(i + 1, n):
            if sims[i, j] >= threshold:
                out.append((float(sims[i, j]), records[i], records[j]))
    return sorted(out, key=lambda x: -x[0])


def check(records: List[Dict[str, Any]], vectors=None, resolved=None):
    if vectors is None:
        vectors = np.array(get_text_embeddings([document_text(r) for r in records], kind="passage"))
    resolved = load_resolved() if resolved is None else resolved
    rejects, review = [], []
    for sim, a, b in similar_pairs(records, vectors):
        item = {"similarity": round(sim, 4), "a": a["doc_key"], "b": b["doc_key"],
                "a_title": a["title"], "b_title": b["title"]}
        if sim >= REJECT:
            newer = a if a["id"] > b["id"] else b
            rejects.append({**item, "reject": newer["doc_key"]})
        elif pair_key(a["doc_key"], b["doc_key"]) not in resolved:
            review.append(item)
    return rejects, review


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=CORPUS_PATH)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    if not semantic_model_available():
        print("[dedup] No sentence-transformers model available; dedup needs real embeddings.")
        return 2
    records = vc.load_jsonl(args.corpus)
    rejects, review = check(records)
    for r in rejects:
        print(f"[dedup] REJECT {r['reject']} (cos {r['similarity']}): {r['a']} ~ {r['b']}")
    with open(REVIEW_PATH, "w", encoding="utf-8", newline="\n") as f:
        for r in review:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for r in review:
        print(f"[dedup] REVIEW cos {r['similarity']}: {r['a']} ~ {r['b']}")
    print(f"[dedup] {len(records)} records: {len(rejects)} rejects (>= {REJECT}), "
          f"{len(review)} unresolved pairs in [{REVIEW}, {REJECT}) -> {os.path.basename(REVIEW_PATH)}")
    return 1 if args.strict and (rejects or review) else 0


if __name__ == "__main__":
    sys.exit(main())
