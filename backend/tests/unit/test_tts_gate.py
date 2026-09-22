"""Phase 11's core safety property: TTS must never receive unvalidated medical output
(voice_pipeline.rule). These tests exercise the gate directly — no LLM call, no pyttsx3 call."""

import pytest

from app.providers.tts.base import TTSError
from app.tts.schema import ValidatedText, _mint_validated_text
from tests.fakes import FakeTTSProvider


def test_validated_text_cannot_be_constructed_directly() -> None:
    """Requirement: an automated test proving unvalidated text cannot reach the TTS provider.
    This is the type-level half of that proof — see test_tts_speech.py for the behavioral half
    (that only get_validated_output()'s result is ever spoken)."""

    with pytest.raises(TypeError, match="cannot be constructed directly"):
        ValidatedText("raw LLM output, not validated")


def test_mint_validated_text_produces_a_usable_instance() -> None:
    validated = _mint_validated_text("hello")
    assert validated.text == "hello"


async def test_speak_rejects_a_plain_string() -> None:
    """A concrete provider's speak() must reject raw str even if some future caller tries to
    bypass the type system — defense in depth beyond the type hint."""

    provider = FakeTTSProvider()
    with pytest.raises(TypeError, match="requires ValidatedText"):
        await provider.speak("raw LLM output")  # type: ignore[arg-type]
    assert provider.synthesized_texts == []


async def test_speak_rejects_empty_text() -> None:
    provider = FakeTTSProvider()
    with pytest.raises(TTSError, match="empty"):
        await provider.speak(_mint_validated_text(""))
    assert provider.synthesized_texts == []


async def test_speak_rejects_whitespace_only_text() -> None:
    provider = FakeTTSProvider()
    with pytest.raises(TTSError, match="empty"):
        await provider.speak(_mint_validated_text("   "))
    assert provider.synthesized_texts == []


async def test_speak_succeeds_with_validated_text() -> None:
    provider = FakeTTSProvider()
    audio = await provider.speak(_mint_validated_text("hello world"))
    assert audio == b"FAKE_AUDIO:hello world"
    assert provider.synthesized_texts == ["hello world"]
