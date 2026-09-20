from fastapi import APIRouter, Depends

from app.api.deps import get_current_patient
from app.db.models import Patient
from app.schemas.patient import PatientResponse

router = APIRouter(prefix="/patient", tags=["patient"])


@router.get("", response_model=PatientResponse)
async def get_patient(patient: Patient = Depends(get_current_patient)) -> Patient:
    return patient
