"""voice_pipeline.rule: "TTS must never receive unvalidated medical output." This module makes
that a type-level guarantee, not just a convention a future caller could forget.

ValidatedText can only be constructed via the private `_mint_validated_text` factory below,
guarded by a module-private sentinel token — Python has no true private cross-module access, but
this is the standard idiom for "only code that has actually run the real validation step may
produce this type," and it is what `TextToSpeechProvider.speak()` (app/providers/tts/base.py)
requires instead of a plain `str`. The only legitimate caller of `_mint_validated_text` is
`app.tts.speech.synthesize_validated_response`, which always runs
`app.validation.validator.get_validated_output()` first — see that module.
"""

_CONSTRUCTION_TOKEN = object()


class ValidatedText:
    """Text that has genuinely passed `get_validated_output()`. Attempting to construct this
    directly (`ValidatedText("...")`) raises `TypeError` — see `test_tts_gate.py`."""

    __slots__ = ("_text",)

    def __init__(self, text: str, *, _token: object = None) -> None:
        if _token is not _CONSTRUCTION_TOKEN:
            raise TypeError(
                "ValidatedText cannot be constructed directly — it may only be produced by "
                "app.tts.speech.synthesize_validated_response(), which requires having actually "
                "called app.validation.validator.get_validated_output() first."
            )
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return f"ValidatedText({self._text!r})"


def _mint_validated_text(text: str) -> ValidatedText:
    """Internal factory — not exported from app/tts/__init__.py. The only intended caller is
    app.tts.speech.synthesize_validated_response, immediately after get_validated_output()
    returns."""

    return ValidatedText(text, _token=_CONSTRUCTION_TOKEN)
