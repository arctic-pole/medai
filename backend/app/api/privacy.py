from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient, get_current_user
from app.core.security import verify_password
from app.db.models import Patient, User
from app.db.session import get_db
from app.privacy.service import delete_patient_account, export_patient_data
from app.schemas.privacy import DeleteAccountRequest, PrivacyExportResponse

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get("/export", response_model=PrivacyExportResponse)
async def export_my_data(
    current_user: User = Depends(get_current_user),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> PrivacyExportResponse:
    """security.minimum_requirements: minimal_data_collection. Everything MEDAI holds about the
    caller, across every table — see app/privacy/service.py:export_patient_data for exactly
    what's included and why."""

    return await export_patient_data(db, current_user, patient)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    payload: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Irreversible: cascades a real DELETE across every patient-owned table (see
    app/privacy/service.py:delete_patient_account for the exact order and what's deliberately
    excluded). Requires re-proving the account password in the request body — a stolen/leaked
    short-lived access token alone isn't enough to trigger this
    (ux.manual_interaction_permitted_for: confirmation_of_ambiguous_critical_information)."""

    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="incorrect password")

    await delete_patient_account(db, current_user, patient)
