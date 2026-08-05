import os
import yaml
from typing import List, Dict, Any
import models
from questions.resolver import QUESTION_BANK

RULES_FILE = os.path.join(os.path.dirname(__file__), "rules_config.yaml")

def load_rules_config() -> Dict[str, Any]:
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

RULES_CONFIG = load_rules_config()

DOMAIN_TRANSLATIONS_AR = {
    "social_communication":   "التواصل الاجتماعي",
    "restricted_repetitive":  "السلوكيات النمطية التكرارية",
    "attention":              "الانتباه والتركيز",
    "hyperactivity":          "فرط الحركة",
    "impulsivity":            "الاندفاعية",
    "executive_function":     "الوظائف التنفيذية",
    "expressive_language":    "اللغة التعبيرية",
    "receptive_language":     "اللغة الاستقبالية",
    "articulation":           "النطق ومخارج الحروف",
    "pragmatic_language":     "اللغة البراغماتية الاجتماعية",
    "sensory_reactivity":     "الاستجابة الحسية",
    "vestibular":             "الجهاز الدهليزي (التوازن والحركة)",
    "proprioceptive":         "الإحساس العميق بالجسم",
    "emotional_regulation":   "التنظيم الانفعالي",
    "externalizing":          "السلوكيات الخارجية (العدوان والتمرد)",
    "internalizing":          "السلوكيات الداخلية (القلق والانسحاب)",
    "academic_skills":        "المهارات الأكاديمية",
}


def _get_child_age_months(session: models.AssessmentSession) -> int:
    """Return child age in months, using session field or falling back to age_band estimate."""
    stored = getattr(session, "child_age_months", None)
    if stored is not None and isinstance(stored, int) and stored > 0:
        return stored
    # Conservative estimate: use midpoint of the age_band range
    return 42 if session.age_band == "0-6" else 108


def _weighted_average(points_weights: List[tuple]) -> float:
    """Compute weighted average from list of (points, weight) tuples."""
    total_weight = sum(w for _, w in points_weights)
    if total_weight == 0:
        return 0.0
    return round(sum(p * w for p, w in points_weights) / total_weight, 2)


