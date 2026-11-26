"""Coverage matrix: 17 domains x 3 age bands x 4 audiences, cross-referenced with the
question bank. Read-only on questions/bank.json and rules/rules_config.yaml.

    python -m rag.coverage_report            # matrix + gap list
    python -m rag.coverage_report --strict   # exit 1 if any question-touched cell has < 8 docs

A cell (domain, age band, audience) is "touched" when at least one question measures that
domain, applies to that age band, and is answered by that informant. A document counts
toward a cell when its domain matches, its age_band is that band or 'any', and its
audience is that audience or 'all'. Every touched cell needs >= MIN_DOCS documents.
"""
import argparse
import collections
import json
import os
import sys
from typing import Any, Dict, List, Tuple

from rag import validate_corpus as vc
from rag.pipeline import CORPUS_PATH

_HERE = os.path.dirname(os.path.abspath(__file__))
BANK_PATH = os.path.join(_HERE, "..", "questions", "bank.json")
MIN_DOCS = 8
AGE_BANDS = ("0-6", "6-18")
AUDIENCES = ("parent", "teacher", "specialist")
INFORMANT_TO_AUDIENCE = {"parent": "parent", "teacher": "teacher", "specialist": "specialist"}

Cell = Tuple[str, str, str]  # (domain, age_band, audience)


def load_bank(path: str = BANK_PATH) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def question_cells(bank: List[Dict[str, Any]]) -> Dict[Cell, int]:
    """Number of questions touching each (domain, age band, audience) cell."""
    cells: Dict[Cell, int] = collections.Counter()
    for q in bank:
        aud = INFORMANT_TO_AUDIENCE.get(q["informant"])
        for dom in q["domain_tags"]:
            for band in q["age_bands"]:
                cells[(dom, band, aud)] += 1
    return cells


def doc_counts(records: List[Dict[str, Any]]) -> Dict[Cell, int]:
    counts: Dict[Cell, int] = collections.Counter()
    for r in records:
        bands = AGE_BANDS if r["age_band"] == "any" else (r["age_band"],)
        auds = AUDIENCES if (r.get("audience") or "all") == "all" else (r["audience"],)
        for b in bands:
            for a in auds:
                counts[(r["domain_tag"], b, a)] += 1
    return counts


def gaps(records: List[Dict[str, Any]], bank: List[Dict[str, Any]], min_docs: int = MIN_DOCS):
    """[(cell, questions, docs)] for touched cells under min_docs, worst (most questions) first."""
    q = question_cells(bank)
    d = doc_counts(records)
    out = [(cell, n, d.get(cell, 0)) for cell, n in q.items() if d.get(cell, 0) < min_docs]
    return sorted(out, key=lambda x: (-x[1], x[2], x[0]))


def dedicated_audience_counts(records: List[Dict[str, Any]]) -> Dict[str, int]:
    return dict(collections.Counter(r.get("audience") or "all" for r in records))


def report(records: List[Dict[str, Any]], bank: List[Dict[str, Any]]) -> str:
    q, d = question_cells(bank), doc_counts(records)
    lines = [f"Coverage: {len(records)} docs vs {len(bank)} questions (cell = domain x age band x audience; "
             f"'any'/'all' docs count in every band/audience; '*' = touched by questions, needs >= {MIN_DOCS})", ""]
    head = f"{'domain':<24}" + "".join(f"{b + '/' + a[:4]:>12}" for b in AGE_BANDS for a in AUDIENCES)
    lines.append(head)
    for dom in sorted(vc.DOMAINS):
        row = f"{dom:<24}"
        for b in AGE_BANDS:
            for a in AUDIENCES:
                mark = "*" if q.get((dom, b, a)) else " "
                row += f"{str(d.get((dom, b, a), 0)) + mark:>12}"
        lines.append(row)
    aud = dedicated_audience_counts(records)
    n = len(records) or 1
    lines += ["", "Dedicated audience docs: " + ", ".join(f"{k}={v} ({100 * v / n:.0f}%)" for k, v in sorted(aud.items())),
              "  targets: teacher >= 15%, specialist >= 10% of the corpus"]
    g = gaps(records, bank)
    lines += ["", f"Gap list ({len(g)} touched cells under {MIN_DOCS} docs; questions, docs):"]
    lines += [f"  {dom:<24}{band:<6}{a:<11} questions={nq:<3} docs={nd}" for (dom, band, a), nq, nd in g]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=CORPUS_PATH)
    ap.add_argument("--bank", default=BANK_PATH)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    records, bank = vc.load_jsonl(args.corpus), load_bank(args.bank)
    print(report(records, bank))
    return 1 if args.strict and gaps(records, bank) else 0


if __name__ == "__main__":
    sys.exit(main())
