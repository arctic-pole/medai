import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.patient_state.schema import PatientState
from app.schemas.evidence import EvidenceItem

Status = Literal["normal", "caution", "urgent", "emergency"]
Confidence = Literal["low", "moderate", "high"]


class EvidencePackage(BaseModel):
    """evidence_package.schema, verbatim field set. This — not raw conversation text — is the
    only thing the clinical reasoner receives (evidence_package.rule)."""

    patient_state: PatientState
    relevant_vitals: list[str] = Field(default_factory=list)  # empty until Phase 9
    relevant_history: list[str] = Field(default_factory=list)
    retrieved_evidence: list[EvidenceItem] = Field(default_factory=list)
    known_unknowns: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)  # empty until Phase 7


class EvidenceReference(BaseModel):
    """A claim in the assessment, tied to a specific retrieved evidence item by id — this is
    what makes "grounded in retrieved evidence" checkable in code, not just a description the
    model could invent (clinical_reasoner.must_not: invent_evidence_or_medication_info)."""

    source_id: uuid.UUID
    note: str


class Assessment(BaseModel):
    """output_schema, verbatim field set — response_states/rule: do not add fields or
    severity states without authorisation. This is Phase 6's internal output only; it is NOT
    released to any user (no API endpoint) until safety_engine (Phase 7) and output_validator
    (Phase 8) exist to gate it — see architecture.bypass_forbidden."""

    status: Status
    summary: str
    possible_explanations: list[str] = Field(default_factory=list)
    known_information: list[str] = Field(default_factory=list)
    unknown_information: list[str] = Field(default_factory=list)
    vital_summary: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    treatment_options: list[str] = Field(default_factory=list)
    medication_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    escalation: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: Confidence
    limitations: list[str] = Field(default_factory=list)
