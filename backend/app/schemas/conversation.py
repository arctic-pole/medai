import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageCreateRequest(BaseModel):
    conversation_id: uuid.UUID
    content: str = Field(min_length=1, max_length=4000)


class MessageExchangeResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse

    # Phase 12: set when this turn ran the full RUN_ASSESSMENT pipeline (nothing more to ask)
    # rather than asking a follow-up question — lets the mobile client offer TTS playback for
    # this specific reply and show a confirmation prompt for a high-risk result
    # (ux.confirmation_required_when: high_risk_recommendation_considered), without needing to
    # persist this metadata on the Message row itself (recomputed fresh each turn, not
    # retrievable for historical messages via GET /messages).
    is_assessment: bool = False
    assessment_status: str | None = None
    escalation: str | None = None
