import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient
from app.conversation.stub_reply import generate_stub_reply
from app.db.models import Conversation, Message, Patient
from app.db.session import get_db
from app.schemas.conversation import MessageCreateRequest, MessageExchangeResponse, MessageResponse

router = APIRouter(prefix="/messages", tags=["messages"])


async def _get_owned_conversation(db: AsyncSession, patient: Patient, conversation_id: uuid.UUID) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.patient_id != patient.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return conversation


@router.post("", response_model=MessageExchangeResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> MessageExchangeResponse:
    """Stores the user's message and returns a Phase 2 scaffold reply — see
    app/conversation/stub_reply.py. This performs no medical reasoning."""

    await _get_owned_conversation(db, patient, payload.conversation_id)

    user_message = Message(conversation_id=payload.conversation_id, role="user", content=payload.content)
    db.add(user_message)
    await db.flush()

    assistant_message = Message(
        conversation_id=payload.conversation_id,
        role="assistant",
        content=generate_stub_reply(payload.content),
    )
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
    await _get_owned_conversation(db, patient, conversation_id)
    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())
