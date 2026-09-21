import uuid
from datetime import datetime, timezone

import pytest

from app.reasoning.reasoner import generate_assessment
from app.reasoning.schema import Assessment, EvidencePackage, EvidenceReference
from app.schemas.evidence import EvidenceItem
from tests.fakes import FakeReasoningLLMProvider, empty_patient_state


def _evidence_item() -> EvidenceItem:
    return EvidenceItem(
        content="Tension headaches are common and usually resolve with rest.",
        similarity=0.8,
        source_id=uuid.uuid4(),
        title="Headache",
        publisher="MedlinePlus",
        url="https://medlineplus.gov/headache.html",
        source_type="government_health_guidance",
        version=1,
        retrieval_date=datetime.now(timezone.utc),
    )


async def test_generate_assessment_returns_valid_grounded_result() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    good = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports the summary")],
    )
    llm = FakeReasoningLLMProvider([good])

    result = await generate_assessment(llm, package)

    assert result.status == "caution"
    assert llm.call_count == 1


async def test_generate_assessment_retries_once_after_ungrounded_result_then_succeeds() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    bad = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=uuid.uuid4(), note="invented")],
    )
    good = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports the summary")],
    )
    llm = FakeReasoningLLMProvider([bad, good])

    result = await generate_assessment(llm, package, max_attempts=2)

    assert result is good
    assert llm.call_count == 2


async def test_generate_assessment_raises_after_exhausting_retries() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    bad = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=uuid.uuid4(), note="invented")],
    )
    llm = FakeReasoningLLMProvider([bad, bad])

    with pytest.raises(Exception):
        await generate_assessment(llm, package, max_attempts=2)

    assert llm.call_count == 2
