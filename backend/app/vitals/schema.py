import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# vital_system.initial_measurements, with blood_pressure split into two scalar readings —
# canonical_measurement's `value` field is a single number, not a compound one.
VitalType = Literal[
    "heart_rate",
    "oxygen_saturation",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "body_temperature",
    "respiratory_rate",
    "weight",
]

Quality = Literal["good", "acceptable", "poor"]
Source = Literal["manual", "device", "health_platform", "simulated"]
ValidationStatus = Literal["accepted", "unreliable", "unavailable"]


class NormalizedMeasurement(BaseModel):
    """vital_system.canonical_measurement — what a DeviceAdapter produces, before validation."""

    type: VitalType
    value: float
    unit: str
    timestamp: datetime
    source: Source
    device_id: uuid.UUID | None = None
    quality: Quality = "good"
    confidence: float | None = None


class ValidationOutcome(BaseModel):
    status: ValidationStatus
    reason: str | None = None
    measurement: NormalizedMeasurement | None = None
