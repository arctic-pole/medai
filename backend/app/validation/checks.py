"""output_validator.checks, in the spec's own order (1-10). Each check is a standalone
function so the mapping from spec item to code is auditable 1:1, even where a few share
underlying logic. None of these are exhaustive clinical judgment — they are the deterministic,
checkable subset of "does this output look safe to show a user", per the spec's own list.
"""

import re

from app.reasoning.checks import check_grounding, check_uncertainty_language, ClinicalReasoningViolation
from app.reasoning.schema import Assessment, EvidencePackage
from app.safety.schema import SafetyEvaluation
from app.validation.schema import ValidationFailure

_STATUS_VALUES = {"normal", "caution", "urgent", "emergency"}
_CONFIDENCE_VALUES = {"low", "moderate", "high"}

# dangerous_language: phrasing that falsely reassures the user out of seeking care — distinct
# from reasoning.checks' forbidden phrases, which are about false *certainty*, not false safety.
_DANGEROUS_REASSURANCE_PHRASES = [
    "you don't need to see a doctor",
    "no need for medical",
    "this is not an emergency",
    "nothing to worry about",
    "you're fine",
]

# prescription_like_directives: dosage-shaped or directive prescribing language.
# prohibited.hard_coded_invented_drug_dosages / clinical_reasoner.must_not.invent_contraindications_or_doses.
_DOSAGE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|ml|g|iu)\b", re.IGNORECASE)
_PRESCRIPTIVE_PHRASES = ["i prescribe", "you should take", "take this medication", "administer"]


def check_schema_compliance(assessment: Assessment) -> ValidationFailure | None:
    """1. schema_compliance — Assessment is already pydantic-validated at construction time
    (Phase 6's structured_generate), so this re-checks the parts pydantic's type system alone
    doesn't enforce: non-empty narrative content, and status/confidence within the exact
    response_states/confidence vocabulary (belt-and-braces against a schema drifting later)."""

    if assessment.status not in _STATUS_VALUES:
        return ValidationFailure(check="schema_compliance", detail=f"status {assessment.status!r} is not a valid response state")
    if assessment.confidence not in _CONFIDENCE_VALUES:
        return ValidationFailure(check="schema_compliance", detail=f"confidence {assessment.confidence!r} is not valid")
    if not assessment.summary.strip():
        return ValidationFailure(check="schema_compliance", detail="summary is empty")
    return None


def check_unsupported_claims(assessment: Assessment, evidence_package: EvidencePackage) -> ValidationFailure | None:
    """2. unsupported_claims — every cited evidence reference must be a source actually given
    to the reasoner (reuses reasoning.checks.check_grounding as the official gate)."""

    try:
        check_grounding(assessment, evidence_package)
    except ClinicalReasoningViolation as exc:
        return ValidationFailure(check="unsupported_claims", detail=str(exc))
    return None


def check_evidence_availability(assessment: Assessment) -> ValidationFailure | None:
    """3. evidence_availability — if the assessment makes substantive clinical claims
    (possible explanations, treatment options, or medication information), at least one
    evidence citation must back them up."""

    has_claims = bool(assessment.possible_explanations or assessment.treatment_options or assessment.medication_information)
    if has_claims and not assessment.evidence:
        return ValidationFailure(
            check="evidence_availability",
            detail="assessment makes substantive claims (explanations/treatments/medication info) with no evidence citations",
        )
    return None


def check_dangerous_language(assessment: Assessment) -> ValidationFailure | None:
    """4. dangerous_language — phrasing that could dissuade a user from seeking care."""

    haystack = " ".join([assessment.summary, *assessment.warnings, *assessment.recommended_next_steps]).lower()
    for phrase in _DANGEROUS_REASSURANCE_PHRASES:
        if phrase in haystack:
            return ValidationFailure(check="dangerous_language", detail=f'contains dangerous reassurance: "{phrase}"')
    return None


