from app.providers.tts.base import TextToSpeechProvider, TTSError, TTSNotConfiguredError
from app.providers.tts.pyttsx3_provider import Pyttsx3Provider


def get_tts_provider() -> TextToSpeechProvider:
    """Concrete TextToSpeechProvider choice: pyttsx3 (app/providers/tts/pyttsx3_provider.py) —
    offline, no API key, no vendor account. Exactly one place selects the active provider;
    swapping means writing a new TextToSpeechProvider subclass and changing only this
    function, same pattern as get_llm_provider()."""

    return Pyttsx3Provider()


__all__ = ["TextToSpeechProvider", "TTSError", "TTSNotConfiguredError", "get_tts_provider"]
