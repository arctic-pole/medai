import logging

from app.conversation.missing_info import MissingInfoItem, identify_missing_info
from app.patient_state.schema import PatientState
from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# conversation_manager.permitted_actions, verbatim.
PERMITTED_ACTIONS = frozenset(
    {"ASK_QUESTION", "GET_VITAL", "RETRIEVE_HISTORY", "RETRIEVE_EVIDENCE", "RUN_ASSESSMENT", "ESCALATE", "RESPOND"}
)

# Of those, the ones with a real backing subsystem today. RUN_ASSESSMENT's pipeline
# (Phases 5-8) is real as of Phase 12, wired into POST /messages (app/api/messages.py) rather
# than here — this module stays deliberately free of DB/evidence/safety dependencies (Phase 4's
# separation of concerns), so it can only decide THAT assessment is the next action, not run it.
# GET_VITAL has no manual-entry conversational trigger yet, ESCALATE has no manager-level
# detection ahead of running the assessment itself. RETRIEVE_HISTORY isn't a separate action
# here because history is already folded into `state` by app/patient_state/assembler.py before
# this module ever runs.
_IMPLEMENTED_ACTIONS = frozenset({"ASK_QUESTION", "RUN_ASSESSMENT"})

_PHRASING_SYSTEM_PROMPT = (
    "You turn a plain description of missing information into a single, short, natural "
    "follow-up question for a patient. Output only the question itself — no preamble, no "
    "explanation, no diagnosis or medical claims."
)


def select_action(items: list[MissingInfoItem]) -> str:
    """conversation_manager.flow step 4 (check_if_missing_info_changes_next_action) — with only
    ASK_QUESTION/RESPOND implemented today, this collapses to "is anything missing", but stays
    a separate step so a future LLM-proposed action (e.g. RUN_ASSESSMENT once Phase 6 exists)
    has one place to be validated.

    conversation_manager.rule: "LLM may propose an action; application determines whether it is
    permitted." This function IS that application-side arbiter — it is the only place an action
    is allowed to be selected, deterministic here, but any future caller (including an
    LLM-proposed action) must be validated the same way before being acted on.
    """

    action = "ASK_QUESTION" if items else "RUN_ASSESSMENT"
    return validate_action(action)


def validate_action(action: str) -> str:
    if action not in PERMITTED_ACTIONS:
        raise ValueError(f"{action!r} is not a permitted_action (medai_spec.yaml conversation_manager)")
    if action not in _IMPLEMENTED_ACTIONS:
        raise NotImplementedError(f"{action} has no backing subsystem yet")
    return action


async def _phrase_question(item: MissingInfoItem, llm: LLMProvider) -> str:
    try:
        question = await llm.generate(
            f"Ask the patient a single, short, natural follow-up question to learn {item.prompt_hint}.",
            system=_PHRASING_SYSTEM_PROMPT,
        )
        question = question.strip()
        if question:
            return question
    except Exception:
        logger.warning("LLM question phrasing failed for field=%s; using fallback template", item.field, exc_info=True)

    return f"Could you tell me {item.prompt_hint}?"


async def generate_reply(llm: LLMProvider, state: PatientState) -> str | None:
    """conversation_manager.flow steps 3-6: identify missing info, decide the next action,
    and — if it's ASK_QUESTION — phrase the highest-priority one
    (conversation_manager.question_priority order, already applied by identify_missing_info).
    Natural phrasing is best-effort via the LLM; a deterministic template is always available,
    so this works with or without an LLM provider configured.

    Returns None once nothing more is missing (action == RUN_ASSESSMENT) — the caller
    (app/api/messages.py) is then responsible for actually running that pipeline, which needs
    dependencies (DB, evidence retrieval, the safety engine) this function deliberately doesn't
    have.
    """

    items = identify_missing_info(state)
    action = select_action(items)

    if action == "ASK_QUESTION":
        return await _phrase_question(items[0], llm)
    return None
