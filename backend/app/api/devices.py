from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient
from app.db.models import Device, Patient
from app.db.session import get_db
from app.schemas.vital import DeviceCreateRequest, DeviceResponse

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> Device:
    device = Device(patient_id=patient.id, device_type=payload.device_type, label=payload.label)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> list[Device]:
    result = await db.execute(select(Device).where(Device.patient_id == patient.id))
    return list(result.scalars().all())
