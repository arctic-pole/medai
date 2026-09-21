import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IngestTopicRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)


class ClinicalSourceResponse(BaseModel):
    id: uuid.UUID
    title: str
    publisher: str
    url: str
    source_type: str
    version: int
    retrieval_date: datetime

    model_config = {"from_attributes": True}


class EvidenceQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class EvidenceItem(BaseModel):
    content: str
    similarity: float
    source_id: uuid.UUID
    title: str
    publisher: str
    url: str
    source_type: str
    version: int
    retrieval_date: datetime
