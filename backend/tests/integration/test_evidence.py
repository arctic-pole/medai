import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.models import ClinicalSource, KnowledgeChunk
from app.main import app
from app.providers.embeddings import get_embedding_provider
from app.providers.medical_knowledge import get_medical_knowledge_provider
from app.rag.ingest import ingest_topic
from app.rag.retrieval import retrieve_evidence
from app.providers.vector_store.pgvector_store import PgVectorStore
from tests.fakes import FakeEmbeddingProvider, FakeMedicalKnowledgeProvider

pytestmark = pytest.mark.asyncio


async def _authed_headers(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": email, "password": "s3curePassw0rd"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_ingest_topic_creates_source_and_chunks(db_session) -> None:
    sources = await ingest_topic(db_session, FakeMedicalKnowledgeProvider(), FakeEmbeddingProvider(), "headache")

    assert len(sources) == 1
    assert sources[0].source_type == "government_health_guidance"
    assert sources[0].superseded_status == "current"
    assert sources[0].version == 1

    chunks = (
        await db_session.execute(select(KnowledgeChunk).where(KnowledgeChunk.source_id == sources[0].id))
    ).scalars().all()
    assert len(chunks) >= 1


async def test_retrieve_evidence_traces_back_to_source(db_session) -> None:
    await ingest_topic(db_session, FakeMedicalKnowledgeProvider(), FakeEmbeddingProvider(), "headache")

    items = await retrieve_evidence(
        db_session, FakeEmbeddingProvider(), PgVectorStore(), "how long does a tension headache last", top_k=3
    )

    assert len(items) >= 1
    top = items[0]
    assert "headache" in top.content.lower()
    assert top.title == "Tension Headache"
    assert top.publisher == "Test Publisher"
    assert top.url == "https://example.org/headache"
    assert top.source_type == "government_health_guidance"
    assert 0.0 <= top.similarity <= 1.0


async def test_reingest_supersedes_previous_version_and_retrieval_only_sees_current(db_session) -> None:
    knowledge = FakeMedicalKnowledgeProvider()
    embeddings = FakeEmbeddingProvider()

    first = await ingest_topic(db_session, knowledge, embeddings, "headache")
    second = await ingest_topic(db_session, knowledge, embeddings, "headache")

    await db_session.refresh(first[0])
    assert first[0].superseded_status == "superseded"
    assert second[0].superseded_status == "current"
    assert second[0].version == 2

    items = await retrieve_evidence(db_session, embeddings, PgVectorStore(), "tension headache relief")
    assert all(item.source_id == second[0].id for item in items)


async def test_evidence_api_ingest_then_search(client: AsyncClient) -> None:
    headers = await _authed_headers(client, "evidence@example.com")

    app.dependency_overrides[get_medical_knowledge_provider] = lambda: FakeMedicalKnowledgeProvider()
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    try:
        ingest_resp = await client.post("/evidence/ingest", headers=headers, json={"topic": "headache"})
        assert ingest_resp.status_code == 201
        assert len(ingest_resp.json()) == 1

        search_resp = await client.get(
            "/evidence", headers=headers, params={"query": "how long does a headache last", "top_k": 3}
        )
    finally:
        del app.dependency_overrides[get_medical_knowledge_provider]
        del app.dependency_overrides[get_embedding_provider]

    assert search_resp.status_code == 200
    body = search_resp.json()
    assert len(body) >= 1
    assert body[0]["title"] == "Tension Headache"
    assert body[0]["url"] == "https://example.org/headache"


async def test_evidence_search_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/evidence", params={"query": "headache"})
    assert resp.status_code in (401, 403)
