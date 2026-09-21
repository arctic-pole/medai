from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeChunk


class VectorStore(ABC):
    """architecture.provider_interfaces: VectorStore."""

    @abstractmethod
    async def similarity_search(
        self, db: AsyncSession, query_embedding: list[float], top_k: int
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Returns (chunk, similarity_score) pairs, best match first. similarity_score is in
        [0, 1] (1 = identical direction), not a raw distance."""
