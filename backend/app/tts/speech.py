from app.providers.llm.base import LLMProvider
from app.providers.tts.base import TextToSpeechProvider
from app.reasoning.schema import Assessment, EvidencePackage
from app.safety.schema import SafetyEvaluation
from app.tts.schema import _mint_validated_text
from app.validation.validator import get_validated_output


def _speech_text_from_assessment(assessment: Assessment) -> str:
    """What gets spoken: the summary, plus escalation guidance if present — spoken emergency
    instructions matter as much as the written ones (voice_pipeline exists precisely so a
    hands-free/eyes-elsewhere user still gets this)."""

    text = assessment.summary
    if assessment.escalation:
        text = f"{text} {assessment.escalation}"
    return text


async def synthesize_validated_response(
    tts: TextToSpeechProvider,
    llm: LLMProvider,
    evidence_package: EvidencePackage,
    safety_evaluation: SafetyEvaluation,
    *,
    max_correction_attempts: int = 1,
) -> tuple[Assessment, bytes]:
    """voice_pipeline.flow's VALIDATED_TEXT -> TTS step, and the only function in this codebase
    permitted to call TextToSpeechProvider.speak(). Deliberately does NOT accept a pre-built
    Assessment as an argument — only the pre-validation pipeline inputs a caller would also pass
    to get_validated_output() directly. This closes the loophole a simpler
    `speak(assessment)`-shaped function would leave open (constructing an Assessment directly,
    e.g. `Assessment(summary="fabricated")`, is trivial and already done throughout this
    codebase's own tests): there is no argument here a caller could use to smuggle unvalidated
    text through, because this function always runs get_validated_output() itself before any
    text reaches TTS (architecture.bypass_forbidden; voice_pipeline.rule: "TTS must never
    receive unvalidated medical output").

    Returns the Assessment alongside the audio bytes so the text form is always available too
    (ux.accessibility.text_always_available) — callers must never treat TTS as the only
    response channel; the text return value here is not optional.
    """

    assessment = await get_validated_output(
        llm, evidence_package, safety_evaluation, max_correction_attempts=max_correction_attempts
    )
    validated_text = _mint_validated_text(_speech_text_from_assessment(assessment))
    audio = await tts.speak(validated_text)
    return assessment, audio
