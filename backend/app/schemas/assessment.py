import uuid

from pydantic import BaseModel


class AssessmentRequest(BaseModel):
    conversation_id: uuid.UUID
