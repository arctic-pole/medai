from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMNotConfiguredError(Exception):
    """Raised when a provider has no credentials configured. Callers must fail closed — per
    error_handling.fail_closed_principle, never fabricate a response instead."""


class LLMProvider(ABC):
    """architecture.provider_interfaces: LLMProvider — generate(), structured_generate(), stream().
    Concrete implementations must never be called with uncontrolled application state
    (clinical_reasoner.prompting.must_not_receive) — callers own prompt construction."""

    @abstractmethod
    async def generate(self, prompt: str, *, system: str | None = None) -> str: ...

    @abstractmethod
    async def structured_generate(self, prompt: str, schema: type[T], *, system: str | None = None) -> T:
        """Returns a validated instance of `schema`. clinical_reasoner.prompting.rule: use
        structured output wherever supported."""

    @abstractmethod
    def stream(self, prompt: str, *, system: str | None = None) -> AsyncIterator[str]: ...
