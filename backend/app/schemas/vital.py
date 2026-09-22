import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.vitals.schema import VitalType

# Every real unit vital_system uses is a few characters ("bpm", "mmHg", "%", "breaths/min",
# "kg", "F") — bounded generously above that, not to the exact set, so a genuinely new unit
# doesn't need a schema change, while still rejecting an arbitrarily large string.
_MAX_UNIT_LENGTH = 20


class VitalCreateRequest(BaseModel):
    type: VitalType
    value: float
    unit: str = Field(min_length=1, max_length=_MAX_UNIT_LENGTH)
    timestamp: datetime | None = None  # defaults to now if omitted


class MeasurementResponse(BaseModel):
    id: uuid.UUID
    type: str
    value: float
    unit: str
    timestamp: datetime
    source: str
    quality: str
    accepted: bool
    rejection_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VitalResponse(BaseModel):
    type: str
    value: float
    unit: str
    timestamp: datetime
    quality: str
    source: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeviceCreateRequest(BaseModel):
    device_type: str = Field(min_length=1, max_length=50)
    label: str | None = Field(default=None, max_length=200)


class DeviceResponse(BaseModel):
    id: uuid.UUID
    device_type: str
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VitalSyncReading(BaseModel):
    """One reading the app already read from a real on-device health platform (Health
    Connect) — this is the wire shape of a NormalizedMeasurement minus `source`/`device_id`,
    which the server fills in itself rather than trusting the client (see POST /vitals/sync).
    """

    type: VitalType
    value: float
    unit: str = Field(min_length=1, max_length=_MAX_UNIT_LENGTH)
    timestamp: datetime


class VitalSyncRequest(BaseModel):
    device_id: uuid.UUID
    # Capped so a single sync call can't submit an unbounded number of readings in one request
    # (input sanitisation / DoS, Phase 13) — 1000 comfortably covers even a full week of
    # multiple-times-daily readings across every vital_system.initial_measurements type.
    readings: list[VitalSyncReading] = Field(max_length=1000)


class VitalSyncResult(BaseModel):
    type: str
    value: float
    unit: str
    timestamp: datetime
    accepted: bool
    rejection_reason: str | None


class VitalSyncResponse(BaseModel):
    synced: int
    accepted: int
    rejected: int
    results: list[VitalSyncResult]
