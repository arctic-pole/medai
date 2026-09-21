from app.reasoning.schema import Assessment, EvidencePackage

# uncertainty_language.forbidden, expanded into a short deterministic pattern list — defense in
# depth ahead of Phase 8's real output_validator, not a replacement for it.
_FORBIDDEN_ABSOLUTE_PHRASES = [
    "definitely",
    "guaranteed",
    "100% certain",
    "certainly is",
    "without a doubt",
    "this is a diagnosis",
]


class ClinicalReasoningViolation(Exception):
    """Raised when an Assessment fails a defense-in-depth check. Phase 6 has no correction/
    fallback pipeline of its own (that's Phase 8's output_validator) — callers must not treat a
    violation as recoverable; the safe response is to not use the assessment at all
    (error_handling.fail_closed_principle)."""


def check_grounding(assessment: Assessment, evidence_package: EvidencePackage) -> None:
    """clinical_reasoner.must_not: invent_evidence_or_medication_info. Every EvidenceReference
    the model cited must point at a source_id that was actually in the evidence package it was
    given — this is checkable in code, unlike prose citations."""

    known_ids = {item.source_id for item in evidence_package.retrieved_evidence}
    for reference in assessment.evidence:
        if reference.source_id not in known_ids:
            raise ClinicalReasoningViolation(
                f"assessment cites evidence source_id {reference.source_id} not present in the "
                "evidence package it was given — likely invented evidence."
            )


def check_uncertainty_language(assessment: Assessment) -> None:
    """uncertainty_language.forbidden: no unqualified absolute claims."""

    text_fields = [assessment.summary, *assessment.possible_explanations, *assessment.warnings]
    haystack = " ".join(text_fields).lower()
    for phrase in _FORBIDDEN_ABSOLUTE_PHRASES:
        if phrase in haystack:
            raise ClinicalReasoningViolation(f'assessment uses forbidden absolute language: "{phrase}"')


def run_defense_in_depth_checks(assessment: Assessment, evidence_package: EvidencePackage) -> None:
    check_grounding(assessment, evidence_package)
    check_uncertainty_language(assessment)
