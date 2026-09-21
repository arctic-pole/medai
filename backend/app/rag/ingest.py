from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClinicalSource, KnowledgeChunk
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.medical_knowledge.base import MedicalKnowledgeProvider
from app.rag.chunking import chunk_text


async def _supersede_existing(db: AsyncSession, url: str) -> int:
    """knowledge_base.versioning: never overwrite — mark any current row for this url as
    superseded and return the version number the new row should use."""

    result = await db.execute(
        select(ClinicalSource).where(ClinicalSource.url == url, ClinicalSource.superseded_status == "current")
    )
    existing = result.scalars().all()
    for source in existing:
        source.superseded_status = "superseded"
    return max((s.version for s in existing), default=0) + 1


async def ingest_topic(
    db: AsyncSession,
    knowledge_provider: MedicalKnowledgeProvider,
    embedding_provider: EmbeddingProvider,
    topic: str,
) -> list[ClinicalSource]:
    """rag_pipeline: SOURCE_INGESTION -> CLEANING (provider's job) -> METADATA -> CHUNKING ->
    EMBEDDINGS -> VECTOR_DB. Returns the newly created (current) ClinicalSource rows."""

    documents = await knowledge_provider.fetch(topic)
    created: list[ClinicalSource] = []

    for doc in documents:
        version = await _supersede_existing(db, doc.url)

        source = ClinicalSource(
            title=doc.title,
            publisher=doc.publisher,
            url=doc.url,
            source_type=doc.source_type,
            version=version,
            superseded_status="current",
        )
        db.add(source)
        await db.flush()

        chunks = chunk_text(doc.content)
        if not chunks:
            continue
        embeddings = await embedding_provider.embed_documents(chunks)
        for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
            db.add(KnowledgeChunk(source_id=source.id, chunk_index=index, content=chunk_content, embedding=embedding))

        created.append(source)

    await db.commit()
    for source in created:
        await db.refresh(source)
    return created
