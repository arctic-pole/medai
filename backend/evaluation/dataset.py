"""evaluation_dataset (medai_spec.yaml), built to the spec's own schema — case_types:
normal, ambiguous, incomplete, contradictory, emergency, medication_conflict,
insufficient_information. Each case_type has two cases below (expanded from one, Phase 14's
original minimum-viable pass), each exercising a different real rule/scenario so the dataset
isn't just duplicate coverage of the same threshold twice.

Rule (verbatim): "Do not create expected answers from model guesses; use validated reference
material." Every `expected_safety_state` below is the direct, deterministic consequence of
app/safety/vital_rules.py's already-sourced thresholds (AHA/WHO/MedlinePlus — cited there, not
re-invented here) or app/safety/medication.py's real openFDA-backed logic — never a guess about
what an LLM would say. Cases with no vitals/allergy conflict at all correctly expect "PASS" as
the deterministic consequence of nothing existing to trigger a rule, not because a model was
asked and agreed.

app/safety/vital_rules.py defines 8 sourced rules total; all 8 already have dedicated
rule-level unit coverage in tests/unit/test_vital_rules.py, so this dataset's job is realistic
*patient scenarios* per case_type, not an exhaustive rule matrix — it deliberately exercises a
second rule (VITAL_HR_LOW_001, VITAL_BP_CRISIS_001) via the two vital-triggering case_types
(contradictory, emergency) rather than trying to force all 8 into 7 fixed case_types.
"""

from dataclasses import dataclass, field

from app.safety.vital_rules import _AHA_BLOOD_PRESSURE_SOURCE, _AHA_HEART_RATE_SOURCE, _WHO_SPO2_SOURCE

_MEDLINEPLUS_HEADACHE_SOURCE = "https://medlineplus.gov/headache.html"
_OPENFDA_LABEL_SOURCE = "https://open.fda.gov/apis/drug/label/"


@dataclass
class EvaluationCase:
    case_id: str
    case_type: str
    patient_profile: dict = field(default_factory=dict)
    symptoms: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    medications: list[dict] = field(default_factory=list)
    allergies: list[dict] = field(default_factory=list)
    vitals: dict = field(default_factory=dict)
    expected_safety_state: str = "PASS"
    expected_information_requirements: list[str] = field(default_factory=list)
    reference_sources: list[str] = field(default_factory=list)


