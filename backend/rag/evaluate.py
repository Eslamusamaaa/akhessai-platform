"""Arabic retrieval evaluation: Recall@6 and MRR over rag/eval_set.jsonl.

Runs every query through the shipped retrieval path, rag_client.search_guidelines
(metadata filter + similarity, exactly as main.py uses it; RAG_STORE / RAG_TABLE /
EMBEDDING_MODEL pick the store and model). Measures only; changes no runtime behaviour.

    python -m rag.evaluate                         # report
    python -m rag.evaluate --similarity-only       # also rank with no metadata filter (measurement)
    python -m rag.evaluate --check                 # exit 1 if Recall@6/MRR regress vs eval_baseline.json
    python -m rag.evaluate --write-baseline        # record the current numbers as the baseline
    python -m rag.evaluate --json out.json         # machine-readable results

Recall@6 per query = |relevant ∩ top-6| / |relevant|; MRR = 1 / rank of the first relevant
doc (0 if none in the top 6). Slices: by query kind and by each domain the query targets.
"""
import argparse
import collections
import json
import os
import sys
from typing import Any, Dict, List

import numpy as np

from config import settings
from rag import pipeline
from rag.pipeline import rag_client

_HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_SET = os.path.join(_HERE, "eval_set.jsonl")
BASELINE = os.path.join(_HERE, "eval_baseline.json")
K = 6
TOLERANCE = 1e-6


def load_eval(path: str = EVAL_SET) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _id_to_key() -> Dict[int, str]:
    return {d["id"]: d["doc_key"] for d in pipeline.SEED_DOCUMENTS}


def similarity_only(query: str, k: int = K) -> List[int]:
    """Same scoring as the shipped path (cosine + 0.05 goals/strategy) over ALL docs, no filter."""
    q = np.array(pipeline.get_text_embedding(query), dtype=float)
    scored = []
    for d in pipeline.SEED_DOCUMENTS:
        if d["id"] not in pipeline._DOC_EMBEDDINGS_CACHE:
            pipeline._DOC_EMBEDDINGS_CACHE[d["id"]] = np.array(
                pipeline.get_text_embedding(pipeline.document_text(d)), dtype=float)
        s = float(np.dot(q, pipeline._DOC_EMBEDDINGS_CACHE[d["id"]]))
        if d["category"] in ("goals", "strategy"):
            s += 0.05
        scored.append((s, d["id"]))
    scored.sort(key=lambda x: -x[0])
    return [i for _, i in scored[:k]]


def score(ranked_keys: List[str], relevant: List[str]) -> Dict[str, float]:
    rel = set(relevant)
    hits = [k for k in ranked_keys[:K] if k in rel]
    rr = next((1.0 / (i + 1) for i, k in enumerate(ranked_keys[:K]) if k in rel), 0.0)
    return {"recall": len(hits) / len(rel) if rel else 0.0, "rr": rr}


def _agg(rows: List[Dict[str, float]]) -> Dict[str, float]:
    n = len(rows)
    return {"n": n,
            "recall@6": round(sum(r["recall"] for r in rows) / n, 4) if n else 0.0,
            "mrr": round(sum(r["rr"] for r in rows) / n, 4) if n else 0.0}


def evaluate(eval_set: List[Dict[str, Any]], with_similarity_only: bool = False) -> Dict[str, Any]:
    id2key = _id_to_key()
    per_query, by_kind, by_domain = [], collections.defaultdict(list), collections.defaultdict(list)
    sim_rows, sim_by_kind = [], collections.defaultdict(list)
    for e in eval_set:
        docs = rag_client.search_guidelines(e["specialties"], e["domains"], e["age_band"], e["query"], K)
        keys = [id2key.get(d["id"], str(d["id"])) for d in docs]
        s = score(keys, e["relevant"])
        per_query.append({"qid": e["qid"], "kind": e["kind"], "retrieved": keys, **s})
        by_kind[e["kind"]].append(s)
        for dom in e["domains"]:
            by_domain[dom].append(s)
        if with_similarity_only:
            ss = score([id2key[i] for i in similarity_only(e["query"])], e["relevant"])
            per_query[-1]["similarity_only"] = ss
            sim_rows.append(ss)
            sim_by_kind[e["kind"]].append(ss)
    result = {
        "model": settings.EMBEDDING_VERSION,
        "store": rag_client.store,
        "table": rag_client.table,
        "corpus_docs": len(pipeline.SEED_DOCUMENTS),
        "overall": _agg([{"recall": q["recall"], "rr": q["rr"]} for q in per_query]),
        "by_kind": {k: _agg(v) for k, v in sorted(by_kind.items())},
        "by_domain": {k: _agg(v) for k, v in sorted(by_domain.items())},
        "queries": per_query,
    }
    if with_similarity_only:
        result["similarity_only"] = {"overall": _agg(sim_rows),
                                     "by_kind": {k: _agg(v) for k, v in sorted(sim_by_kind.items())}}
    return result


def regressions(result: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
    """Overall and per-kind Recall@6 / MRR must not drop below the recorded baseline."""
    out = []
    pairs = [("overall", result["overall"], baseline["overall"])]
    pairs += [(f"kind={k}", result["by_kind"].get(k, {}), v) for k, v in baseline.get("by_kind", {}).items()]
    for name, cur, base in pairs:
        for m in ("recall@6", "mrr"):
            if cur.get(m, 0.0) + TOLERANCE < base[m]:
                out.append(f"{name} {m}: {cur.get(m, 0.0):.4f} < baseline {base[m]:.4f}")
    return out


def print_report(r: Dict[str, Any]) -> None:
    print(f"\n== {r['model']}  (store={r['store']}, table={r['table']}, corpus={r['corpus_docs']} docs)")
    o = r["overall"]
    print(f"   overall    n={o['n']:<3} Recall@6={o['recall@6']:.4f}  MRR={o['mrr']:.4f}")
    for k, v in r["by_kind"].items():
        print(f"   {k:<14} n={v['n']:<3} Recall@6={v['recall@6']:.4f}  MRR={v['mrr']:.4f}")
    print("   by domain:")
    for k, v in r["by_domain"].items():
        print(f"     {k:<24} n={v['n']:<3} Recall@6={v['recall@6']:.4f}  MRR={v['mrr']:.4f}")
    if "similarity_only" in r:
        s = r["similarity_only"]["overall"]
        print(f"   similarity-only (no filter, measurement): Recall@6={s['recall@6']:.4f}  MRR={s['mrr']:.4f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default=EVAL_SET)
    ap.add_argument("--similarity-only", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--baseline", default=BASELINE)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args(argv)

    result = evaluate(load_eval(args.set), args.similarity_only)
    print_report(result)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    if args.write_baseline:
        keep = {k: result[k] for k in ("model", "store", "corpus_docs", "overall", "by_kind", "by_domain")}
        with open(args.baseline, "w", encoding="utf-8", newline="\n") as f:
            json.dump(keep, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[eval] baseline written to {args.baseline}")
    if args.check:
        with open(args.baseline, encoding="utf-8") as f:
            base = json.load(f)
        bad = regressions(result, base)
        for b in bad:
            print(f"[eval] REGRESSION {b}")
        if bad:
            return 1
        print(f"[eval] no regression vs baseline ({base['model']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
