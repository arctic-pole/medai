def generate_stub_reply(user_text: str) -> str:
    """Phase 2 scaffolding only — proves the mic/STT -> API -> UI loop end-to-end.

    This is NOT clinical reasoning and must not be mistaken for it: per
    phases.2_conversation.constraint ("No medical reasoning yet"), it performs no symptom
    extraction, no evidence retrieval, and makes no medical claims. It is replaced by the real
    conversation_manager (Phase 4) once patient_state (Phase 3) exists. Per prompt_safety,
    user_text is untrusted data — it is only ever echoed back, never interpreted as instructions.
    """

    trimmed = user_text.strip()
    if not trimmed:
        return "I didn't catch that — could you try again?"

    return (
        f'I heard: "{trimmed}"\n\n'
        "(This is a placeholder response for testing the conversation pipeline. "
        "MEDAI does not yet understand or reason about what you said — that starts in a later "
        "development phase.)"
    )
