import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient, get_owned_conversation
from app.db.models import Conversation, Patient
from app.db.session import get_db
from app.schemas.conversation import ConversationResponse

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> Conversation:
    conversation = Conversation(patient_id=patient.id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation).where(Conversation.patient_id == patient.id).order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    return await get_owned_conversation(db, patient, conversation_id)