def evaluate_rules(
    session: models.AssessmentSession,
    responses: List[models.Response]
) -> Dict[str, Any]:
    """
    Full rule-based evaluation pipeline.

    Returns:
        domain_scores          — weighted avg concern 0-100 per domain
        severity_levels        — Level 1-5 + translated label per domain
        active_specialties     — triggered + onboarding specialties
        discrepancies          — cross-informant flags with rationale
        strengths              — domains with low scores (clinical strengths)
        priority_tier          — 'Priority 1' | 'Priority 2' | 'Priority 3'
        priority_rationale_ar  — Arabic rationale string
    """
    q_lookup = {q["id"]: q for q in QUESTION_BANK}
    child_age_months = _get_child_age_months(session)

    # ── Stage 1: Accumulate weighted scores per domain & informant ────────────
    # Structure: {domain: {informant: [(points, weight), ...]}}
    domain_by_informant: Dict[str, Dict[str, List[tuple]]] = {}
    # Global (all informants combined): {domain: [(points, weight)]}
    domain_global: Dict[str, List[tuple]] = {}

    for resp in responses:
        q = q_lookup.get(resp.question_id)
        if not q:
            continue

        weight = float(q.get("weight", 1.0))
        points = float(resp.points)
        informant = resp.informant

        for domain in q.get("domain_tags", []):
            domain_global.setdefault(domain, []).append((points, weight))
            domain_by_informant.setdefault(domain, {})
            domain_by_informant[domain].setdefault(informant, []).append((points, weight))

    # ── Stage 2: Compute weighted averages ────────────────────────────────────
    avg_domain_scores: Dict[str, float] = {
        domain: _weighted_average(pw_list)
        for domain, pw_list in domain_global.items()
    }

    avg_domain_by_informant: Dict[str, Dict[str, float]] = {}
    for domain, inf_dict in domain_by_informant.items():
        avg_domain_by_informant[domain] = {
            inf: _weighted_average(pw_list)
            for inf, pw_list in inf_dict.items()
        }

    # ── Stage 3: Trigger specialties ─────────────────────────────────────────
    triggered_specialties = set(session.onboarding_specialties or [])

    for spec, config in RULES_CONFIG.get("triggers", {}).items():
        # Age gate check (fixed bug: was min_age_years, now uses min_age_months)
        min_age_months = config.get("min_age_months")
        if min_age_months is not None and child_age_months < min_age_months:
            continue

        # Age-band required (e.g., learning_disabilities only for 6-18)
        if "age_band_required" in config and session.age_band != config["age_band_required"]:
            continue

        trigger_domains = config.get("domains", [])
        threshold = float(config.get("threshold", 60.0))
        any_threshold = float(config.get("any_domain_threshold", threshold + 15.0))

        # Average threshold: mean of all trigger domains exceeds threshold
        domain_scores_for_spec = [
            avg_domain_scores[d] for d in trigger_domains if d in avg_domain_scores
        ]
        if not domain_scores_for_spec:
            continue

        avg_score = sum(domain_scores_for_spec) / len(domain_scores_for_spec)
        max_single_domain = max(domain_scores_for_spec)

        if avg_score >= threshold or max_single_domain >= any_threshold:
            triggered_specialties.add(spec)

    # ── Stage 4: Severity levels per domain ──────────────────────────────────
    bands = RULES_CONFIG.get("severity_bands", [])
    severity_levels: Dict[str, Dict[str, Any]] = {}

    for domain, score in avg_domain_scores.items():
        matched_band = bands[-1]
        for band in bands:
            if score <= band["max_score"]:
                matched_band = band
                break
        severity_levels[domain] = {
            "score": score,
            "level": matched_band["level"],
            "name_en": matched_band["name_en"],
            "name_ar": matched_band["name_ar"],
            "domain_ar": DOMAIN_TRANSLATIONS_AR.get(domain, domain),
        }

    # ── Stage 5: Cross-informant discrepancy detection ────────────────────────
    threshold_delta = float(RULES_CONFIG.get("discrepancy", {}).get("threshold_delta", 25.0))
    rationale_template = RULES_CONFIG.get("discrepancy", {}).get(
        "rationale_template_ar",
        "فجوة تقييمية بمقدار {delta} نقطة بين الوالدين والمعلم في مجال ({domain_ar})"
    )
    discrepancy_flags = []

    for domain, inf_scores in avg_domain_by_informant.items():
        if "parent" in inf_scores and "teacher" in inf_scores:
            p_score = inf_scores["parent"]
            t_score = inf_scores["teacher"]
            delta = abs(p_score - t_score)
            if delta >= threshold_delta:
                domain_ar = DOMAIN_TRANSLATIONS_AR.get(domain, domain)
                discrepancy_flags.append({
                    "domain": domain,
                    "domain_ar": domain_ar,
                    "parent_score": p_score,
                    "teacher_score": t_score,
                    "delta": round(delta, 1),
                    "higher_informant": "parent" if p_score > t_score else "teacher",
                    "rationale_ar": rationale_template.format(
                        delta=round(delta, 1),
                        domain_ar=domain_ar
                    ),
                })

    # ── Stage 6: Strengths profile ────────────────────────────────────────────
    strengths_threshold = float(RULES_CONFIG.get("strengths_threshold", 25.0))
    strengths = [
        {
            "domain": domain,
            "domain_ar": DOMAIN_TRANSLATIONS_AR.get(domain, domain),
            "score": score,
        }
        for domain, score in avg_domain_scores.items()
        if score <= strengths_threshold
    ]

    # ── Stage 7: Priority matrix ──────────────────────────────────────────────
    l5_domains = [d for d, s in severity_levels.items() if s["level"] == 5]
    l4_domains = [d for d, s in severity_levels.items() if s["level"] == 4]
    l3_domains = [d for d, s in severity_levels.items() if s["level"] == 3]

    priority_cfg = RULES_CONFIG.get("priority", {})
    t1 = priority_cfg.get("tier_1_conditions", {})
    t2 = priority_cfg.get("tier_2_conditions", {})

    safety_flag = any(
        resp.question_id == "q_behavior_05" and resp.points >= 50.0
        for resp in responses
    )

    priority_tier = "Priority 3"
    priority_rationale_ar: List[str] = []

    tier1_triggered = (
        len(l5_domains) >= t1.get("min_level5_domains", 1)
        or len(l4_domains) >= t1.get("min_level4_domains", 2)
        or (safety_flag and t1.get("specialist_safety_flag", True))
    )

    tier2_triggered = (
        len(l4_domains) >= t2.get("min_level4_domains", 1)
        or len(l3_domains) >= t2.get("min_level3_domains", 2)
        or (len(discrepancy_flags) > 0 and t2.get("discrepancy_flag", True))
    )

    if tier1_triggered:
        priority_tier = "Priority 1"
        if l5_domains:
            translated = [DOMAIN_TRANSLATIONS_AR.get(d, d) for d in l5_domains]
            priority_rationale_ar.append(
                f"مستوى شديد جداً (Level 5) في: {', '.join(translated)}"
            )
        if len(l4_domains) >= 2:
            translated = [DOMAIN_TRANSLATIONS_AR.get(d, d) for d in l4_domains]
            priority_rationale_ar.append(
                f"مستويات شديدة متعددة (Level 4) في: {', '.join(translated)}"
            )
        if safety_flag:
            priority_rationale_ar.append(
                "مؤشر أمان سريري يستوجب متابعة عاجلة من الأخصائي"
            )

    elif tier2_triggered:
        priority_tier = "Priority 2"
        if l4_domains:
            translated = [DOMAIN_TRANSLATIONS_AR.get(d, d) for d in l4_domains]
            priority_rationale_ar.append(
                f"مستوى شديد (Level 4) في: {', '.join(translated)}"
            )
        if l3_domains:
            translated = [DOMAIN_TRANSLATIONS_AR.get(d, d) for d in l3_domains]
            priority_rationale_ar.append(
                f"مستوى متوسط (Level 3) في: {', '.join(translated)}"
            )
        for flag in discrepancy_flags:
            priority_rationale_ar.append(flag["rationale_ar"])

    else:
        priority_rationale_ar.append(
            "جميع المجالات ضمن النطاق البسيط (Level 1-2) ولا توجد فجوات تقييمية مثيرة للقلق."
        )

    return {
        "domain_scores": avg_domain_scores,
        "severity_levels": severity_levels,
        "active_specialties": list(triggered_specialties),
        "discrepancies": discrepancy_flags,
        "strengths": strengths,
        "priority_tier": priority_tier,
        "priority_rationale_ar": " • ".join(priority_rationale_ar),
    }
