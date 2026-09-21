from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Patient
from app.patient_state.assembler import build_patient_state
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.vector_store.base import VectorStore
from app.rag.retrieval import retrieve_evidence
from app.reasoning.schema import EvidencePackage


def _build_retrieval_query(state) -> str:
    """A crude but deterministic query built only from already-structured symptom fields —
    never the raw conversation transcript (prompt_safety: user text is untrusted, and
    patient_state.rules: the LLM must not reason from unstructured text directly here either)."""

    parts: list[str] = []
    for symptom in state.symptoms:
        parts.append(symptom.symptom)
        if symptom.location:
            parts.append(symptom.location)
        if symptom.progression:
            parts.append(symptom.progression)
    return " ".join(parts)


async def build_evidence_package(
    db: AsyncSession,
    patient: Patient,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStore,
    top_k: int = 5,
) -> EvidencePackage:
    """Assembles the evidence_package.schema object the clinical reasoner receives — combining
    Phase 3's patient_state with Phase 5's retrieval, scoped to the patient's own symptoms
    (rag_pipeline.rule: "LLM must not receive arbitrary unrelated documents")."""

    state = await build_patient_state(db, patient)

    query = _build_retrieval_query(state)
    retrieved = await retrieve_evidence(db, embedding_provider, vector_store, query, top_k) if query else []

    return EvidencePackage(
        patient_state=state,
        relevant_vitals=[
            f"{vtype}: {v['value']} {v['unit']} (quality: {v['quality']}, recorded {v['timestamp']})"
            for vtype, v in state.vitals.items()
        ],
        relevant_history=[h.condition for h in state.medical_history],
        retrieved_evidence=retrieved,
        known_unknowns=state.unknowns,
        # Populated by the caller if it has already run the safety engine before building this
        # package — build_evidence_package itself doesn't call evaluate_safety (Phase 7), since
        # today's callers (e.g. app/api/assessment.py) run safety evaluation as a sibling step,
        # not a prerequisite, of evidence-package assembly.
        safety_flags=[],
    )
