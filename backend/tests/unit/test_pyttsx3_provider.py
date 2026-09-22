"""Real (not faked) pyttsx3 synthesis — offline, no API key, no Gemini quota interaction, safe
to run in every test suite run. Exercises the actual concrete provider Pyttsx3Provider, not
just the gate/fakes covered elsewhere in this phase's test suite."""

import pytest

from app.providers.tts.pyttsx3_provider import Pyttsx3Provider
from app.tts.schema import _mint_validated_text

pytestmark = pytest.mark.asyncio


async def test_pyttsx3_provider_produces_real_nonempty_audio() -> None:
    provider = Pyttsx3Provider()

    audio = await provider.speak(_mint_validated_text("This is a test of the offline speech engine."))

    assert isinstance(audio, bytes)
    assert len(audio) > 1000  # a real synthesized WAV, not an empty/stub file
    assert audio[:4] == b"RIFF"  # WAV container magic bytes — genuinely audio, not placeholder text
