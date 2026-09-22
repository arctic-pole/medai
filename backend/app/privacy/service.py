from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Allergy,
    AuditLog,
    Consent,
    Conversation,
    CurrentMedication,
    Device,
    MedicalHistory,
    Measurement,
    Message,
    Patient,
    PatientProfile,
    SafetyEvent,
    Symptom,
    User,
    Vital,
)
from app.schemas.auth import UserResponse
from app.schemas.patient import AllergyResponse, MedicalHistoryResponse, MedicationResponse, ProfileResponse
from app.schemas.privacy import (
    AuditLogExport,
    ConsentExport,
    ConversationExport,
    PrivacyExportResponse,
    SafetyEventExport,
)
from app.schemas.symptom import SymptomResponse
from app.schemas.vital import DeviceResponse, MeasurementResponse, VitalResponse


async def export_patient_data(db: AsyncSession, user: User, patient: Patient) -> PrivacyExportResponse:
    """security.minimum_requirements: minimal_data_collection — the data-export half of it: the
    patient can see exactly what MEDAI holds about them, across every table it lives in.
    EncryptedString columns decrypt transparently on read (app/db/encrypted_types.py), so this
    returns real plaintext values — correct here, since the export is for the data's own owner.
    """

    profile = await db.get(PatientProfile, patient.id)

    async def _all(model, where_col, value):
        result = await db.execute(select(model).where(where_col == value).order_by(model.created_at))
        return result.scalars().all()

    history = await _all(MedicalHistory, MedicalHistory.patient_id, patient.id)
    allergies = await _all(Allergy, Allergy.patient_id, patient.id)
    medications = await _all(CurrentMedication, CurrentMedication.patient_id, patient.id)
    symptoms = await _all(Symptom, Symptom.patient_id, patient.id)
    devices = await _all(Device, Device.patient_id, patient.id)
    measurements = await _all(Measurement, Measurement.patient_id, patient.id)
    safety_events = await _all(SafetyEvent, SafetyEvent.patient_id, patient.id)

    vitals_result = await db.execute(select(Vital).where(Vital.patient_id == patient.id))
    vitals = vitals_result.scalars().all()

    audit_logs_result = await db.execute(
        select(AuditLog).where(AuditLog.user_uuid == user.id).order_by(AuditLog.timestamp)
    )
    audit_logs = audit_logs_result.scalars().all()

    consents_result = await db.execute(
        select(Consent).where(Consent.user_id == user.id).order_by(Consent.timestamp)
    )
    consents = consents_result.scalars().all()

    conversations_result = await db.execute(
        select(Conversation).where(Conversation.patient_id == patient.id).order_by(Conversation.created_at)
    )
    conversation_exports = []
    for conversation in conversations_result.scalars().all():
        messages_result = await db.execute(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)
        )
        conversation_exports.append(
            ConversationExport(
                id=conversation.id,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                messages=[m for m in messages_result.scalars().all()],
            )
        )

    return PrivacyExportResponse(
        exported_at=datetime.now(timezone.utc),
        user=UserResponse.model_validate(user),
        patient_id=patient.id,
        profile=ProfileResponse.model_validate(profile) if profile else None,
        medical_history=[MedicalHistoryResponse.model_validate(h) for h in history],
        allergies=[AllergyResponse.model_validate(a) for a in allergies],
        current_medications=[MedicationResponse.model_validate(m) for m in medications],
        symptoms=[SymptomResponse.model_validate(s) for s in symptoms],
        conversations=conversation_exports,
        devices=[DeviceResponse.model_validate(d) for d in devices],
        measurements=[MeasurementResponse.model_validate(m) for m in measurements],
        vitals=[VitalResponse.model_validate(v) for v in vitals],
        safety_events=[SafetyEventExport.model_validate(e) for e in safety_events],
        consents=[ConsentExport.model_validate(c) for c in consents],
        audit_logs=[AuditLogExport.model_validate(a) for a in audit_logs],
    )


async def delete_patient_account(db: AsyncSession, user: User, patient: Patient) -> None:
    """security.minimum_requirements: minimal_data_collection — the delete half. Cascades
    across every patient-owned table in dependency order (deepest child first — no ON DELETE
    CASCADE is declared at the DB level, so this is explicit and auditable rather than implicit
    schema behavior).

    Deliberately does NOT delete `audit_logs`: they carry only the security.logging.allowed
    fields (never raw health data — verified in test_audit_log.py), and retaining them after an
    account deletion is a normal, defensible security practice (detecting abuse patterns,
    investigating an incident that happened before the deletion) rather than a privacy
    violation. This is a judgment call, not a spec requirement, and is documented here and in
    docs/SECURITY.md rather than made silently.
    """

    conversation_ids_result = await db.execute(select(Conversation.id).where(Conversation.patient_id == patient.id))
    conversation_ids = list(conversation_ids_result.scalars().all())
    if conversation_ids:
        await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))

    await db.execute(delete(Vital).where(Vital.patient_id == patient.id))
    await db.execute(delete(Symptom).where(Symptom.patient_id == patient.id))
    await db.execute(delete(Measurement).where(Measurement.patient_id == patient.id))
    await db.execute(delete(Conversation).where(Conversation.patient_id == patient.id))
    await db.execute(delete(Device).where(Device.patient_id == patient.id))
    await db.execute(delete(SafetyEvent).where(SafetyEvent.patient_id == patient.id))
    await db.execute(delete(CurrentMedication).where(CurrentMedication.patient_id == patient.id))
    await db.execute(delete(Allergy).where(Allergy.patient_id == patient.id))
    await db.execute(delete(MedicalHistory).where(MedicalHistory.patient_id == patient.id))
    await db.execute(delete(PatientProfile).where(PatientProfile.patient_id == patient.id))
    await db.execute(delete(Consent).where(Consent.user_id == user.id))
    await db.execute(delete(Patient).where(Patient.id == patient.id))
    await db.execute(delete(User).where(User.id == user.id))

    await db.commit()