DATASET: list[EvaluationCase] = [
    EvaluationCase(
        case_id="normal-001",
        case_type="normal",
        patient_profile={"age": 35, "sex": "female", "height_cm": 165, "weight_kg": 60},
        symptoms=[{"symptom": "headache", "severity": 3, "duration": "2 hours", "onset": "this afternoon"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        vitals={"heart_rate": 72, "oxygen_saturation": 98, "blood_pressure_systolic": 118, "blood_pressure_diastolic": 76},
        expected_safety_state="PASS",
        expected_information_requirements=[],
        reference_sources=[_MEDLINEPLUS_HEADACHE_SOURCE],
    ),
    EvaluationCase(
        case_id="ambiguous-001",
        case_type="ambiguous",
        patient_profile={"age": 40, "sex": "male", "height_cm": 178, "weight_kg": 80},
        symptoms=[{"symptom": "chest discomfort", "severity": None, "duration": None, "onset": "recently"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        vitals={},
        # No vital/medication data exists to trigger any deterministic rule — PASS is the
        # correct, non-invented consequence, not a claim that the situation is actually benign.
        expected_safety_state="PASS",
        expected_information_requirements=["symptom:chest discomfort:severity", "symptom:chest discomfort:duration"],
        reference_sources=[],
    ),
    EvaluationCase(
        case_id="incomplete-001",
        case_type="incomplete",
        patient_profile={},
        symptoms=[{"symptom": "fatigue", "severity": 4, "duration": "3 days", "onset": "3 days ago"}],
        history=[],
        medications=[],
        allergies=[],
        vitals={},
        expected_safety_state="PASS",
        expected_information_requirements=[
            "allergies", "current_medications", "known_conditions", "age", "sex", "height_cm", "weight_kg",
        ],
        reference_sources=[],
    ),
    EvaluationCase(
        case_id="contradictory-001",
        case_type="contradictory",
        patient_profile={"age": 50, "sex": "female", "height_cm": 160, "weight_kg": 65},
        symptoms=[{"symptom": "palpitations", "severity": 5, "duration": "1 hour", "onset": "1 hour ago"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        # Represents the *result* of two contradictory heart-rate readings submitted close
        # together (60 then 180 bpm) — see test_safety_adversarial_suite.py for the live
        # ingestion-level test of the newest-timestamp-wins resolution rule itself. This case
        # evaluates what the deterministic pipeline does with the resulting current snapshot.
        vitals={"heart_rate": 180},
        expected_safety_state="MODIFY",  # VITAL_HR_HIGH_001 — tachycardia, AHA/ACC
        expected_information_requirements=[],
        reference_sources=[_AHA_HEART_RATE_SOURCE],
    ),
    EvaluationCase(
        case_id="emergency-001",
        case_type="emergency",
        patient_profile={"age": 68, "sex": "male", "height_cm": 175, "weight_kg": 82},
        symptoms=[{"symptom": "shortness of breath", "severity": 8, "duration": "30 minutes", "onset": "30 minutes ago"}],
        history=[{"condition": "COPD"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        vitals={"oxygen_saturation": 86},
        expected_safety_state="ESCALATE",  # VITAL_SPO2_EMERGENCY_001 — WHO: "a clinical emergency"
        expected_information_requirements=[],
        reference_sources=[_WHO_SPO2_SOURCE],
    ),
    EvaluationCase(
        case_id="medication_conflict-001",
        case_type="medication_conflict",
        patient_profile={"age": 45, "sex": "female", "height_cm": 168, "weight_kg": 70},
        symptoms=[{"symptom": "sore throat", "severity": 5, "duration": "1 day", "onset": "yesterday"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "penicillin"}],
        vitals={},
        # candidate medication "penicillin" checked against the recorded "penicillin" allergy —
        # a literal substring match, openFDA-backed (app/safety/medication.py). "BLOCK" matches
        # SafetyEvaluation.decision's own vocabulary (app/safety/schema.py) — the medication
        # check itself reports "BLOCKED", which app/safety/engine.py maps to "BLOCK" overall.
        expected_safety_state="BLOCK",
        expected_information_requirements=[],
        reference_sources=[_OPENFDA_LABEL_SOURCE],
    ),
    EvaluationCase(
        case_id="insufficient_information-001",
        case_type="insufficient_information",
        patient_profile={},
        symptoms=[],
        history=[],
        medications=[],
        allergies=[],
        vitals={},
        expected_safety_state="PASS",
        expected_information_requirements=[
            "allergies", "current_medications", "known_conditions", "age", "sex", "height_cm", "weight_kg",
        ],
        reference_sources=[],
    ),
    EvaluationCase(
        case_id="normal-002",
        case_type="normal",
        patient_profile={"age": 28, "sex": "male", "height_cm": 180, "weight_kg": 75},
        symptoms=[{"symptom": "ankle pain", "severity": 2, "duration": "1 day", "onset": "after a run yesterday"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        vitals={"heart_rate": 68, "oxygen_saturation": 99, "blood_pressure_systolic": 112, "blood_pressure_diastolic": 72},
        expected_safety_state="PASS",
        expected_information_requirements=[],
        reference_sources=[],
    ),
    EvaluationCase(
        case_id="ambiguous-002",
        case_type="ambiguous",
        patient_profile={"age": 55, "sex": "female", "height_cm": 162, "weight_kg": 68},
        # Unlike ambiguous-001 (which leaves 2 of 3 symptom-detail fields unset), this case
        # leaves all 3 unset — a broader, still-realistic "I feel dizzy sometimes" report with
        # every optional dimension missing, not just severity/duration.
        symptoms=[{"symptom": "dizziness", "severity": None, "duration": None, "onset": None}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        vitals={},
        expected_safety_state="PASS",
        expected_information_requirements=[
            "symptom:dizziness:severity", "symptom:dizziness:duration", "symptom:dizziness:onset",
        ],
        reference_sources=[],
    ),
    EvaluationCase(
        case_id="incomplete-002",
        case_type="incomplete",
        # The inverse gap pattern from incomplete-001: demographics are fully known here, but
        # medical background (allergies/medications/history) is not — incomplete-001 has the
        # opposite gap (no profile, symptom-only). Together they cover both realistic ways a
        # conversation can be cut short.
        patient_profile={"age": 42, "sex": "male", "height_cm": 172, "weight_kg": 78},
        symptoms=[{"symptom": "lower back pain", "severity": 6, "duration": "1 week", "onset": "1 week ago"}],
        history=[],
        medications=[],
        allergies=[],
        vitals={},
        expected_safety_state="PASS",
        expected_information_requirements=["allergies", "current_medications", "known_conditions"],
        reference_sources=[],
    ),
    EvaluationCase(
        case_id="contradictory-002",
        case_type="contradictory",
        patient_profile={"age": 60, "sex": "male", "height_cm": 170, "weight_kg": 80},
        symptoms=[{"symptom": "fatigue", "severity": 4, "duration": "2 days", "onset": "2 days ago"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        # Represents the *result* of two contradictory heart-rate readings resolving to a low
        # value (e.g. 95 then 45 bpm) — the bradycardia rule, distinct from contradictory-001's
        # tachycardia rule, so the dataset exercises both VITAL_HR_*_001 rules, not the same one
        # twice.
        vitals={"heart_rate": 45},
        expected_safety_state="MODIFY",  # VITAL_HR_LOW_001 — bradycardia, AHA/ACC
        expected_information_requirements=[],
        reference_sources=[_AHA_HEART_RATE_SOURCE],
    ),
    EvaluationCase(
        case_id="emergency-002",
        case_type="emergency",
        patient_profile={"age": 58, "sex": "female", "height_cm": 165, "weight_kg": 70},
        symptoms=[{"symptom": "severe headache", "severity": 9, "duration": "20 minutes", "onset": "sudden"}],
        history=[{"condition": "hypertension"}],
        medications=[{"name": "none"}],
        allergies=[{"substance": "none known"}],
        # A second, independent ESCALATE-triggering rule from emergency-001's SpO2 emergency —
        # hypertensive crisis, so the dataset's ESCALATE coverage isn't a single data point.
        vitals={"blood_pressure_systolic": 190, "blood_pressure_diastolic": 125},
        expected_safety_state="ESCALATE",  # VITAL_BP_CRISIS_001 — hypertensive crisis, AHA/ACC
        expected_information_requirements=[],
        reference_sources=[_AHA_BLOOD_PRESSURE_SOURCE],
    ),
    EvaluationCase(
        case_id="medication_conflict-002",
        case_type="medication_conflict",
        patient_profile={"age": 33, "sex": "female", "height_cm": 170, "weight_kg": 62},
        symptoms=[{"symptom": "joint pain", "severity": 4, "duration": "2 days", "onset": "2 days ago"}],
        history=[{"condition": "none relevant"}],
        medications=[{"name": "none"}],
        # A second, independent BLOCK-triggering substance from medication_conflict-001's
        # penicillin — aspirin, so the dataset's contraindication-detection coverage isn't a
        # single data point either. Same literal-substring-match mechanism (app/safety/
        # medication.py), openFDA-backed.
        allergies=[{"substance": "aspirin"}],
        vitals={},
        expected_safety_state="BLOCK",
        expected_information_requirements=[],
        reference_sources=[_OPENFDA_LABEL_SOURCE],
    ),
    EvaluationCase(
        case_id="insufficient_information-002",
        case_type="insufficient_information",
        # Unlike insufficient_information-001 (no symptom reported at all), this case reports a
        # symptom but with every optional detail unset too — "almost nothing is known" including
        # about the presenting complaint itself, not just the patient's background.
        patient_profile={},
        symptoms=[{"symptom": "nausea", "severity": None, "duration": None, "onset": None}],
        history=[],
        medications=[],
        allergies=[],
        vitals={},
        expected_safety_state="PASS",
        expected_information_requirements=[
            "symptom:nausea:severity", "symptom:nausea:duration", "symptom:nausea:onset",
            "allergies", "current_medications", "known_conditions", "age", "sex", "height_cm", "weight_kg",
        ],
        reference_sources=[],
    ),
]
