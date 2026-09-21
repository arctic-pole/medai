import pytest
from sqlalchemy import select

from app.db.models import Patient, PatientProfile, Symptom, User
from app.providers.vector_store.pgvector_store import PgVectorStore
from app.rag.ingest import ingest_topic
from app.reasoning.evidence_package import build_evidence_package
from tests.fakes import FakeEmbeddingProvider, FakeMedicalKnowledgeProvider

pytestmark = pytest.mark.asyncio


async def _make_patient(db_session, email: str) -> Patient:
    user = User(email=email, hashed_password="not-a-real-hash")
    db_session.add(user)
    await db_session.flush()
    patient = Patient(user_id=user.id)
    db_session.add(patient)
    await db_session.flush()
    return patient


async def test_evidence_package_includes_retrieval_scoped_to_symptoms(db_session) -> None:
    patient = await _make_patient(db_session, "package@example.com")
    db_session.add(PatientProfile(patient_id=patient.id, age=34))
    db_session.add(Symptom(patient_id=patient.id, symptom="headache", severity=6, certainty="user_reported"))
    await db_session.commit()

    embeddings = FakeEmbeddingProvider()
    await ingest_topic(db_session, FakeMedicalKnowledgeProvider(), embeddings, "headache")

    package = await build_evidence_package(db_session, patient, embeddings, PgVectorStore())

    assert package.patient_state.patient.age == 34
    assert len(package.patient_state.symptoms) == 1
    assert len(package.retrieved_evidence) >= 1
    assert package.retrieved_evidence[0].title == "Tension Headache"
    assert package.safety_flags == []
    assert package.relevant_vitals == []


async def test_evidence_package_retrieval_empty_when_no_symptoms(db_session) -> None:
    patient = await _make_patient(db_session, "nopackage@example.com")
    await db_session.commit()

    embeddings = FakeEmbeddingProvider()
    package = await build_evidence_package(db_session, patient, embeddings, PgVectorStore())

    assert package.retrieved_evidence == []
