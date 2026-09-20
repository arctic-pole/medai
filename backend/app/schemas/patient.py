import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# --- Patient ---


class PatientResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Profile ---


class ProfileUpdateRequest(BaseModel):
    age: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    consent_status: str | None = None


class ProfileResponse(BaseModel):
    age: int | None
    sex: str | None
    height_cm: float | None
    weight_kg: float | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    consent_status: str
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Medical history ---


class MedicalHistoryCreateRequest(BaseModel):
    condition: str = Field(min_length=1, max_length=500)
    status: str = "active"
    notes: str | None = None


class MedicalHistoryUpdateRequest(BaseModel):
    condition: str | None = None
    status: str | None = None
    notes: str | None = None


class MedicalHistoryResponse(BaseModel):
    id: uuid.UUID
    condition: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Allergies ---


class AllergyCreateRequest(BaseModel):
    substance: str = Field(min_length=1, max_length=200)
    reaction: str | None = None
    severity: str | None = None


class AllergyUpdateRequest(BaseModel):
    substance: str | None = None
    reaction: str | None = None
    severity: str | None = None


class AllergyResponse(BaseModel):
    id: uuid.UUID
    substance: str
    reaction: str | None
    severity: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Current medications ---


class MedicationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str | None = None
    frequency: str | None = None


class MedicationUpdateRequest(BaseModel):
    name: str | None = None
    dosage: str | None = None
    frequency: str | None = None


class MedicationResponse(BaseModel):
    id: uuid.UUID
    name: str
    dosage: str | None
    frequency: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
