import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ExtractSymptomsRequest(BaseModel):
    conversation_id: uuid.UUID


class SymptomResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    symptom: str
    onset: str | None
    duration: str | None
    severity: int | None = Field(default=None, ge=0, le=10)
    frequency: str | None
    location: str | None
    progression: str | None
    triggers: str | None
    relieving_factors: str | None
    associated_symptoms: str | None
    certainty: str
    created_at: datetime

    model_config = {"from_attributes": True}
