"""Phase 14 (evaluation): testing.safety_adversarial, mapped 1:1 to the spec's own 10
categories, so the mapping from requirement to test is auditable. Most categories already have
real coverage from the phase that built the corresponding mechanism — this file references that
coverage explicitly by file/test name rather than duplicating it, and adds new tests only for
the categories (or specific angles of a category) that had a genuine gap.

Categories and where each is actually covered:
 1. emergency_symptoms         -> tests/unit/test_vital_rules.py, test_conversation_flow.py
                                   (test_send_message_assessment_surfaces_escalation_...),
                                   test_privacy.py's live-verified Phase 9/10 ESCALATE chain.
 2. missing_data               -> tests/unit/test_conversation_manager.py,
                                   test_missing_info (identify_missing_info tiers).
 3. contradictory_data         -> NEW, this file.
 4. invalid_vitals             -> tests/unit/test_vital_validation.py.
 5. medication_conflicts       -> tests/integration/test_medication_safety.py.
 6. allergies                  -> tests/integration/test_medication_safety.py (BLOCKED path).
 7. hallucination_attempts     -> tests/unit/test_reasoning_checks.py (check_grounding), plus
                                   NEW cases here for the explicit UNKNOWN/INSUFFICIENT_
                                   INFORMATION framing testing.hallucination_tests calls for.
 8. prompt_injection           -> tests/unit/test_prompt_injection.py (Phase 13).
 9. malformed_AI_output        -> NEW, this file.
10. insufficient_evidence      -> NEW, this file (evidence_availability check + fail-closed).
"""

import uuid
from datetime import datetime, timezone

import pydantic

from app.providers.llm.base import LLMProvider
from app.reasoning.schema import Assessment, EvidencePackage, EvidenceReference
from app.safety.schema import SafetyEvaluation
from app.schemas.evidence import EvidenceItem
from app.validation.validator import SAFE_FALLBACK, get_validated_output
from tests.fakes import FakeReasoningLLMProvider, empty_patient_state


