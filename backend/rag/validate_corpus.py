"""Validate rag_data/documents/corpus.jsonl records before they are loaded.

    python -m rag.validate_corpus                # all checks (ingestion runs the same ones)

Every record: required fields, exact taxonomy enums (6 specialties, 17 domains, 3 age
bands, 4 categories, 4 audiences), Arabic content, unique id / doc_key.

Every new (non-legacy) record must also carry its source: source_name, source_url (http/s),
license and accessed_at (YYYY-MM-DD). A document containing any number (prevalence, dosage,
cutoff, age...) without a source_url is rejected outright. No single source domain may
contribute more than 15% of the corpus.

The 120 legacy records (legacy: true) are grandfathered on sources; the ones that contain
unsourced numbers are listed as warnings so they can gain sources during re-tagging.
Exit code 1 on any violation. Ingestion (rag/ingest.py) refuses invalid records.
"""
import argparse
import collections
import json
import re
import sys
from datetime import date
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

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
SOURCE_FIELDS = ("source_name", "source_url", "license", "accessed_at")
SOURCE_CAP = 0.15
ARABIC_RE = re.compile(r"[؀-ۿ]")
NUMBER_RE = re.compile(r"[0-9٠-٩۰-۹]")
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


def source_domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def has_number(rec: Dict[str, Any]) -> bool:
    return bool(NUMBER_RE.search(rec.get("content", "")))


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

    if not rec.get("legacy"):
        errs += [f"new documents need '{k}'" for k in SOURCE_FIELDS if not rec.get(k)]
        url = rec.get("source_url") or ""
        if url and urlparse(url).scheme not in ("http", "https"):
            errs.append("source_url must be an http(s) URL")
        if rec.get("accessed_at"):
            try:
                date.fromisoformat(rec["accessed_at"])
            except (TypeError, ValueError):
                errs.append("accessed_at must be YYYY-MM-DD")
    if has_number(rec) and not rec.get("source_url") and not rec.get("legacy"):
        errs.append("contains a number but has no source_url")
    return errs


def source_cap_violations(records: List[Dict[str, Any]], cap: float = SOURCE_CAP) -> List[Tuple[str, str]]:
    n = len(records)
    counts = collections.Counter(source_domain(r["source_url"]) for r in records if r.get("source_url"))
    return [(dom, f"source domain contributes {c}/{n} docs ({c / n:.0%}) > {cap:.0%} cap")
            for dom, c in counts.items() if n and c / n > cap]


def legacy_warnings(records: List[Dict[str, Any]]) -> List[str]:
    return [r["doc_key"] for r in records
            if r.get("legacy") and has_number(r) and not r.get("source_url")]


def validate(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    """Returns (valid records, [(doc_key or source domain, problem), ...])."""
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
    failures += source_cap_violations(records)
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
    warn = legacy_warnings(records)
    if warn:
        print(f"[WARN] {len(warn)} legacy docs contain numbers but have no source yet: {', '.join(warn)}")
    print(f"[validate] {len(records)} records, {len(valid)} valid, {len(failures)} problems")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
