from collections.abc import AsyncIterator

from google import genai

from app.core.config import settings
from app.providers.llm.base import LLMNotConfiguredError, LLMProvider, T

# Observed live (Phase 8/assessment-endpoint testing): with no timeout, a rate-limited call can
# hang far longer than the "retry in Ns" the API itself reports — the SDK doesn't fail fast on
# its own. A bounded timeout ensures a stuck call surfaces as a real exception (which
# generate_assessment/get_validated_output already handle via retry + fail-closed) instead of
# hanging the whole request.
_REQUEST_TIMEOUT_SECONDS = 30.0


class GeminiProvider(LLMProvider):
    """Concrete LLMProvider choice: Google Gemini, via the official `google-genai` SDK
    (`client.aio.interactions.create` — the current async Interactions API, verified against
    the live docs and the installed SDK's own type definitions, not assumed from training
    data). User decision, superseding the earlier OpenAI default — see
    docs/KNOWN_LIMITATIONS.md. OpenAIProvider is left in place as a second, still-working
    implementation of the same interface."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        self._model = settings.gemini_model

    def _require_client(self) -> genai.Client:
        if self._client is None:
            raise LLMNotConfiguredError(
                "GEMINI_API_KEY is not set — see .env.example. No response was fabricated."
            )
        return self._client

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        client = self._require_client()
        interaction = await client.aio.interactions.create(
            model=self._model, input=prompt, system_instruction=system, timeout=_REQUEST_TIMEOUT_SECONDS
        )
        return interaction.output_text or ""

    async def structured_generate(self, prompt: str, schema: type[T], *, system: str | None = None) -> T:
        client = self._require_client()
        interaction = await client.aio.interactions.create(
            model=self._model,
            input=prompt,
            system_instruction=system,
            response_format={"type": "text", "mime_type": "application/json", "schema_": schema.model_json_schema()},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        return schema.model_validate_json(interaction.output_text)

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        client = self._require_client()
        response_stream = await client.aio.interactions.create(
            model=self._model, input=prompt, system_instruction=system, stream=True, timeout=_REQUEST_TIMEOUT_SECONDS
        )
        async for event in response_stream:
            if event.event_type == "step.delta" and getattr(event.delta, "type", None) == "text":
                yield event.delta.text
