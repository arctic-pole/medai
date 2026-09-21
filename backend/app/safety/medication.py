from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Allergy, CurrentMedication, MedicalHistory, Patient, PatientProfile
from app.providers.medication_db.base import MedicationDBProvider
from app.safety.schema import MedicationCheckResult


def _mentions(haystack: str | None, needle: str | None) -> bool:
    return bool(haystack) and bool(needle) and needle.lower() in haystack.lower()


async def check_candidate_medication(
    db: AsyncSession, patient: Patient, candidate_name: str, medication_db: MedicationDBProvider
) -> MedicationCheckResult:
    """medication_safety.pipeline, in order: CANDIDATE_MEDICATION -> MEDICATION_DB ->
    ALLERGY_CHECK -> CURRENT_MED_CHECK -> CONDITION_CHECK -> CONTRAINDICATION_CHECK ->
    INTERACTION_CHECK -> VALIDATOR -> ALLOWED|BLOCKED|REQUIRES_REVIEW.

    Interaction/contraindication detection is text-matching against openFDA label sections —
    a heuristic, not a validated structured drug-interaction engine (openFDA's label endpoint
    exposes label prose, not a structured interaction graph). Concretely: it catches literal
    substring matches only, so it will BLOCK "penicillin" for a "penicillin" allergy but will
    NOT catch a drug-class allergy (e.g. "amoxicillin" for a "penicillin" allergy — the words
    share no substring), and will NOT catch a word-form mismatch (a condition recorded as
    "pregnancy" won't match label text that says "pregnant"). This is a real limitation, not
    covered by any deterministic layer here — see docs/AI_PIPELINE.md and
    docs/KNOWN_LIMITATIONS.md. A match always yields BLOCKED or REQUIRES_REVIEW, never a silent
    ALLOWED, so the heuristic's false-negative risk doesn't translate into false reassurance —
    but a false positive can still over-flag. dosage_validity (medication_safety.checks) is not
    implemented: a candidate here is a drug name only, with no proposed dose to validate.
    """

    # MEDICATION_DB
    label = await medication_db.lookup(candidate_name)
    if label is None:
        return MedicationCheckResult(
            candidate_name=candidate_name,
            decision="REQUIRES_REVIEW",
            reasons=[f"No openFDA label found for '{candidate_name}' — cannot verify safety automatically."],
        )

    allergies = (await db.execute(select(Allergy).where(Allergy.patient_id == patient.id))).scalars().all()
    medications = (
        (await db.execute(select(CurrentMedication).where(CurrentMedication.patient_id == patient.id)))
        .scalars()
        .all()
    )
    history = (
        (await db.execute(select(MedicalHistory).where(MedicalHistory.patient_id == patient.id))).scalars().all()
    )
    profile = await db.get(PatientProfile, patient.id)

    names = [n for n in [label.generic_name, *label.brand_names, candidate_name] if n]

    # ALLERGY_CHECK
    blocked_reasons: list[str] = []
    for allergy in allergies:
        if any(_mentions(name, allergy.substance) or _mentions(allergy.substance, name) for name in names):
            blocked_reasons.append(f"Patient has a recorded allergy to '{allergy.substance}'.")

    # CONDITION_CHECK / CONTRAINDICATION_CHECK
    for condition in history:
        if _mentions(label.contraindications, condition.condition):
            blocked_reasons.append(f"Contraindications section mentions the patient's condition: '{condition.condition}'.")

    if blocked_reasons:
        return MedicationCheckResult(
            candidate_name=candidate_name, decision="BLOCKED", reasons=blocked_reasons, source_version=label.source_version
        )

    # CURRENT_MED_CHECK / INTERACTION_CHECK / duplicate_therapy
    review_reasons: list[str] = []
    for med in medications:
        if _mentions(med.name, label.generic_name) or _mentions(label.generic_name, med.name):
            review_reasons.append(f"Candidate appears to duplicate an existing medication: '{med.name}'.")
        elif _mentions(label.drug_interactions, med.name):
            review_reasons.append(f"Drug interactions section mentions current medication '{med.name}'.")

    # age_related_restrictions (heuristic)
    if profile and profile.age is not None and profile.age < 18 and label.pediatric_use:
        if any(
            _mentions(label.pediatric_use, phrase)
            for phrase in ["not been established", "not recommended", "safety and effectiveness"]
        ):
            review_reasons.append("Pediatric use section raises concerns for patients under 18.")

    if label.boxed_warning:
        review_reasons.append("This medication has an FDA boxed warning — requires clinician review.")

    if review_reasons:
        return MedicationCheckResult(
            candidate_name=candidate_name, decision="REQUIRES_REVIEW", reasons=review_reasons, source_version=label.source_version
        )

    return MedicationCheckResult(
        candidate_name=candidate_name,
        decision="ALLOWED",
        reasons=["No allergy, contraindication, interaction, or duplicate-therapy signal found."],
        source_version=label.source_version,
    )
