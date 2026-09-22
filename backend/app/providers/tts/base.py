from abc import ABC, abstractmethod

from app.tts.schema import ValidatedText


class TTSError(Exception):
    """error_handling.error_categories: TTS_ERROR. Raised on any synthesis failure — never
    return silent/empty audio and call it success."""


class TTSNotConfiguredError(TTSError):
    """Raised when no TTS engine is available on this machine — fail closed, never fabricate
    audio (same fail-closed principle as LLMNotConfiguredError)."""


class TextToSpeechProvider(ABC):
    """architecture.provider_interfaces: TextToSpeechProvider. voice_pipeline.rule: "TTS must
    never receive unvalidated medical output" is enforced here structurally, not left to each
    concrete provider or caller to remember correctly.

    `speak()` is the only public entry point and is NOT abstract: it requires a `ValidatedText`
    (app/tts/schema.py) — a type that can only be constructed by code that has actually called
    `app.validation.validator.get_validated_output()` — and re-checks that at runtime via
    `isinstance`, so passing a plain `str` (raw LLM output, raw ClinicalReasoner output, or
    anything else that hasn't been through validation) is rejected before it ever reaches a
    concrete provider's synthesis code. Concrete providers implement only `_synthesize`, which
    never sees anything but already-validated text.
    """

    async def speak(self, text: ValidatedText) -> bytes:
        if not isinstance(text, ValidatedText):
            raise TypeError(
                f"TextToSpeechProvider.speak() requires ValidatedText, got {type(text).__name__}. "
                "Raw LLM/reasoner output must never reach TTS directly — see app/tts/schema.py."
            )
        if not text.text.strip():
            raise TTSError("cannot synthesize empty text")
        return await self._synthesize(text.text)

    @abstractmethod
    async def _synthesize(self, text: str) -> bytes:
        """Returns audio bytes (WAV) for already-validated `text`. Must raise TTSError (or a
        subclass) on failure — never return empty bytes and call it success."""
        ...
