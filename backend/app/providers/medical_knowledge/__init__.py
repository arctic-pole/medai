from app.providers.medical_knowledge.base import MedicalKnowledgeProvider, RawDocument
from app.providers.medical_knowledge.medlineplus_provider import MedlinePlusProvider


def get_medical_knowledge_provider() -> MedicalKnowledgeProvider:
    """Concrete choice: MedlinePlus (user decision, Phase 5). PubMed Central and openFDA are
    also user-approved sources (see docs/KNOWN_LIMITATIONS.md) but not yet wired in — adding
    either means writing a new MedicalKnowledgeProvider and combining results at the call site,
    not changing this function's contract."""

    return MedlinePlusProvider()


__all__ = ["MedicalKnowledgeProvider", "RawDocument", "get_medical_knowledge_provider"]
