from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_patient
from app.db.models import Measurement, Patient, Vital
from app.db.session import get_db
from app.schemas.vital import MeasurementResponse, VitalCreateRequest, VitalResponse
from app.vitals.schema import NormalizedMeasurement
from app.vitals.service import ingest_measurement

router = APIRouter(prefix="/vitals", tags=["vitals"])


@router.post("", response_model=MeasurementResponse, status_code=status.HTTP_201_CREATED)
async def create_vital(
    payload: VitalCreateRequest,
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> Measurement:
    """Manual entry — the only DEVICE step reachable today
    (automatic_retrieval_preference: DEVICE -> HEALTH_PLATFORM -> MEDAI isn't available until
    Phase 10 exists). `source` is always "manual" server-side regardless of client input —
    nothing else is real yet, so nothing else may claim to be (never fabricate a measurement's
    provenance). Returns 422 (not silently accepted) if the measurement fails validation —
    vital_system.on_suspicious_measurement: MEASUREMENT_UNRELIABLE, request another.
    """

    measurement = NormalizedMeasurement(
        type=payload.type,
        value=payload.value,
        unit=payload.unit,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
        source="manual",
        quality="good",
    )
    record = await ingest_measurement(db, patient, measurement)

    if not record.accepted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"MEASUREMENT_UNRELIABLE: {record.rejection_reason} — please take another measurement.",
        )
    return record


@router.get("", response_model=list[VitalResponse])
async def list_current_vitals(
    patient: Patient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
) -> list[Vital]:
    result = await db.execute(select(Vital).where(Vital.patient_id == patient.id))
    return list(result.scalars().all())


@router.get("/history", response_model=list[MeasurementResponse])
async def list_measurement_history(
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    patient: Patient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
) -> list[Measurement]:
    query = select(Measurement).where(Measurement.patient_id == patient.id)
    if type is not None:
        query = query.where(Measurement.type == type)
    query = query.order_by(Measurement.timestamp.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
