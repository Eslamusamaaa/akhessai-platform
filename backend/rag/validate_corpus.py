"""Validate rag/corpus.jsonl records before they are loaded.

    python -m rag.validate_corpus                # schema / taxonomy checks
Exit code 1 on any violation. Ingestion (rag/ingest.py) refuses invalid records.
"""
import argparse
import json
import re
import sys
from typing import Any, Dict, List, Tuple

SPECIALTIES = {"autism", "speech_language", "adhd", "learning_disabilities",
               "sensory_processing", "behavior_emotional"}
DOMAINS = {"academic_skills", "social_communication", "sensory_reactivity", "expressive_language",
           "restricted_repetitive", "internalizing", "attention", "emotional_regulation",
           "executive_function", "receptive_language", "pragmatic_language", "impulsivity",
           "articulation", "hyperactivity", "vestibular", "proprioceptive", "externalizing"}
AGE_BANDS = {"0-6", "6-18", "any"}
CATEGORIES = {"glossary", "strategy", "goals", "referral"}
AUDIENCES = {"parent", "teacher", "specialist", "all"}
DIALECTS = {"msa", "egy", "gulf", None}

REQUIRED = ("id", "doc_key", "title", "content", "specialty_tag", "domain_tag",
            "age_band", "category", "audience", "language")
ARABIC_RE = re.compile(r"[؀-ۿ]")
DOC_KEY_RE = re.compile(r"^[a-z_]+-\d{3,4}$")


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    records = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"line {n}: invalid JSON ({e})") from e
    return records


def check_record(rec: Dict[str, Any]) -> List[str]:
    """Problems with a single record (empty list = valid)."""
    errs = [f"missing field '{k}'" for k in REQUIRED if rec.get(k) in (None, "")]
    if errs:
        return errs
    if not isinstance(rec["id"], int):
        errs.append("id must be an integer")
    if not DOC_KEY_RE.match(rec["doc_key"]) or not rec["doc_key"].startswith(rec["specialty_tag"] + "-"):
        errs.append(f"doc_key '{rec['doc_key']}' must look like '<specialty_tag>-NNN'")
    for field, allowed in (("specialty_tag", SPECIALTIES), ("domain_tag", DOMAINS),
                           ("age_band", AGE_BANDS), ("category", CATEGORIES),
                           ("audience", AUDIENCES)):
        if rec[field] not in allowed:
            errs.append(f"{field}='{rec[field]}' not in {sorted(allowed)}")
    if rec.get("dialect_examples") not in DIALECTS:
        errs.append(f"dialect_examples='{rec.get('dialect_examples')}' not in msa|egy|gulf|null")
    if rec["language"] != "ar":
        errs.append("language must be 'ar'")
    if not ARABIC_RE.search(rec["content"]):
        errs.append("content contains no Arabic text")
    return errs


def validate(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Returns (valid records, [(doc_key, problem), ...])."""
    failures: List[Tuple[str, str]] = []
    valid: List[Dict[str, Any]] = []
    seen_keys, seen_ids = set(), set()
    for rec in records:
        key = rec.get("doc_key") or f"id={rec.get('id')}"
        errs = check_record(rec)
        if rec.get("doc_key") in seen_keys:
            errs.append("duplicate doc_key")
        if rec.get("id") in seen_ids:
            errs.append("duplicate id")
        seen_keys.add(rec.get("doc_key"))
        seen_ids.add(rec.get("id"))
        if errs:
            failures.extend((key, e) for e in errs)
        else:
            valid.append(rec)
    return valid, failures


def main(argv=None) -> int:
    from rag.pipeline import CORPUS_PATH
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=CORPUS_PATH)
    args = ap.parse_args(argv)
    records = load_jsonl(args.corpus)
    valid, failures = validate(records)
    for key, problem in failures:
        print(f"[INVALID] {key}: {problem}")
    print(f"[validate] {len(records)} records, {len(valid)} valid, {len(failures)} problems")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
