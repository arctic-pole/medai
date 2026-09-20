import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.encrypted_types import EncryptedString
from app.db.session import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    patient: Mapped["Patient"] = relationship(back_populates="user", uselist=False)


class Patient(Base):
    """A patient record, 1:1 with a user — this prototype models a single-patient-per-account
    personal health assistant, per ux.primary_action "Talk to Health AI"."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="patient")
    profile: Mapped["PatientProfile"] = relationship(back_populates="patient", uselist=False)
    medical_history: Mapped[list["MedicalHistory"]] = relationship(back_populates="patient")
    allergies: Mapped[list["Allergy"]] = relationship(back_populates="patient")
    current_medications: Mapped[list["CurrentMedication"]] = relationship(back_populates="patient")


class PatientProfile(Base):
    """Covers patient_profile.required_fields that are scalar demographic/consent data.
    known_conditions/allergies/current_medications/relevant_history live in their own tables
    per database.tables, and are assembled into the logical "profile" at the API layer."""

    __tablename__ = "patient_profiles"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), primary_key=True
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    emergency_contact_name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    consent_status: Mapped[str] = mapped_column(String, default="not_provided", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patient: Mapped["Patient"] = relationship(back_populates="profile")


class MedicalHistory(Base):
    """Covers both patient_profile's known_conditions and relevant_history."""

    __tablename__ = "medical_history"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    condition: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)  # active | resolved
    notes: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patient: Mapped["Patient"] = relationship(back_populates="medical_history")


class Allergy(Base):
    __tablename__ = "allergies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    substance: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    reaction: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patient: Mapped["Patient"] = relationship(back_populates="allergies")


class CurrentMedication(Base):
    __tablename__ = "current_medications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    name: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    dosage: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    frequency: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    patient: Mapped["Patient"] = relationship(back_populates="current_medications")


class Consent(Base):
    """Not an explicit table in database.tables, but required to satisfy
    security.consent_record_fields (user, consent_type, timestamp, version, status) as an
    append-only consent event log, distinct from patient_profiles.consent_status (current
    value). Flagged in IMPLEMENTATION_PLAN.md / the Phase 1 completion report."""

    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # granted | withdrawn
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """Phase 2: raw conversation container. No medical reasoning happens against these rows —
    see phases.2_conversation.constraint. Structured extraction into patient_state is Phase 3."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    """content is encrypted at rest like Phase 1's sensitive fields — a conversation transcript
    can carry the same kind of sensitive information as medical_history/allergies. Untrusted
    per prompt_safety.untrusted_inputs; never reasoned over directly (see conversation.rule in
    app/conversation/stub_reply.py's docstring)."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class AuditLog(Base):
    """Only fields in security.logging.allowed are ever written here — see app/audit/middleware.py."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_uuid: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    module: Mapped[str] = mapped_column(String, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
