import asyncio
import os
import tempfile

import pyttsx3

from app.providers.tts.base import TextToSpeechProvider, TTSError


class Pyttsx3Provider(TextToSpeechProvider):
    """Concrete TextToSpeechProvider choice: pyttsx3, wrapping the OS's native TTS engine
    (SAPI5 on Windows — this dev machine; NSSpeechSynthesizer on macOS; espeak on Linux).
    Offline, no API key, no network call — mirrors Phase 2's on-device STT choice
    (speech_to_text) and cannot interact with Gemini's quota at all, by construction (this
    phase's own constraint: TTS must never consume LLM quota).

    Verified to actually produce audio on this machine before being wired in (not assumed):
    `pyttsx3.init().save_to_file(...)` was run standalone and produced a real, non-empty WAV
    file.
    """

    async def _synthesize(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        try:
            engine = pyttsx3.init()
        except Exception as exc:
            raise TTSError(f"failed to initialize TTS engine: {exc}") from exc

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            engine.save_to_file(text, path)
            engine.runAndWait()
            with open(path, "rb") as f:
                data = f.read()
            if not data:
                raise TTSError("TTS engine produced no audio output")
            return data
        except TTSError:
            raise
        except Exception as exc:
            raise TTSError(f"TTS synthesis failed: {exc}") from exc
        finally:
            engine.stop()
            os.unlink(path)
