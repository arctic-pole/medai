import hashlib
import math
from collections.abc import AsyncIterator

from app.patient_state.schema import ExtractedSymptom, SymptomExtractionResult
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.base import LLMNotConfiguredError, LLMProvider, T
from app.providers.medical_knowledge.base import MedicalKnowledgeProvider, RawDocument


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


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, hashed bag-of-words embedding — no model download, no GPU/CPU inference.
    Texts sharing more words get higher cosine similarity, which is enough to test retrieval
    ranking without the real ~1.3GB BAAI/bge-large-en-v1.5 model in fast tests."""

    @property
    def dimensions(self) -> int:
        return 1024

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimensions
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeMedicalKnowledgeProvider(MedicalKnowledgeProvider):
    """A deterministic stand-in for MedlinePlusProvider — no real network call."""

    def __init__(self, documents: list[RawDocument] | None = None) -> None:
        self._documents = documents or [
            RawDocument(
                title="Tension Headache",
                publisher="Test Publisher",
                url="https://example.org/headache",
                content=(
                    "Tension headaches are the most common type of headache. They often last "
                    "from thirty minutes to several hours and are related to stress, poor "
                    "posture, or lack of sleep. Most people find relief with rest and "
                    "over-the-counter pain relievers."
                ),
                source_type="government_health_guidance",
            )
        ]

    async def fetch(self, topic: str) -> list[RawDocument]:
        return self._documents
