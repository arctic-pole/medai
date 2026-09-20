import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient, get_owned_conversation
from app.conversation.manager import generate_reply
from app.db.models import Message, Patient
from app.db.session import get_db
from app.patient_state.assembler import build_patient_state
from app.providers.llm import LLMProvider, get_llm_provider
from app.schemas.conversation import MessageCreateRequest, MessageExchangeResponse, MessageResponse

router = APIRouter(prefix="/messages", tags=["messages"])


@router.post("", response_model=MessageExchangeResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> MessageExchangeResponse:
    """Stores the user's message, then runs the Phase 4 conversation manager
    (app/conversation/manager.py) to decide and phrase the reply — either the
    highest-priority follow-up question, or a "nothing more to ask" message. No medical
    reasoning happens here (phases.2_conversation.constraint, carried into Phase 4)."""

    conversation = await get_owned_conversation(db, patient, payload.conversation_id)

    user_message = Message(conversation_id=conversation.id, role="user", content=payload.content)
    db.add(user_message)
    await db.flush()

    state = await build_patient_state(db, patient)
    reply_text = await generate_reply(llm, state)

    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=reply_text)
    db.add(assistant_message)
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)

    return MessageExchangeResponse(user_message=user_message, assistant_message=assistant_message)


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
