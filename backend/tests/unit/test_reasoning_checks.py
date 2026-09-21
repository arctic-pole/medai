import uuid
from datetime import datetime, timezone

import pytest

from app.reasoning.checks import ClinicalReasoningViolation, check_grounding, check_uncertainty_language
from app.reasoning.schema import Assessment, EvidencePackage, EvidenceReference
from app.schemas.evidence import EvidenceItem
from tests.fakes import empty_patient_state


def _evidence_item(source_id: uuid.UUID | None = None) -> EvidenceItem:
    return EvidenceItem(
        content="Tension headaches are common and usually resolve with rest.",
        similarity=0.8,
        source_id=source_id or uuid.uuid4(),
        title="Headache",
        publisher="MedlinePlus",
        url="https://medlineplus.gov/headache.html",
        source_type="government_health_guidance",
        version=1,
        retrieval_date=datetime.now(timezone.utc),
    )


def _package(evidence: list[EvidenceItem]) -> EvidencePackage:
    return EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=evidence)


def _assessment(**overrides) -> Assessment:
    base = dict(status="caution", summary="Possible explanations include a tension headache.", confidence="low")
    base.update(overrides)
    return Assessment(**base)


def test_grounding_passes_when_cited_source_was_actually_retrieved() -> None:
    item = _evidence_item()
    package = _package([item])
    assessment = _assessment(evidence=[EvidenceReference(source_id=item.source_id, note="supports the summary")])

    check_grounding(assessment, package)  # should not raise


def test_grounding_rejects_invented_source_id() -> None:
    package = _package([_evidence_item()])
    assessment = _assessment(evidence=[EvidenceReference(source_id=uuid.uuid4(), note="made up")])

    with pytest.raises(ClinicalReasoningViolation):
        check_grounding(assessment, package)


@pytest.mark.parametrize("phrase", ["definitely", "This is a diagnosis", "100% certain"])
def test_uncertainty_language_rejects_forbidden_absolute_claims(phrase: str) -> None:
    assessment = _assessment(summary=f"{phrase} the patient has a tension headache.")

    with pytest.raises(ClinicalReasoningViolation):
        check_uncertainty_language(assessment)


def test_uncertainty_language_allows_hedged_phrasing() -> None:
    assessment = _assessment(summary="Possible explanations include a tension headache.")
    check_uncertainty_language(assessment)  # should not raise
