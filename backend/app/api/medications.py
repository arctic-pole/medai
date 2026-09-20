import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient
from app.db.models import CurrentMedication, Patient
from app.db.session import get_db
from app.schemas.patient import MedicationCreateRequest, MedicationResponse, MedicationUpdateRequest

router = APIRouter(prefix="/medications", tags=["medications"])


async def _get_owned_entry(db: AsyncSession, patient: Patient, entry_id: uuid.UUID) -> CurrentMedication:
    entry = await db.get(CurrentMedication, entry_id)
    if entry is None or entry.patient_id != patient.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="medication not found")
    return entry


@router.get("", response_model=list[MedicationResponse])
async def list_medications(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> list[CurrentMedication]:
    result = await db.execute(select(CurrentMedication).where(CurrentMedication.patient_id == patient.id))
    return list(result.scalars().all())


@router.post("", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
async def create_medication(
    payload: MedicationCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> CurrentMedication:
    entry = CurrentMedication(patient_id=patient.id, **payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=MedicationResponse)
async def update_medication(
    entry_id: uuid.UUID,
    payload: MedicationUpdateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> CurrentMedication:
    entry = await _get_owned_entry(db, patient, entry_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_medication(
    entry_id: uuid.UUID,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> None:
    entry = await _get_owned_entry(db, patient, entry_id)
    await db.delete(entry)
    await db.commit()
