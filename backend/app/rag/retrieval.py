from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClinicalSource
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.vector_store.base import VectorStore
from app.schemas.evidence import EvidenceItem


async def retrieve_evidence(
    db: AsyncSession,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    query: str,
    top_k: int = 5,
) -> list[EvidenceItem]:
    """rag_pipeline: RETRIEVAL -> RERANKING -> EVIDENCE_PACKAGE.

    "Reranking" today is the same order similarity_search already returns (cosine similarity
    over the embedding space) — no separate reranker model was specified, so none is invented
    here. This is the one seam a future cross-encoder reranker would slot into, re-ordering
    `results` before the EvidenceItem list is built.
    """

    if not query.strip():
        return []

    query_embedding = await embedding_provider.embed_query(query)
    results = await vector_store.similarity_search(db, query_embedding, top_k)

    items: list[EvidenceItem] = []
    for chunk, score in results:
        source: ClinicalSource = chunk.source
        items.append(
            EvidenceItem(
                content=chunk.content,
                similarity=round(score, 4),
                source_id=source.id,
                title=source.title,
                publisher=source.publisher,
                url=source.url,
                source_type=source.source_type,
                version=source.version,
                retrieval_date=source.retrieval_date,
            )
        )
    return items
