"""Parity check: pgvector search_guidelines vs the in-memory path, on the same corpus
and embedding model. Run after `python -m rag.ingest`.

    python -m rag.parity_check

Inputs mirror what main.py sends: each specialty's trigger domains (from
rules_config.yaml, read-only), both age bands, with and without a domain filter, plus
multi-specialty profiles. The query string is built exactly like main.py builds it.
Exit code 1 if any input returns a different ordered list of document ids.
"""
import os
import sys
from typing import Dict, List

import yaml

from rag.pipeline import rag_client

_HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(_HERE, "..", "rules", "rules_config.yaml")


def main_query(specialties: List[str]) -> str:
    # Same f-string as backend/main.py (trigger_report_draft); main.py itself is not imported.
    return f"أهداف وتوصيات وخطط علاجية لـ {', '.join(specialties)}"


def sample_inputs() -> List[Dict]:
    with open(RULES_PATH, encoding="utf-8") as f:
        triggers = yaml.safe_load(f)["triggers"]
    cases = []
    for spec, cfg in triggers.items():
        for age in ("0-6", "6-18"):
            cases.append({"specialties": [spec], "domains": list(cfg["domains"]), "age_band": age})
            cases.append({"specialties": [spec], "domains": [cfg["domains"][0]], "age_band": age})
            cases.append({"specialties": [spec], "domains": [], "age_band": age})
    combos = [["autism", "speech_language"], ["adhd", "learning_disabilities"],
              ["autism", "sensory_processing", "behavior_emotional"], list(triggers)]
    for specs in combos:
        doms = sorted({d for s in specs for d in triggers[s]["domains"]})
        for age in ("0-6", "6-18"):
            cases.append({"specialties": specs, "domains": doms, "age_band": age})
            cases.append({"specialties": specs, "domains": [], "age_band": age})
    return cases


def run() -> int:
    if rag_client.store != "pgvector":
        print("[parity] RAG_STORE is not pgvector / RAG_DATABASE_URL is not Postgres.")
        return 2
    mismatches, max_score_diff = 0, 0.0
    cases = sample_inputs()
    for c in cases:
        q = main_query(c["specialties"])
        pg = rag_client._search_pgvector(c["specialties"], c["domains"], c["age_band"], q, 6)
        mem = rag_client._search_in_memory(c["specialties"], c["domains"], c["age_band"], q, 6)
        same = [d["id"] for d in pg] == [d["id"] for d in mem]
        same_shape = all(set(d) == set(m) for d, m in zip(pg, mem))
        for d, m in zip(pg, mem):
            if d["id"] == m["id"]:
                max_score_diff = max(max_score_diff, abs(d["score"] - m["score"]))
        if not (same and same_shape):
            mismatches += 1
            print(f"[parity] MISMATCH {c}\n   pgvector={[d['id'] for d in pg]}\n   memory  ={[d['id'] for d in mem]}")
    print(f"[parity] {len(cases) - mismatches}/{len(cases)} inputs identical "
          f"(ordered ids + dict shape); max |score diff| = {max_score_diff:.2e}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(run())
