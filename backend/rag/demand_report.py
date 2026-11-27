"""Demand matrix derived from the question bank, and the ranked writing queue.
Read-only on questions/bank.json and rules/rules_config.yaml; never modifies them.

    python -m rag.demand_report
    python -m rag.demand_report --json queue.json

Prints, per domain: question count, informants asking about it, age bands it applies
to, and which specialties' triggers use it; per specialty: question counts. Then joins
demand with current corpus coverage (rag/coverage_report.py) into one ranked queue:
under-covered cells sorted by the number of questions touching them (descending). That
queue is the order in which new documents are written.
"""
import argparse
import collections
import json
import os
import sys
from typing import Any, Dict, List

import yaml

from rag import coverage_report as cov
from rag import validate_corpus as vc
from rag.pipeline import CORPUS_PATH

_HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(_HERE, "..", "rules", "rules_config.yaml")


def load_triggers(path: str = RULES_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["triggers"]


def domain_specialties(triggers: Dict[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = collections.defaultdict(list)
    for spec, cfg in triggers.items():
        for d in cfg["domains"]:
            out[d].append(spec)
    return out


def demand(bank: List[Dict[str, Any]], triggers: Dict[str, Any]) -> Dict[str, Any]:
    dom_spec = domain_specialties(triggers)
    per_domain: Dict[str, Dict[str, Any]] = {}
    for dom in sorted(vc.DOMAINS):
        qs = [q for q in bank if dom in q["domain_tags"]]
        per_domain[dom] = {
            "questions": len(qs),
            "informants": dict(collections.Counter(q["informant"] for q in qs)),
            "age_bands": dict(collections.Counter(b for q in qs for b in q["age_bands"])),
            "trigger_specialties": dom_spec.get(dom, []),
        }
    return {
        "totals": {
            "questions": len(bank),
            "informants": dict(collections.Counter(q["informant"] for q in bank)),
            "age_bands": dict(collections.Counter(b for q in bank for b in q["age_bands"])),
            "core": sum(1 for q in bank if q.get("is_core")),
        },
        "per_specialty": dict(collections.Counter(s for q in bank for s in q["specialty_tags"])),
        "per_domain": per_domain,
    }


def writing_queue(records, bank, triggers) -> List[Dict[str, Any]]:
    """Under-covered cells, most-demanded first, each with the specialties that can own the doc."""
    dom_spec = domain_specialties(triggers)
    by_q = collections.defaultdict(set)
    for q in bank:
        for d in q["domain_tags"]:
            for b in q["age_bands"]:
                by_q[(d, b, q["informant"])].update(q["specialty_tags"])
    out = []
    for (dom, band, aud), nq, nd in cov.gaps(records, bank):
        specs = sorted(by_q[(dom, band, aud)] | set(dom_spec.get(dom, [])))
        out.append({"domain": dom, "age_band": band, "audience": aud, "questions": nq,
                    "docs": nd, "needed": cov.MIN_DOCS - nd, "specialties": specs})
    return out


def corpus_share(records) -> Dict[str, Any]:
    n = len(records) or 1
    band = collections.Counter(r["age_band"] for r in records)
    return {"docs": len(records), "age_band": dict(band),
            "share_0_6_or_any": round((band["0-6"] + band["any"]) / n, 3),
            "share_0_6_only": round(band["0-6"] / n, 3)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=CORPUS_PATH)
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    records, bank, triggers = vc.load_jsonl(args.corpus), cov.load_bank(), load_triggers()
    dem = demand(bank, triggers)
    queue = writing_queue(records, bank, triggers)

    t = dem["totals"]
    print(f"Question bank: {t['questions']} questions ({t['core']} core); informants {t['informants']}; "
          f"age bands {t['age_bands']}")
    print("Per specialty (multi-tag): " + ", ".join(f"{k}={v}" for k, v in sorted(dem["per_specialty"].items(), key=lambda x: -x[1])))
    print(f"\n{'domain':<24}{'qs':>4}  {'informants':<38}{'age bands':<22}trigger specialties")
    for dom, v in dem["per_domain"].items():
        inf = ", ".join(f"{k}={n}" for k, n in sorted(v["informants"].items()))
        ab = ", ".join(f"{k}={n}" for k, n in sorted(v["age_bands"].items()))
        print(f"{dom:<24}{v['questions']:>4}  {inf:<38}{ab:<22}{', '.join(v['trigger_specialties'])}")
    share = corpus_share(records)
    print(f"\nCorpus age-band mix: {share['age_band']} (0-6-only share {share['share_0_6_only']:.0%}; "
          f"questions applying to 0-6: {t['age_bands'].get('0-6', 0)}/{t['questions']})")
    print(f"\nRanked writing queue ({len(queue)} cells under {cov.MIN_DOCS} docs, most questions first):")
    for i, c in enumerate(queue, 1):
        print(f"{i:>3}. {c['domain']:<24}{c['age_band']:<6}{c['audience']:<11}questions={c['questions']:<3}"
              f"docs={c['docs']:<3}need={c['needed']:<3}specialties={','.join(c['specialties'])}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"demand": dem, "corpus": share, "queue": queue}, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
