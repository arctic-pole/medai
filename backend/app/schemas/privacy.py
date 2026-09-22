import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.auth import UserResponse
from app.schemas.conversation import MessageResponse
from app.schemas.patient import AllergyResponse, MedicalHistoryResponse, MedicationResponse, ProfileResponse
from app.schemas.symptom import SymptomResponse
from app.schemas.vital import DeviceResponse, MeasurementResponse, VitalResponse


class DeleteAccountRequest(BaseModel):
    # Re-proving the password guards against an irreversible action being taken with just a
    # stolen/leaked short-lived access token (ux.manual_interaction_permitted_for:
    # confirmation_of_ambiguous_critical_information — this is about as critical as it gets).
    password: str = Field(min_length=1, max_length=128)


class ConversationExport(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]


class ConsentExport(BaseModel):
    id: uuid.UUID
    consent_type: str
    version: str
    status: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class SafetyEventExport(BaseModel):
    id: uuid.UUID
    rule_id: str
    rule_version: str
    decision: str
    detail: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogExport(BaseModel):
    """Included for transparency (the user can see exactly what's logged about them), even
    though audit_logs rows are deliberately NOT deleted by DELETE /privacy/me — see that
    endpoint's docstring for why."""

    id: uuid.UUID
    request_id: uuid.UUID
    timestamp: datetime
    module: str
    latency_ms: float | None
    error_code: str | None

    model_config = {"from_attributes": True}


class PrivacyExportResponse(BaseModel):
    """security.minimum_requirements: minimal_data_collection, plus the interim data-handling
    posture (docs/SECURITY.md) — every table a patient's own data lives in, in one response.
    Excludes clinical_sources/knowledge_chunks (public reference material, not patient data)."""

    exported_at: datetime
    user: UserResponse
    patient_id: uuid.UUID
    profile: ProfileResponse | None
    medical_history: list[MedicalHistoryResponse]
    allergies: list[AllergyResponse]
    current_medications: list[MedicationResponse]
    symptoms: list[SymptomResponse]
    conversations: list[ConversationExport]
    devices: list[DeviceResponse]
    measurements: list[MeasurementResponse]
    vitals: list[VitalResponse]
    safety_events: list[SafetyEventExport]
    consents: list[ConsentExport]
    audit_logs: list[AuditLogExport]
