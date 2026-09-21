import hashlib
import math
import uuid
from collections.abc import AsyncIterator

from app.patient_state.schema import ExtractedSymptom, PatientState, PatientStateIdentity, SymptomExtractionResult
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.base import LLMNotConfiguredError, LLMProvider, T
from app.providers.medical_knowledge.base import MedicalKnowledgeProvider, RawDocument
from app.providers.medication_db.base import DrugLabel, MedicationDBProvider
from app.reasoning.schema import Assessment


def empty_patient_state(**overrides) -> PatientState:
    base = dict(patient=PatientStateIdentity(id=uuid.uuid4()), unknowns=[])
    base.update(overrides)
    return PatientState(**base)


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


class FakeReasoningLLMProvider(LLMProvider):
    """Returns a queue of canned Assessment objects, one per call to structured_generate — lets
    a test simulate a first bad attempt (e.g. ungrounded evidence) followed by a good one, to
    exercise app/reasoning/reasoner.py's retry path without a real model."""

    def __init__(self, assessments: list[Assessment]) -> None:
        self._assessments = list(assessments)
        self.call_count = 0

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return "fake response"

    async def structured_generate(self, prompt: str, schema: type[T], *, system: str | None = None) -> T:
        self.call_count += 1
        if schema is not Assessment:
            raise NotImplementedError(f"FakeReasoningLLMProvider has no canned response for {schema}")
        if not self._assessments:
            raise RuntimeError("FakeReasoningLLMProvider ran out of canned assessments")
        return self._assessments.pop(0)  # type: ignore[return-value]

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        yield "fake"


class FakeMedicationDBProvider(MedicationDBProvider):
    """A deterministic stand-in for OpenFDAProvider — no real network call. Register labels by
    (lowercased) name via the constructor; lookup() is case-insensitive against generic_name,
    brand_names, and the name it was registered under."""

    def __init__(self, labels: dict[str, DrugLabel] | None = None) -> None:
        self._labels = {k.lower(): v for k, v in (labels or {}).items()}

    async def lookup(self, drug_name: str) -> DrugLabel | None:
        return self._labels.get(drug_name.lower())
