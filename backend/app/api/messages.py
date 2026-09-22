import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient, get_owned_conversation
from app.conversation.manager import generate_reply
from app.db.models import Message, Patient
from app.db.session import get_db
from app.patient_state.assembler import build_patient_state
from app.providers.embeddings import EmbeddingProvider, get_embedding_provider
from app.providers.llm import LLMProvider, get_llm_provider
from app.providers.vector_store import VectorStore, get_vector_store
from app.reasoning.evidence_package import build_evidence_package
from app.safety.engine import evaluate_safety, vitals_from_patient_state
from app.schemas.conversation import MessageCreateRequest, MessageExchangeResponse, MessageResponse
from app.validation.validator import get_validated_output

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageExchangeResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> MessageExchangeResponse:
    """Stores the user's message, then runs the Phase 4 conversation manager
    (app/conversation/manager.py) to decide the next action: either the highest-priority
    follow-up question, or — once nothing more is missing — the real RUN_ASSESSMENT pipeline
    (Phase 12: architecture.canonical_pipeline's EVIDENCE_RETRIEVAL through OUTPUT_VALIDATION,
    the same steps POST /assessment runs, reachable here automatically instead of only via a
    separate manual action). No medical reasoning happens in the ASK_QUESTION path
    (phases.2_conversation.constraint, carried into Phase 4)."""

    conversation = await get_owned_conversation(db, patient, payload.conversation_id)

    user_message = Message(conversation_id=conversation.id, role="user", content=payload.content)
    db.add(user_message)
    await db.flush()

    state = await build_patient_state(db, patient)
    reply_text = await generate_reply(llm, state)

    is_assessment = False
    assessment_status: str | None = None
    escalation: str | None = None

    if reply_text is None:
        evidence_package = await build_evidence_package(db, patient, embedding_provider, vector_store)
        vitals = vitals_from_patient_state(evidence_package.patient_state.vitals)
        safety_evaluation = await evaluate_safety(db, patient_id=patient.id, vitals=vitals)
        assessment = await get_validated_output(llm, evidence_package, safety_evaluation)

        reply_text = assessment.summary
        if assessment.escalation:
            reply_text = f"{reply_text}\n\n{assessment.escalation}"
        is_assessment = True
        assessment_status = assessment.status
        escalation = assessment.escalation

    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=reply_text)
    db.add(assistant_message)
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)

    return MessageExchangeResponse(
        user_message=user_message,
        assistant_message=assistant_message,
        is_assessment=is_assessment,
        assessment_status=assessment_status,
        escalation=escalation,
    )


@router.get("", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID = Query(...),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> list[Message]:
    await get_owned_conversation(db, patient, conversation_id)
    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())
