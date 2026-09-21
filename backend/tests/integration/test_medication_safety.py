import pytest

from app.db.models import Allergy, CurrentMedication, MedicalHistory, Patient, PatientProfile, User
from app.providers.medication_db.base import DrugLabel
from app.safety.medication import check_candidate_medication
from tests.fakes import FakeMedicationDBProvider

pytestmark = pytest.mark.asyncio


async def _make_patient(db_session, email: str) -> Patient:
    user = User(email=email, hashed_password="not-a-real-hash")
    db_session.add(user)
    await db_session.flush()
    patient = Patient(user_id=user.id)
    db_session.add(patient)
    await db_session.flush()
    return patient


async def test_unknown_drug_requires_review(db_session) -> None:
    patient = await _make_patient(db_session, "medA@example.com")
    await db_session.commit()

    result = await check_candidate_medication(db_session, patient, "not-a-real-drug", FakeMedicationDBProvider())

    assert result.decision == "REQUIRES_REVIEW"
    assert "No openFDA label found" in result.reasons[0]


async def test_allergy_match_blocks(db_session) -> None:
    # A literal-substring case: this heuristic cannot catch drug-class allergies (e.g. a
    # "penicillin" allergy vs a candidate named "amoxicillin") since the words don't share a
    # substring either way — see check_candidate_medication's docstring.
    patient = await _make_patient(db_session, "medB@example.com")
    db_session.add(Allergy(patient_id=patient.id, substance="penicillin"))
    await db_session.commit()

    labels = {"penicillin": DrugLabel(generic_name="Penicillin V Potassium")}
    result = await check_candidate_medication(db_session, patient, "penicillin", FakeMedicationDBProvider(labels))

    assert result.decision == "BLOCKED"
    assert "penicillin" in result.reasons[0]


async def test_contraindicated_condition_blocks(db_session) -> None:
    # Literal substring match: "pregnant" (not "pregnancy" — a different word form the
    # substring heuristic would miss, see check_candidate_medication's docstring).
    patient = await _make_patient(db_session, "medC@example.com")
    db_session.add(MedicalHistory(patient_id=patient.id, condition="pregnant"))
    await db_session.commit()

    labels = {
        "warfarin": DrugLabel(
            generic_name="Warfarin",
            contraindications="Warfarin is contraindicated in patients who are pregnant.",
        )
    }
    result = await check_candidate_medication(db_session, patient, "warfarin", FakeMedicationDBProvider(labels))

    assert result.decision == "BLOCKED"
    assert "pregnant" in result.reasons[0]


async def test_drug_interaction_with_current_medication_requires_review(db_session) -> None:
    patient = await _make_patient(db_session, "medD@example.com")
    db_session.add(CurrentMedication(patient_id=patient.id, name="aspirin"))
    await db_session.commit()

    labels = {
        "warfarin": DrugLabel(
            generic_name="Warfarin",
            drug_interactions="Concomitant use of aspirin increases the risk of bleeding.",
        )
    }
    result = await check_candidate_medication(db_session, patient, "warfarin", FakeMedicationDBProvider(labels))

    assert result.decision == "REQUIRES_REVIEW"
    assert any("aspirin" in r for r in result.reasons)


async def test_duplicate_therapy_requires_review(db_session) -> None:
    patient = await _make_patient(db_session, "medE@example.com")
    db_session.add(CurrentMedication(patient_id=patient.id, name="Ibuprofen"))
    await db_session.commit()

    labels = {"ibuprofen": DrugLabel(generic_name="Ibuprofen")}
    result = await check_candidate_medication(db_session, patient, "ibuprofen", FakeMedicationDBProvider(labels))

    assert result.decision == "REQUIRES_REVIEW"
    assert "duplicate" in result.reasons[0].lower()


async def test_pediatric_concern_requires_review(db_session) -> None:
    patient = await _make_patient(db_session, "medF@example.com")
    db_session.add(PatientProfile(patient_id=patient.id, age=10))
    await db_session.commit()

    labels = {
        "somedrug": DrugLabel(
            generic_name="SomeDrug", pediatric_use="Safety and effectiveness have not been established in pediatric patients."
        )
    }
    result = await check_candidate_medication(db_session, patient, "somedrug", FakeMedicationDBProvider(labels))

    assert result.decision == "REQUIRES_REVIEW"
    assert any("pediatric" in r.lower() for r in result.reasons)


async def test_boxed_warning_requires_review(db_session) -> None:
    patient = await _make_patient(db_session, "medG@example.com")
    await db_session.commit()

    labels = {"riskydrug": DrugLabel(generic_name="RiskyDrug", boxed_warning="Risk of serious harm.")}
    result = await check_candidate_medication(db_session, patient, "riskydrug", FakeMedicationDBProvider(labels))

    assert result.decision == "REQUIRES_REVIEW"
    assert "boxed warning" in result.reasons[0].lower()


async def test_clean_candidate_is_allowed(db_session) -> None:
    patient = await _make_patient(db_session, "medH@example.com")
    await db_session.commit()

    labels = {"cleandrug": DrugLabel(generic_name="CleanDrug")}
    result = await check_candidate_medication(db_session, patient, "cleandrug", FakeMedicationDBProvider(labels))

    assert result.decision == "ALLOWED"
