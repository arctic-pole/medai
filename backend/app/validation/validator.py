import logging

from app.providers.llm.base import LLMProvider
from app.reasoning.reasoner import generate_assessment
from app.reasoning.schema import Assessment, EvidencePackage
from app.safety.schema import SafetyEvaluation
from app.validation.checks import run_all_checks

logger = logging.getLogger(__name__)

# safe_fallback, verbatim.
SAFE_FALLBACK = Assessment(
    status="caution",
    summary="Insufficient information to provide a reliable assessment.",
    confidence="low",
    recommended_next_steps=["Seek appropriate medical advice."],
    limitations=["The available information was insufficient."],
)


async def get_validated_output(
    llm: LLMProvider,
    evidence_package: EvidencePackage,
    safety_evaluation: SafetyEvaluation,
    *,
    max_correction_attempts: int = 1,
) -> Assessment:
    """output_validator: the single choke point an Assessment must pass through before it is
    fit to show a user. This is intentionally the ONLY function in this codebase that returns
    an Assessment intended for release — app/reasoning/reasoner.py's generate_assessment()
    returns unvalidated output and must never be treated as user-facing on its own
    (architecture.bypass_forbidden).

    on_failure: on a failed check, re-generates once with the failure reasons fed back
    (output_validator.on_failure: "return to correction pipeline"). If that still fails,
    returns SAFE_FALLBACK rather than the rejected content ("if correction fails use safe
    fallback").

    on_validator_failure: any unexpected exception anywhere in this function (including a bug
    in the checks themselves) is caught and also resolves to SAFE_FALLBACK — "Fail closed — do
    not release output" is interpreted here as "never release unvalidated content", not as
    "raise and crash the caller".
    """

    try:
        assessment = await generate_assessment(llm, evidence_package)
        failures = run_all_checks(assessment, evidence_package, safety_evaluation)

        attempt = 0
        while failures and attempt < max_correction_attempts:
            attempt += 1
            logger.warning(
                "output validation failed (attempt %s), retrying with correction feedback: %s",
                attempt,
                [f.detail for f in failures],
            )
            assessment = await generate_assessment(
                llm, evidence_package, correction_feedback=[f.detail for f in failures]
            )
            failures = run_all_checks(assessment, evidence_package, safety_evaluation)

        if not failures:
            return assessment

        logger.warning("output validation failed after correction attempts, using safe fallback: %s", [f.detail for f in failures])
        return SAFE_FALLBACK
    except Exception:
        logger.exception("output_validator internal failure — failing closed with safe fallback")
        return SAFE_FALLBACK
