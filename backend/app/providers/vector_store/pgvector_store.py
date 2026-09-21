from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.db.models import ClinicalSource, KnowledgeChunk
from app.providers.vector_store.base import VectorStore


class PgVectorStore(VectorStore):
    """Concrete choice: pgvector (user decision, Phase 5) — no separate vector DB service,
    per architecture's "never introduce unnecessary microservices" rule; Postgres is already
    the only database this project runs."""

    async def similarity_search(
        self, db: AsyncSession, query_embedding: list[float], top_k: int
    ) -> list[tuple[KnowledgeChunk, float]]:
        # embeddings are normalized (SentenceTransformersProvider, normalize_embeddings=True),
        # so cosine_distance in [0, 2] maps to similarity = 1 - distance in [-1, 1].
        distance = KnowledgeChunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(KnowledgeChunk, distance.label("distance"))
            .join(ClinicalSource, KnowledgeChunk.source_id == ClinicalSource.id)
            .where(ClinicalSource.superseded_status == "current")
            .options(contains_eager(KnowledgeChunk.source))
            .order_by(distance)
            .limit(top_k)
        )
        result = await db.execute(stmt)
        return [(chunk, 1 - dist) for chunk, dist in result.all()]
