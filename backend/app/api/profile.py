from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient
from app.db.models import Patient, PatientProfile
from app.db.session import get_db
from app.schemas.patient import ProfileResponse, ProfileUpdateRequest

router = APIRouter(prefix="/profile", tags=["profile"])


async def _get_or_create_profile(db: AsyncSession, patient: Patient) -> PatientProfile:
    profile = await db.get(PatientProfile, patient.id)
    if profile is None:
        profile = PatientProfile(patient_id=patient.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.get("", response_model=ProfileResponse)
async def get_profile(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> PatientProfile:
    return await _get_or_create_profile(db, patient)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> PatientProfile:
    profile = await _get_or_create_profile(db, patient)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.commit()
    await db.refresh(profile)
    return profile
