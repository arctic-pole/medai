import uuid
from datetime import datetime

from pydantic import BaseModel

from app.vitals.schema import VitalType


class VitalCreateRequest(BaseModel):
    type: VitalType
    value: float
    unit: str
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
    device_type: str
    label: str | None = None


class DeviceResponse(BaseModel):
    id: uuid.UUID
    device_type: str
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
