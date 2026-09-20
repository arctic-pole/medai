from app.providers.llm.base import LLMNotConfiguredError, LLMProvider
from app.providers.llm.openai_provider import OpenAIProvider


def get_llm_provider() -> LLMProvider:
    """Concrete LLMProvider choice: OpenAI (medai_spec.yaml architecture.provider_interfaces
    names the interface but no vendor — decided by the user for Phase 3, see
    docs/KNOWN_LIMITATIONS.md). Swapping providers means adding a new class implementing
    LLMProvider and changing only this function."""

    return OpenAIProvider()


__all__ = ["LLMProvider", "LLMNotConfiguredError", "get_llm_provider"]
