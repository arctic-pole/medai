from app.patient_state.schema import ExtractedSymptom, SymptomExtractionResult
from app.providers.llm.base import LLMProvider

_SYSTEM_PROMPT = (
    "You extract structured symptom information from a patient's own words. "
    "Extract only what the patient actually said — never invent, infer beyond what is stated, "
    "or fill in a plausible-sounding value for anything not mentioned; leave that field null "
    "instead. Mark certainty as 'user_reported' for anything the patient stated directly. "
    "This is data extraction, not diagnosis: do not suggest causes, conditions, or treatments."
)


def _build_prompt(user_messages: list[str]) -> str:
    transcript = "\n".join(f"- {m}" for m in user_messages)
    return (
        "Here is what the patient said, in order, across one conversation:\n"
        f"{transcript}\n\n"
        "Extract every distinct symptom mentioned as a separate entry."
    )


async def extract_symptoms_from_conversation(
    llm: LLMProvider, user_messages: list[str]
) -> list[ExtractedSymptom]:
    """Phase 3: transcript -> structured symptom_extraction.fields. Per patient_state.rules,
    this is the ONLY place raw conversation text is handed to an LLM for interpretation in this
    phase — the result is structured data, not prose the rest of the system reasons over
    directly."""

    if not user_messages:
        return []

    result = await llm.structured_generate(
        _build_prompt(user_messages), schema=SymptomExtractionResult, system=_SYSTEM_PROMPT
    )
    return result.symptoms
