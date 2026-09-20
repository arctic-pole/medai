import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient, get_owned_conversation
from app.db.models import Message, Patient, Symptom
from app.db.session import get_db
from app.patient_state.extraction import extract_symptoms_from_conversation
from app.providers.llm import LLMNotConfiguredError, LLMProvider, get_llm_provider
from app.schemas.symptom import ExtractSymptomsRequest, SymptomResponse

router = APIRouter(prefix="/symptoms", tags=["symptoms"])


@router.post("/extract", response_model=list[SymptomResponse], status_code=status.HTTP_201_CREATED)
async def extract_symptoms(
    payload: ExtractSymptomsRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> list[Symptom]:
    """Runs Phase 3 symptom extraction over a conversation's user messages and stores the
    result. Fails closed (503) if no LLMProvider is configured — per
    error_handling.fail_closed_principle, never fabricates a response instead."""

    conversation = await get_owned_conversation(db, patient, payload.conversation_id)

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.role == "user")
        .order_by(Message.created_at)
    )
    user_messages = [m.content for m in result.scalars().all()]
    if not user_messages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="conversation has no user messages yet")

    try:
        extracted = await extract_symptoms_from_conversation(llm, user_messages)
    except LLMNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM_ERROR: {exc}",
        ) from exc
    except Exception as exc:  # LLM/network failure — controlled failure, not silent (error_handling.rule)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM_ERROR: extraction failed: {exc}"
        ) from exc

    stored: list[Symptom] = []
    for item in extracted:
        symptom = Symptom(patient_id=patient.id, conversation_id=conversation.id, **item.model_dump())
        db.add(symptom)
        stored.append(symptom)
    await db.commit()
    for symptom in stored:
        await db.refresh(symptom)
    return stored


@router.get("", response_model=list[SymptomResponse])
async def list_symptoms(
    conversation_id: uuid.UUID | None = Query(default=None),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> list[Symptom]:
    query = select(Symptom).where(Symptom.patient_id == patient.id)
    if conversation_id is not None:
        await get_owned_conversation(db, patient, conversation_id)
        query = query.where(Symptom.conversation_id == conversation_id)
    query = query.order_by(Symptom.created_at)
    result = await db.execute(query)
    return list(result.scalars().all())