def _evidence_item(content: str = "Tension headaches usually resolve with rest.") -> EvidenceItem:
    return EvidenceItem(
        content=content,
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


# --- 3. contradictory_data ------------------------------------------------------------------


async def test_contradictory_vitals_readings_are_both_kept_not_silently_resolved(client, db_session) -> None:
    """Two contradictory heart-rate readings close together (60 then 180 bpm) — the system's
    real, existing answer to "contradictory data" is vital_system's own design: never silently
    pick one and discard the other. Both are recorded in the audit-trail `measurements` table
    (Phase 9); only the most recent (by timestamp, not insertion order) becomes the current
    `vitals` snapshot the safety engine and reasoner see. This is a deliberate, disclosed
    handling strategy, not silent conflict resolution — verified here end to end over real
    HTTP, not just described."""

    from sqlalchemy import select

    from app.db.models import Measurement, Patient, User, Vital

    resp = await client.post(
        "/auth/register", json={"email": "adversarial-contradictory@example.com", "password": "s3curePassw0rd"}
    )
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    await client.post("/vitals", headers=headers, json={"type": "heart_rate", "value": 60, "unit": "bpm"})
    await client.post("/vitals", headers=headers, json={"type": "heart_rate", "value": 180, "unit": "bpm"})

    user = (
        await db_session.execute(select(User).where(User.email == "adversarial-contradictory@example.com"))
    ).scalar_one()
    patient = (await db_session.execute(select(Patient).where(Patient.user_id == user.id))).scalar_one()

    all_measurements = (
        await db_session.execute(select(Measurement).where(Measurement.patient_id == patient.id))
    ).scalars().all()
    assert len(all_measurements) == 2  # neither reading was discarded

    snapshot = await db_session.get(Vital, (patient.id, "heart_rate"))
    assert snapshot is not None  # a definite current value exists — the system doesn't refuse
    assert snapshot.value == 180  # to have an opinion just because the readings conflicted; it
    # uses the documented newest-timestamp-wins rule
    # (test_newer_reading_updates_snapshot_older_backdated_one_does_not in test_vitals.py covers
    # the exact ordering rule this relies on).


async def test_contradictory_assessment_status_and_escalation_is_rejected_not_shown() -> None:
    """A different angle on "contradictory": the LLM's own output can internally contradict
    itself (status='normal' but escalation text present, or 'emergency' with none) —
    check_contradictions (output_validator check 6) exists specifically to catch this before
    it reaches a user. Verified here as a distinct, explicit adversarial case."""

    from app.validation.checks import check_contradictions

    normal_but_escalating = Assessment(
        status="normal", summary="You seem fine.", confidence="low", escalation="Go to the ER immediately."
    )
    assert check_contradictions(normal_but_escalating) is not None

    emergency_but_silent = Assessment(status="emergency", summary="This is serious.", confidence="low")
    assert check_contradictions(emergency_but_silent) is not None


# --- 7. hallucination_attempts (UNKNOWN/INSUFFICIENT_INFORMATION framing) -------------------


async def test_hallucination_attempt_is_corrected_then_falls_back_to_safe_unknown_response() -> None:
    """testing.hallucination_tests: "Cases where correct answer is UNKNOWN /
    INSUFFICIENT_INFORMATION / SEEK_PROFESSIONAL_EVALUATION." With zero retrieved evidence, an
    LLM that nonetheless states confident explanations is hallucinating by definition — this
    must be rejected (check_evidence_availability) and, if the LLM can't stop doing it within
    the correction budget, resolve to SAFE_FALLBACK's own "insufficient information" framing —
    never released as if it were a grounded answer."""

    package = EvidencePackage(patient_state=empty_patient_state())  # no retrieved evidence at all
    hallucinating_1 = Assessment(
        status="caution",
        summary="This is very likely appendicitis.",
        possible_explanations=["Appendicitis"],
        confidence="moderate",
    )
    hallucinating_2 = Assessment(
        status="caution",
        summary="This is very likely a migraine.",
        possible_explanations=["Migraine"],
        confidence="moderate",
    )
    llm = FakeReasoningLLMProvider([hallucinating_1, hallucinating_2])

    result = await get_validated_output(llm, package, _no_findings(), max_correction_attempts=1)

    assert result == SAFE_FALLBACK
    assert "insufficient information" in result.summary.lower()
    assert result.recommended_next_steps  # SEEK_PROFESSIONAL_EVALUATION-shaped guidance present


async def test_a_properly_hedged_response_with_no_evidence_is_accepted_not_penalized() -> None:
    """The other side of the same coin: correctly saying "I don't know" with no evidence and no
    substantive claims must NOT be rejected just for lacking citations — evidence_availability
    only requires citations when actual claims are made."""

    package = EvidencePackage(patient_state=empty_patient_state())
    honest = Assessment(
        status="caution",
        summary="There is not enough information here to identify a likely cause.",
        confidence="low",
        unknown_information=["symptom details", "vital signs", "medical history"],
        recommended_next_steps=["Seek an in-person professional evaluation."],
    )
    llm = FakeReasoningLLMProvider([honest])

    result = await get_validated_output(llm, package, _no_findings())

    assert result is honest  # accepted on the first attempt — no correction needed


# --- 9. malformed_AI_output ------------------------------------------------------------------


class _MalformedOutputLLMProvider(LLMProvider):
    """Simulates the real failure mode of app/providers/llm/gemini_provider.py's
    `schema.model_validate_json(interaction.output_text)` when the model returns text that
    doesn't parse into the Assessment schema at all — a genuine pydantic.ValidationError, not a
    schema-valid-but-ungrounded response (that's the hallucination case above, a different
    failure mode)."""

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return "not used"

    async def structured_generate(self, prompt: str, schema, *, system: str | None = None):
        try:
            schema.model_validate({"this": "does not match the schema at all"})
        except pydantic.ValidationError:
            raise
        raise AssertionError("expected model_validate to raise for a deliberately malformed payload")

    async def stream(self, prompt: str, *, system: str | None = None):
        raise NotImplementedError
        yield  # pragma: no cover


async def test_malformed_ai_output_fails_closed_to_safe_fallback_not_a_crash() -> None:
    package = EvidencePackage(patient_state=empty_patient_state())
    llm = _MalformedOutputLLMProvider()

    result = await get_validated_output(llm, package, _no_findings())

    assert result == SAFE_FALLBACK


# --- 10. insufficient_evidence ----------------------------------------------------------------


async def test_insufficient_evidence_with_substantive_claims_triggers_correction() -> None:
    """A more targeted version of the hallucination test above: isolates exactly the
    evidence_availability check (output_validator check 3), rather than the full
    correction-exhaustion path."""

    from app.validation.checks import check_evidence_availability

    unsupported = Assessment(
        status="caution",
        summary="Likely a tension headache.",
        possible_explanations=["Tension headache"],
        confidence="low",
        evidence=[],  # no citations at all
    )
    failure = check_evidence_availability(unsupported)
    assert failure is not None
    assert failure.check == "evidence_availability"


async def test_insufficient_evidence_assessment_with_real_evidence_present_is_fine() -> None:
    """Control case: the same kind of claim, but genuinely backed by a citation, must not be
    flagged — confirms the check above isn't just rejecting all claims."""

    from app.validation.checks import check_evidence_availability

    item = _evidence_item()
    supported = Assessment(
        status="caution",
        summary="Likely a tension headache.",
        possible_explanations=["Tension headache"],
        confidence="low",
        evidence=[EvidenceReference(source_id=item.source_id, note="supports it")],
    )
    assert check_evidence_availability(supported) is None
