from abc import ABC, abstractmethod

from pydantic import BaseModel


class RawDocument(BaseModel):
    """One retrieved document, pre-chunking. `source_type` must be one of
    knowledge_base.approved_sources."""

    title: str
    publisher: str
    url: str
    content: str
    source_type: str


class MedicalKnowledgeProvider(ABC):
    """architecture.provider_interfaces: MedicalKnowledgeProvider."""

    @abstractmethod
    async def fetch(self, topic: str) -> list[RawDocument]: ...
