import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient
from app.db.models import Allergy, Patient
from app.db.session import get_db
from app.schemas.patient import AllergyCreateRequest, AllergyResponse, AllergyUpdateRequest

router = APIRouter(prefix="/allergies", tags=["allergies"])


async def _get_owned_entry(db: AsyncSession, patient: Patient, entry_id: uuid.UUID) -> Allergy:
    entry = await db.get(Allergy, entry_id)
    if entry is None or entry.patient_id != patient.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="allergy not found")
    return entry


@router.get("", response_model=list[AllergyResponse])
async def list_allergies(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> list[Allergy]:
    result = await db.execute(select(Allergy).where(Allergy.patient_id == patient.id))
    return list(result.scalars().all())


@router.post("", response_model=AllergyResponse, status_code=status.HTTP_201_CREATED)
async def create_allergy(
    payload: AllergyCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> Allergy:
    entry = Allergy(patient_id=patient.id, **payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=AllergyResponse)
async def update_allergy(
    entry_id: uuid.UUID,
    payload: AllergyUpdateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> Allergy:
    entry = await _get_owned_entry(db, patient, entry_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allergy(
    entry_id: uuid.UUID,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> None:
    entry = await _get_owned_entry(db, patient, entry_id)
    await db.delete(entry)
    await db.commit()