def check_prescription_like_directives(assessment: Assessment) -> ValidationFailure | None:
    """5. prescription_like_directives — dosage-shaped or directive prescribing language.
    prohibited.hard_coded_invented_drug_dosages: this is a prototype, not a prescriber."""

    haystack = " ".join([assessment.summary, *assessment.medication_information, *assessment.treatment_options])
    if _DOSAGE_PATTERN.search(haystack):
        return ValidationFailure(check="prescription_like_directives", detail="contains a dosage-shaped value (e.g. '200mg')")
    lowered = haystack.lower()
    for phrase in _PRESCRIPTIVE_PHRASES:
        if phrase in lowered:
            return ValidationFailure(check="prescription_like_directives", detail=f'contains prescriptive phrasing: "{phrase}"')
    return None


def check_contradictions(assessment: Assessment) -> ValidationFailure | None:
    """6. contradictions — internal consistency between status and escalation."""

    if assessment.status == "normal" and assessment.escalation:
        return ValidationFailure(check="contradictions", detail="status is 'normal' but an escalation is also present")
    if assessment.status in ("urgent", "emergency") and not assessment.escalation:
        return ValidationFailure(
            check="contradictions", detail=f"status is {assessment.status!r} but no escalation guidance is present"
        )
    return None


def check_safety_engine_result(assessment: Assessment, safety_evaluation: SafetyEvaluation) -> ValidationFailure | None:
    """7. safety_engine_result — safety_engine.rule: "Hard safety rules take precedence over
    LLM output; LLM cannot override them." If the deterministic engine says ESCALATE, the
    assessment must reflect that regardless of what the LLM itself concluded."""

    if safety_evaluation.decision == "ESCALATE" and assessment.status not in ("urgent", "emergency"):
        return ValidationFailure(
            check="safety_engine_result",
            detail=f"safety_engine decided ESCALATE but assessment status is {assessment.status!r}",
        )
    return None


def check_medication_validation(assessment: Assessment, safety_evaluation: SafetyEvaluation) -> ValidationFailure | None:
    """8. medication_validation — a medication the medication-safety pipeline BLOCKED must not
    appear as a recommended option in the output."""

    blocked_names = {f.candidate_name.lower() for f in safety_evaluation.medication_findings if f.decision == "BLOCKED"}
    if not blocked_names:
        return None
    mentioned = " ".join([*assessment.medication_information, *assessment.treatment_options]).lower()
    for name in blocked_names:
        if name in mentioned:
            return ValidationFailure(
                check="medication_validation", detail=f"assessment mentions '{name}', which medication safety BLOCKED"
            )
    return None


def check_uncertainty_requirements(assessment: Assessment) -> ValidationFailure | None:
    """9. uncertainty_requirements — reuses reasoning.checks.check_uncertainty_language as the
    official gate, plus a confidence/evidence consistency check."""

    try:
        check_uncertainty_language(assessment)
    except ClinicalReasoningViolation as exc:
        return ValidationFailure(check="uncertainty_requirements", detail=str(exc))
    if assessment.confidence == "high" and not assessment.evidence:
        return ValidationFailure(check="uncertainty_requirements", detail="confidence is 'high' with no supporting evidence")
    return None


def check_escalation_requirements(assessment: Assessment) -> ValidationFailure | None:
    """10. escalation_requirements — an 'emergency' status must carry actual escalation text."""

    if assessment.status == "emergency" and not (assessment.escalation and assessment.escalation.strip()):
        return ValidationFailure(check="escalation_requirements", detail="status is 'emergency' but escalation text is empty")
    return None


def run_all_checks(
    assessment: Assessment, evidence_package: EvidencePackage, safety_evaluation: SafetyEvaluation
) -> list[ValidationFailure]:
    checks = [
        check_schema_compliance(assessment),
        check_unsupported_claims(assessment, evidence_package),
        check_evidence_availability(assessment),
        check_dangerous_language(assessment),
        check_prescription_like_directives(assessment),
        check_contradictions(assessment),
        check_safety_engine_result(assessment, safety_evaluation),
        check_medication_validation(assessment, safety_evaluation),
        check_uncertainty_requirements(assessment),
        check_escalation_requirements(assessment),
    ]
    return [failure for failure in checks if failure is not None]
