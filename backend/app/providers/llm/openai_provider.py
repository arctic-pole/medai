from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.core.config import settings
from app.providers.llm.base import LLMNotConfiguredError, LLMProvider, T


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self._model = settings.openai_model

    def _require_client(self) -> AsyncOpenAI:
        if self._client is None:
            raise LLMNotConfiguredError(
                "OPENAI_API_KEY is not set — see .env.example. No response was fabricated."
            )
        return self._client

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        client = self._require_client()
        response = await client.chat.completions.create(
            model=self._model, messages=self._messages(prompt, system)
        )
        return response.choices[0].message.content or ""

    async def structured_generate(self, prompt: str, schema: type[T], *, system: str | None = None) -> T:
        client = self._require_client()
        completion = await client.chat.completions.parse(
            model=self._model, messages=self._messages(prompt, system), response_format=schema
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI did not return a response matching the requested schema")
        return parsed

    async def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]:
        client = self._require_client()
        response_stream = await client.chat.completions.create(
            model=self._model, messages=self._messages(prompt, system), stream=True
        )
        async for chunk in response_stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
