import uuid
from datetime import datetime, timezone

from app.reasoning.schema import Assessment, EvidencePackage, EvidenceReference
from app.safety.schema import SafetyEvaluation
from app.schemas.evidence import EvidenceItem
from app.validation.validator import SAFE_FALLBACK, get_validated_output
from tests.fakes import FakeReasoningLLMProvider, NotConfiguredLLMProvider, empty_patient_state


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


def _no_findings() -> SafetyEvaluation:
    return SafetyEvaluation(decision="PASS")


async def test_returns_first_assessment_when_it_passes_all_checks() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    good = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports it")],
    )
    llm = FakeReasoningLLMProvider([good])

    result = await get_validated_output(llm, package, _no_findings())

    assert result is good
    assert llm.call_count == 1


async def test_corrects_once_then_returns_the_fixed_assessment() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    bad = Assessment(status="normal", summary="You're fine.", confidence="low", escalation="Go to the ER")
    good = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports it")],
    )
    llm = FakeReasoningLLMProvider([bad, good])

    result = await get_validated_output(llm, package, _no_findings(), max_correction_attempts=1)

    assert result is good
    assert llm.call_count == 2


async def test_falls_back_to_safe_response_after_exhausting_corrections() -> None:
    package = EvidencePackage(patient_state=empty_patient_state())
    bad1 = Assessment(status="normal", summary="You're fine.", confidence="low", escalation="Go to the ER")
    bad2 = Assessment(status="normal", summary="Still fine.", confidence="low", escalation="Go to the ER")
    llm = FakeReasoningLLMProvider([bad1, bad2])

    result = await get_validated_output(llm, package, _no_findings(), max_correction_attempts=1)

    assert result == SAFE_FALLBACK


async def test_fails_closed_to_safe_fallback_when_generation_itself_errors() -> None:
    package = EvidencePackage(patient_state=empty_patient_state())

    result = await get_validated_output(NotConfiguredLLMProvider(), package, _no_findings())

    assert result == SAFE_FALLBACK


async def test_escalation_status_mismatch_triggers_correction() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    ignores_safety = Assessment(status="caution", summary="Seems mild.", confidence="low")
    correct = Assessment(
        status="emergency", summary="This requires urgent attention.", confidence="low", escalation="Seek emergency care now."
    )
    llm = FakeReasoningLLMProvider([ignores_safety, correct])
    escalated_safety = SafetyEvaluation(decision="ESCALATE")

    result = await get_validated_output(llm, package, escalated_safety, max_correction_attempts=1)

    assert result is correct
