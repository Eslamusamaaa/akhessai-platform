import pytest
import sys
import os

# Add backend to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from rules.evaluator import evaluate_rules

@pytest.fixture
def base_session():
    # Helper to construct dummy sessions
    return models.AssessmentSession(
        age_band="0-6",
        onboarding_specialties=["speech_language"],
        active_specialties=["speech_language"]
    )

def test_no_responses_defaults(base_session):
    results = evaluate_rules(base_session, [])
    assert results["domain_scores"] == {}
    assert results["priority_tier"] == "Priority 3"
    assert "جميع المجالات ضمن النطاق البسيط" in results["priority_rationale_ar"]

def test_autism_trigger_due_to_score(base_session):
    # Autism triggers when social_communication >= 60
    # Let's create responses for q_core_01 (social_communication) with high concern (100.0)
    resp = models.Response(
        question_id="q_core_01",
        informant="parent",
        selected_options=["أبدًا"],
        points=100.0
    )
    
    results = evaluate_rules(base_session, [resp])
    # Core screener question has social_communication domain_tag
    assert results["domain_scores"]["social_communication"] == 100.0
    assert "autism" in results["active_specialties"]
    assert "speech_language" in results["active_specialties"] # Kept from onboarding
    
    # Check severity mapping: 100.0 -> Level 5 (Severe)
    assert results["severity_levels"]["social_communication"]["level"] == 5
    assert results["priority_tier"] == "Priority 1"

def test_severity_levels_mapping(base_session):
    # 68.0 points should fall under Level 4 (60 to 79.99)
    resp = models.Response(
        question_id="q_core_01",
        informant="parent",
        selected_options=["أحيانًا"],
        points=68.0
    )
    results = evaluate_rules(base_session, [resp])
    assert results["severity_levels"]["social_communication"]["level"] == 4
    assert results["severity_levels"]["social_communication"]["name_en"] == "Significant"

def test_cross_informant_discrepancy_flag(base_session):
    # Parent and teacher evaluate attention
    # Parent gives 80 points, Teacher gives 30 points.
    # Delta = 50.0 (which is >= 25.0 threshold) -> Priority 2 evaluation promoted
    resp_parent = models.Response(
        question_id="q_core_02",  # attention
        informant="parent",
        points=80.0
    )
    resp_teacher = models.Response(
        question_id="q_core_08",  # attention
        informant="teacher",
        points=30.0
    )
    
    results = evaluate_rules(base_session, [resp_parent, resp_teacher])
    # The average score for attention is (80 + 30)/2 = 55.0 (Moderate - Level 3)
    assert results["domain_scores"]["attention"] == 55.0
    assert len(results["discrepancies"]) == 1
    assert results["discrepancies"][0]["delta"] == 50.0
    # Promoted to Priority 2 due to discrepancy (even though Level 3 alone also triggers Priority 2)
    assert results["priority_tier"] == "Priority 2"
    assert "فجوة تقييمية" in results["priority_rationale_ar"]

def test_priority_1_multiple_level_4(base_session):
    # Multiple Level 4 domains should trigger Priority 1
    # Let's create two Level 4 domains: social_communication (70.0) and attention (70.0)
    resp1 = models.Response(
        question_id="q_core_01",  # social_communication
        informant="parent",
        points=70.0
    )
    resp2 = models.Response(
        question_id="q_core_02",  # attention
        informant="parent",
        points=70.0
    )
    
    results = evaluate_rules(base_session, [resp1, resp2])
    assert results["severity_levels"]["social_communication"]["level"] == 4
    assert results["severity_levels"]["attention"]["level"] == 4
    assert results["priority_tier"] == "Priority 1"
