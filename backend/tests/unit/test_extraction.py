import pytest

from app.patient_state.extraction import extract_symptoms_from_conversation
from app.patient_state.schema import ExtractedSymptom
from tests.fakes import FakeLLMProvider

pytestmark = pytest.mark.asyncio


async def test_extract_symptoms_returns_provider_result() -> None:
    fake = FakeLLMProvider(
        symptoms=[ExtractedSymptom(symptom="sore throat", severity=4, certainty="user_reported")]
    )

    result = await extract_symptoms_from_conversation(fake, ["My throat has been sore since yesterday"])

    assert len(result) == 1
    assert result[0].symptom == "sore throat"
    assert result[0].severity == 4


async def test_extract_symptoms_with_no_messages_returns_empty_without_calling_llm() -> None:
    fake = FakeLLMProvider()
    result = await extract_symptoms_from_conversation(fake, [])
    assert result == []
