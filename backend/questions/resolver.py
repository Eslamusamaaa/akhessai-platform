import os
import json
from typing import List, Dict, Any, Optional
import models

QUESTIONS_FILE = os.path.join(os.path.dirname(__file__), "bank.json")

def load_question_bank() -> List[Dict[str, Any]]:
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

QUESTION_BANK = load_question_bank()

# Pre-sort: core questions always before specialty questions, then by priority, then by id.
# is_core=True → 0 (higher importance), is_core=False → 1
QUESTION_BANK.sort(key=lambda q: (0 if q.get("is_core") else 1, q.get("priority", 3), q["id"]))

# Per-informant question caps to prevent questionnaire fatigue
MAX_QUESTIONS_PER_INFORMANT: Dict[str, int] = {
    "parent":     35,
    "teacher":    20,
    "specialist": 15,
}


def _dependency_met(q: Dict[str, Any], answered_ids: Dict[str, List[str]]) -> bool:
    """Return True if the question's depends_on condition is satisfied (or absent)."""
    dep = q.get("depends_on")
    if not dep:
        return True

    dep_id = dep["question_id"]
    if dep_id not in answered_ids:
        return False  # Parent question not yet answered

    expected = dep["answer_equals"]
    if not isinstance(expected, list):
        expected = [expected]

    given_answers = answered_ids[dep_id]
    if not isinstance(given_answers, list):
        given_answers = [given_answers]

    return any(val in expected for val in given_answers)


def get_next_question(
    session: models.AssessmentSession,
    db_responses: List[models.Response],
) -> Optional[Dict[str, Any]]:
    """
    Resolves the next unanswered question using adaptive priority ordering.

    Selection criteria (all must pass):
      1. age_band matches session.age_band
      2. informant matches session.current_informant (or 'any')
      3. is_core=True  OR  specialty_tags ∩ session.active_specialties ≠ ∅
      4. Not already answered
      5. depends_on condition satisfied

    The bank is pre-sorted by priority (1→3) so high-importance questions
    always surface before lower-priority ones within the same filter pass.
    """
    answered_ids: Dict[str, List[str]] = {
        r.question_id: r.selected_options for r in db_responses
    }

    current_informant = session.current_informant
    current_age_band = session.age_band
    active_specialties = set(session.active_specialties or [])

    # Enforce per-informant cap
    informant_count = sum(
        1 for r in db_responses if r.informant == current_informant
    )
    max_allowed = MAX_QUESTIONS_PER_INFORMANT.get(current_informant, 25)
    if informant_count >= max_allowed:
        return None  # Signal caller to advance to next informant

    for q in QUESTION_BANK:
        # ── 1. Age band ────────────────────────────────────────────────────
        if current_age_band not in q.get("age_bands", []):
            continue

        # ── 2. Informant ───────────────────────────────────────────────────
        q_informant = q.get("informant", "any")
        if q_informant != "any" and q_informant != current_informant:
            continue

        # ── 3. Specialty gate ──────────────────────────────────────────────
        is_core = q.get("is_core", False)
        if not is_core:
            q_specialties = set(q.get("specialty_tags", []))
            if not q_specialties.intersection(active_specialties):
                continue

        # ── 4. Not already answered ────────────────────────────────────────
        if q["id"] in answered_ids:
            continue

        # ── 5. Dependency check ────────────────────────────────────────────
        if not _dependency_met(q, answered_ids):
            continue

        return q

    return None  # No more eligible questions for this informant
