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
