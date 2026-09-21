from app.providers.llm.base import LLMNotConfiguredError, LLMProvider
from app.providers.llm.gemini_provider import GeminiProvider


def get_llm_provider() -> LLMProvider:
    """Concrete LLMProvider choice: Gemini (medai_spec.yaml architecture.provider_interfaces
    names the interface but no vendor — decided by the user; originally OpenAI in Phase 3,
    switched to Gemini afterward, see docs/KNOWN_LIMITATIONS.md). Swapping providers means
    adding a new class implementing LLMProvider and changing only this function —
    app/providers/llm/openai_provider.py is left in place as a working example of exactly
    that."""

    return GeminiProvider()


__all__ = ["LLMProvider", "LLMNotConfiguredError", "get_llm_provider"]
