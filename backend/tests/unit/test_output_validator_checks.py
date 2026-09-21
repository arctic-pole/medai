import uuid
from datetime import datetime, timezone

from app.reasoning.schema import Assessment, EvidencePackage, EvidenceReference
from app.safety.schema import MedicationCheckResult, SafetyEvaluation
from app.schemas.evidence import EvidenceItem
from app.validation.checks import (
    check_contradictions,
    check_dangerous_language,
    check_escalation_requirements,
    check_evidence_availability,
    check_medication_validation,
    check_prescription_like_directives,
    check_safety_engine_result,
    check_schema_compliance,
    check_uncertainty_requirements,
    check_unsupported_claims,
    run_all_checks,
)
from tests.fakes import empty_patient_state


def _evidence_item() -> EvidenceItem:
    return EvidenceItem(
        content="Tension headaches usually resolve with rest.",
        similarity=0.8,
        source_id=uuid.uuid4(),
        title="Headache",
        publisher="MedlinePlus",
        url="https://medlineplus.gov/headache.html",
        source_type="government_health_guidance",
        version=1,
        retrieval_date=datetime.now(timezone.utc),
    )


def _clean_assessment(**overrides) -> Assessment:
    base = dict(status="caution", summary="Possible explanations include a tension headache.", confidence="low")
    base.update(overrides)
    return Assessment(**base)


def _package(evidence: list[EvidenceItem] | None = None) -> EvidencePackage:
    return EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=evidence or [])


def _no_findings() -> SafetyEvaluation:
    return SafetyEvaluation(decision="PASS")


# 1. schema_compliance


def test_schema_compliance_rejects_empty_summary() -> None:
    assessment = _clean_assessment(summary="")
    assert check_schema_compliance(assessment) is not None


def test_schema_compliance_passes_clean_assessment() -> None:
    assert check_schema_compliance(_clean_assessment()) is None


# 2. unsupported_claims


def test_unsupported_claims_rejects_invented_evidence_id() -> None:
    package = _package([_evidence_item()])
    assessment = _clean_assessment(evidence=[EvidenceReference(source_id=uuid.uuid4(), note="made up")])
    assert check_unsupported_claims(assessment, package) is not None


def test_unsupported_claims_passes_real_citation() -> None:
    item = _evidence_item()
    package = _package([item])
    assessment = _clean_assessment(evidence=[EvidenceReference(source_id=item.source_id, note="supports it")])
    assert check_unsupported_claims(assessment, package) is None


# 3. evidence_availability


def test_evidence_availability_rejects_claims_without_evidence() -> None:
    assessment = _clean_assessment(possible_explanations=["tension headache"], evidence=[])
    assert check_evidence_availability(assessment) is not None


def test_evidence_availability_allows_pure_unknowns_with_no_evidence() -> None:
    assessment = _clean_assessment(unknown_information=["patient age"], evidence=[])
    assert check_evidence_availability(assessment) is None


# 4. dangerous_language


def test_dangerous_language_rejects_false_reassurance() -> None:
    assessment = _clean_assessment(summary="You're fine, nothing to worry about.")
    assert check_dangerous_language(assessment) is not None


def test_dangerous_language_passes_hedged_summary() -> None:
    assert check_dangerous_language(_clean_assessment()) is None


# 5. prescription_like_directives


def test_prescription_like_directives_rejects_dosage() -> None:
    assessment = _clean_assessment(medication_information=["Take 200mg twice daily"])
    assert check_prescription_like_directives(assessment) is not None


def test_prescription_like_directives_passes_clean_text() -> None:
    assert check_prescription_like_directives(_clean_assessment()) is None


# 6. contradictions


def test_contradictions_rejects_normal_with_escalation() -> None:
    assessment = _clean_assessment(status="normal", escalation="Go to the ER")
    assert check_contradictions(assessment) is not None


def test_contradictions_rejects_urgent_without_escalation() -> None:
    assessment = _clean_assessment(status="urgent", escalation=None)
    assert check_contradictions(assessment) is not None


def test_contradictions_passes_consistent_emergency() -> None:
    assessment = _clean_assessment(status="emergency", escalation="Seek emergency care immediately")
    assert check_contradictions(assessment) is None


# 7. safety_engine_result


def test_safety_engine_result_rejects_mismatched_status() -> None:
    assessment = _clean_assessment(status="caution")
    evaluation = SafetyEvaluation(decision="ESCALATE")
    assert check_safety_engine_result(assessment, evaluation) is not None


def test_safety_engine_result_passes_when_escalated_status_matches() -> None:
    assessment = _clean_assessment(status="emergency", escalation="Seek emergency care")
    evaluation = SafetyEvaluation(decision="ESCALATE")
    assert check_safety_engine_result(assessment, evaluation) is None


# 8. medication_validation


def test_medication_validation_rejects_blocked_medication_mentioned() -> None:
    assessment = _clean_assessment(medication_information=["Consider penicillin"])
    evaluation = SafetyEvaluation(
        decision="BLOCK",
        medication_findings=[MedicationCheckResult(candidate_name="penicillin", decision="BLOCKED", reasons=["allergy"])],
    )
    assert check_medication_validation(assessment, evaluation) is not None


def test_medication_validation_passes_when_no_blocked_medication_mentioned() -> None:
    assessment = _clean_assessment()
    evaluation = SafetyEvaluation(
        decision="BLOCK",
        medication_findings=[MedicationCheckResult(candidate_name="penicillin", decision="BLOCKED", reasons=["allergy"])],
    )
    assert check_medication_validation(assessment, evaluation) is None


# 9. uncertainty_requirements


def test_uncertainty_requirements_rejects_high_confidence_without_evidence() -> None:
    assessment = _clean_assessment(confidence="high", evidence=[])
    assert check_uncertainty_requirements(assessment) is not None


def test_uncertainty_requirements_rejects_forbidden_absolute_language() -> None:
    assessment = _clean_assessment(summary="This is definitely a tension headache.")
    assert check_uncertainty_requirements(assessment) is not None


# 10. escalation_requirements


def test_escalation_requirements_rejects_emergency_without_text() -> None:
    assessment = _clean_assessment(status="emergency", escalation=None)
    assert check_escalation_requirements(assessment) is not None


def test_escalation_requirements_passes_emergency_with_text() -> None:
    assessment = _clean_assessment(status="emergency", escalation="Call emergency services now.")
    assert check_escalation_requirements(assessment) is None


# aggregate


def test_run_all_checks_returns_no_failures_for_clean_assessment() -> None:
    assert run_all_checks(_clean_assessment(), _package(), _no_findings()) == []


def test_run_all_checks_collects_multiple_failures() -> None:
    assessment = _clean_assessment(status="normal", escalation="Go to the ER", summary="You're fine.")
    failures = run_all_checks(assessment, _package(), _no_findings())
    checks_failed = {f.check for f in failures}
    assert "contradictions" in checks_failed
    assert "dangerous_language" in checks_failed
