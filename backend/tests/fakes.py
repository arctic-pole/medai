from collections.abc import AsyncIterator

from app.patient_state.schema import ExtractedSymptom, SymptomExtractionResult
from app.providers.llm.base import LLMNotConfiguredError, LLMProvider, T


class FakeLLMProvider(LLMProvider):
    """A deterministic stand-in for OpenAIProvider, used wherever tests need to exercise the
    extraction pipeline without a real API key or network call."""

    def __init__(self, symptoms: list[ExtractedSymptom] | None = None) -> None:
        self._symptoms = symptoms or [
            ExtractedSymptom(symptom="headache", severity=6, duration="8 hours", certainty="user_reported")
        ]

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return "fake response"

    async def structured_generate(self, prompt: str, schema: type[T], *, system: str | None = None) -> T:
        if schema is SymptomExtractionResult:
            return SymptomExtractionResult(symptoms=self._symptoms)  # type: ignore[return-value]
        raise NotImplementedError(f"FakeLLMProvider has no canned response for {schema}")

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        for chunk in ["fake ", "stream"]:
            yield chunk


class NotConfiguredLLMProvider(LLMProvider):
    """Mirrors OpenAIProvider's behavior with no API key set — fails closed."""

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        raise LLMNotConfiguredError("no provider configured")

    async def structured_generate(self, prompt: str, schema: type[T], *, system: str | None = None) -> T:
        raise LLMNotConfiguredError("no provider configured")

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        raise LLMNotConfiguredError("no provider configured")
        yield  # pragma: no cover — makes this an async generator
