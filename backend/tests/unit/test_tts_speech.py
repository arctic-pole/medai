"""Behavioral half of "TTS never receives unvalidated text": synthesize_validated_response
always runs get_validated_output() first, and only ever hands TTS the text that function
actually returned — including SAFE_FALLBACK when validation fails, never the rejected content."""

import uuid
from datetime import datetime, timezone

from app.reasoning.schema import Assessment, EvidencePackage, EvidenceReference
from app.safety.schema import SafetyEvaluation
from app.schemas.evidence import EvidenceItem
from app.tts.speech import synthesize_validated_response
from app.validation.validator import SAFE_FALLBACK
from tests.fakes import FailingTTSProvider, FakeReasoningLLMProvider, FakeTTSProvider, empty_patient_state


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


async def test_successful_synthesis_speaks_the_validated_summary() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    good = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports it")],
    )
    llm = FakeReasoningLLMProvider([good])
    tts = FakeTTSProvider()

    assessment, audio = await synthesize_validated_response(tts, llm, package, _no_findings())

    assert assessment is good
    assert tts.synthesized_texts == [good.summary]
    assert audio == f"FAKE_AUDIO:{good.summary}".encode()


async def test_escalation_text_is_appended_to_what_is_spoken() -> None:
    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    emergency = Assessment(
        status="emergency",
        summary="This requires urgent attention.",
        confidence="low",
        escalation="Seek emergency care immediately.",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports it")],
    )
    llm = FakeReasoningLLMProvider([emergency])
    tts = FakeTTSProvider()

    await synthesize_validated_response(tts, llm, package, SafetyEvaluation(decision="ESCALATE"))

    assert tts.synthesized_texts == ["This requires urgent attention. Seek emergency care immediately."]


async def test_validator_rejection_means_safe_fallback_is_spoken_not_the_rejected_content() -> None:
    """The core safety property: an LLM output that fails validation must never reach TTS, even
    indirectly. Two bad attempts exhaust the correction budget, so get_validated_output()
    resolves to SAFE_FALLBACK — and that, not either rejected Assessment's text, is what must be
    spoken."""

    package = EvidencePackage(patient_state=empty_patient_state())
    dangerous1 = Assessment(status="normal", summary="You're totally fine, no need to worry.", confidence="low", escalation="Go to the ER")
    dangerous2 = Assessment(status="normal", summary="Still nothing to worry about.", confidence="low", escalation="Go to the ER")
    llm = FakeReasoningLLMProvider([dangerous1, dangerous2])
    tts = FakeTTSProvider()

    assessment, _audio = await synthesize_validated_response(tts, llm, package, _no_findings(), max_correction_attempts=1)

    assert assessment == SAFE_FALLBACK
    assert tts.synthesized_texts == [SAFE_FALLBACK.summary]
    assert "totally fine" not in tts.synthesized_texts[0]
    assert "Still nothing" not in tts.synthesized_texts[0]


async def test_tts_failure_propagates_but_the_assessment_was_already_validated() -> None:
    """Requirement: text remains available when TTS fails. synthesize_validated_response raises
    on a TTS-specific failure (so the caller can respond 503 for audio specifically), but
    get_validated_output() has already run by then — a caller that separately calls
    POST /assessment (as the mobile app does) still gets the text regardless of this failure;
    nothing here blocks or corrupts that independent path."""

    item = _evidence_item()
    package = EvidencePackage(patient_state=empty_patient_state(), retrieved_evidence=[item])
    good = Assessment(
        status="caution",
        summary="Possible explanations include a tension headache.",
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports it")],
    )
    llm = FakeReasoningLLMProvider([good])
    failing_tts = FailingTTSProvider()

    try:
        await synthesize_validated_response(failing_tts, llm, package, _no_findings())
        raised = False
    except Exception:
        raised = True

    assert raised, "a TTS engine failure must propagate, not be silently swallowed into fake audio"

    # The same inputs, re-run through get_validated_output() directly (what POST /assessment
    # does), still produce the real text — TTS failing does not corrupt or consume it.
    from app.validation.validator import get_validated_output

    llm2 = FakeReasoningLLMProvider([good])
    text_only_result = await get_validated_output(llm2, package, _no_findings())
    assert text_only_result is good
