from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Measurement, Patient, Vital
from app.vitals.schema import NormalizedMeasurement
from app.vitals.validation import validate_measurement


async def ingest_measurement(db: AsyncSession, patient: Patient, measurement: NormalizedMeasurement) -> Measurement:
    """vital_system.device_pipeline's VITAL_SERVICE step: validates, then persists to the
    append-only `measurements` log — accepted or not, for audit — and, if accepted, upserts the
    `vitals` current-value snapshot that app/patient_state/assembler.py reads from. A rejected
    measurement is still recorded (never silently dropped, `accepted=False` +
    `rejection_reason` on the returned row) but never updates the snapshot.
    """

    outcome = validate_measurement(measurement)

    record = Measurement(
        patient_id=patient.id,
        type=measurement.type,
        value=measurement.value,
        unit=measurement.unit,
        timestamp=measurement.timestamp,
        source=measurement.source,
        device_id=measurement.device_id,
        quality=measurement.quality,
        confidence=measurement.confidence,
        accepted=outcome.status == "accepted",
        rejection_reason=outcome.reason,
    )
    db.add(record)
    await db.flush()

    if outcome.status == "accepted":
        existing = await db.get(Vital, (patient.id, measurement.type))
        if existing is None:
            db.add(
                Vital(
                    patient_id=patient.id,
                    type=measurement.type,
                    value=measurement.value,
                    unit=measurement.unit,
                    timestamp=measurement.timestamp,
                    quality=measurement.quality,
                    source=measurement.source,
                    measurement_id=record.id,
                )
            )
        elif measurement.timestamp >= existing.timestamp:
            # Never let a backdated/out-of-order reading overwrite a more current snapshot.
            existing.value = measurement.value
            existing.unit = measurement.unit
            existing.timestamp = measurement.timestamp
            existing.quality = measurement.quality
            existing.source = measurement.source
            existing.measurement_id = record.id

    await db.commit()
    await db.refresh(record)
    return record
