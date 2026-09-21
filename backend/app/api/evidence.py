from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.providers.embeddings import EmbeddingProvider, get_embedding_provider
from app.providers.medical_knowledge import MedicalKnowledgeProvider, get_medical_knowledge_provider
from app.providers.vector_store import VectorStore, get_vector_store
from app.rag.ingest import ingest_topic
from app.rag.retrieval import retrieve_evidence
from app.schemas.evidence import ClinicalSourceResponse, EvidenceItem, IngestTopicRequest

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.post("/ingest", response_model=list[ClinicalSourceResponse], status_code=status.HTTP_201_CREATED)
async def ingest(
    payload: IngestTopicRequest,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    knowledge_provider: MedicalKnowledgeProvider = Depends(get_medical_knowledge_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> list:
    """rag_pipeline SOURCE_INGESTION entry point. Fetches real documents for `topic` from the
    configured MedicalKnowledgeProvider (MedlinePlus), chunks, embeds, and stores them —
    superseding any prior version of the same source (knowledge_base.versioning)."""

    return await ingest_topic(db, knowledge_provider, embedding_provider, payload.topic)


@router.get("", response_model=list[EvidenceItem])
async def search(
    query: str = Query(..., min_length=1, max_length=500),
    top_k: int = Query(default=5, ge=1, le=20),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStore = Depends(get_vector_store),
) -> list[EvidenceItem]:
    """rag_pipeline RETRIEVAL -> EVIDENCE_PACKAGE. Every item traces back to a specific,
    versioned ClinicalSource (evidence_package.rule)."""

    return await retrieve_evidence(db, embedding_provider, vector_store, query, top_k)
