"""safety_engine.emergency_triage: sourced vital-sign thresholds only — nothing here is
invented (agent_rules.behaviour: never fabricate; "Do not hard-code arbitrary medical
thresholds without an authoritative source"). Each rule's `version` field records exactly how
it was verified in this session:

- SpO2 and body-temperature figures: fetched and quoted directly from the primary source
  (the WHO pulse-oximetry manual PDF, and the MedlinePlus body-temperature page).
- Heart-rate and blood-pressure figures: the AHA pages the user supplied block automated
  fetches (HTTP 403), including the AHA's own PDF chart. These are the standard, widely
  published AHA/ACC 2017 guideline figures, corroborated by a direct fetch of Cleveland
  Clinic's heart-rate page (independently citing the same numbers) and cross-checked against
  multiple other reputable clinical sources (e.g. Mayo Clinic) that explicitly attribute the
  same blood-pressure categories to AHA/ACC. This is disclosed, not glossed over, per
  agent_rules — if stronger direct-source confirmation is wanted, an authenticated/manual
  fetch of the AHA pages would be needed.

Sources that stated no explicit numeric threshold for a category were NOT given an invented
one: neither source names a heart-rate "emergency" cutoff distinct from tachycardia/bradycardia
itself, and MedlinePlus's temperature page explicitly does not define a dangerous-high-fever or
hypothermia threshold — so none of those exist as rules below.
"""

from app.safety.schema import SafetyRuleMeta, TriggeredRule

_AHA_HEART_RATE_SOURCE = (
    "https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/"
    "all-about-heart-rate-pulse"
)
_AHA_BLOOD_PRESSURE_SOURCE = "https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings"
_WHO_SPO2_SOURCE = (
    "https://cdn.who.int/media/docs/default-source/patient-safety/pulse-oximetry/"
    "who-ps-pulse-oxymetry-training-manual-en.pdf"
)
_MEDLINEPLUS_TEMP_SOURCE = "https://medlineplus.gov/ency/article/001982.htm"

_VERIFIED_CORROBORATED = "verified-2026-09 (AHA page blocks automated fetch; corroborated via independent clinical sources — see module docstring)"
_VERIFIED_PRIMARY = "verified-2026-09 (direct primary-source fetch, exact quote confirmed)"

RULE_HR_LOW = SafetyRuleMeta(
    rule_id="VITAL_HR_LOW_001",
    condition="Resting heart rate below 60 bpm (bradycardia)",
    severity="moderate",
    action="MODIFY",
    source=_AHA_HEART_RATE_SOURCE,
    version=_VERIFIED_CORROBORATED,
)
RULE_HR_HIGH = SafetyRuleMeta(
    rule_id="VITAL_HR_HIGH_001",
    condition="Resting heart rate above 100 bpm (tachycardia)",
    severity="moderate",
    action="MODIFY",
    source=_AHA_HEART_RATE_SOURCE,
    version=_VERIFIED_CORROBORATED,
)
RULE_BP_CRISIS = SafetyRuleMeta(
    rule_id="VITAL_BP_CRISIS_001",
    condition="Systolic over 180 mmHg and/or diastolic over 120 mmHg (hypertensive crisis)",
    severity="critical",
    action="ESCALATE",
    source=_AHA_BLOOD_PRESSURE_SOURCE,
    version=_VERIFIED_CORROBORATED,
)
RULE_BP_STAGE2 = SafetyRuleMeta(
    rule_id="VITAL_BP_STAGE2_001",
    condition="Systolic 140+ mmHg or diastolic 90+ mmHg (Hypertension Stage 2)",
    severity="moderate",
    action="MODIFY",
    source=_AHA_BLOOD_PRESSURE_SOURCE,
    version=_VERIFIED_CORROBORATED,
)
RULE_BP_STAGE1 = SafetyRuleMeta(
    rule_id="VITAL_BP_STAGE1_001",
    condition="Systolic 130-139 mmHg or diastolic 80-89 mmHg (Hypertension Stage 1)",
    severity="informational",
    action="MODIFY",
    source=_AHA_BLOOD_PRESSURE_SOURCE,
    version=_VERIFIED_CORROBORATED,
)
RULE_SPO2_EMERGENCY = SafetyRuleMeta(
    rule_id="VITAL_SPO2_EMERGENCY_001",
    condition='SpO2 below 90% — WHO: "a clinical emergency and should be treated urgently"',
    severity="critical",
    action="ESCALATE",
    source=_WHO_SPO2_SOURCE,
    version=_VERIFIED_PRIMARY,
)
RULE_SPO2_LOW = SafetyRuleMeta(
    rule_id="VITAL_SPO2_LOW_001",
    condition="SpO2 90-94% (WHO: healthy patients should be 95% or above; 94% or below needs prompt treatment)",
    severity="moderate",
    action="MODIFY",
    source=_WHO_SPO2_SOURCE,
    version=_VERIFIED_PRIMARY,
)
RULE_TEMP_FEVER = SafetyRuleMeta(
    rule_id="VITAL_TEMP_FEVER_001",
    condition='Body temperature above 100.4°F / 38°C — MedlinePlus: "most often means you have a fever"',
    severity="informational",
    action="MODIFY",
    source=_MEDLINEPLUS_TEMP_SOURCE,
    version=_VERIFIED_PRIMARY,
)

ALL_VITAL_RULES = [
    RULE_HR_LOW,
    RULE_HR_HIGH,
    RULE_BP_CRISIS,
    RULE_BP_STAGE2,
    RULE_BP_STAGE1,
    RULE_SPO2_EMERGENCY,
    RULE_SPO2_LOW,
    RULE_TEMP_FEVER,
]


def evaluate_vitals(vitals: dict[str, float]) -> list[TriggeredRule]:
    """vitals: optional float values keyed by heart_rate, systolic_bp, diastolic_bp, spo2,
    body_temp_f. Returns every rule whose condition is met, highest-severity-relevant first
    isn't guaranteed here — callers (app/safety/engine.py) decide overall precedence."""

    triggered: list[TriggeredRule] = []

    heart_rate = vitals.get("heart_rate")
    if heart_rate is not None:
        if heart_rate < 60:
            triggered.append(TriggeredRule(rule=RULE_HR_LOW, detail=f"heart rate {heart_rate} bpm is below 60"))
        elif heart_rate > 100:
            triggered.append(TriggeredRule(rule=RULE_HR_HIGH, detail=f"heart rate {heart_rate} bpm is above 100"))

    systolic = vitals.get("systolic_bp")
    diastolic = vitals.get("diastolic_bp")
    if systolic is not None or diastolic is not None:
        crisis = (systolic is not None and systolic > 180) or (diastolic is not None and diastolic > 120)
        stage2 = (systolic is not None and systolic >= 140) or (diastolic is not None and diastolic >= 90)
        stage1 = (systolic is not None and 130 <= systolic <= 139) or (
            diastolic is not None and 80 <= diastolic <= 89
        )
        reading = f"{systolic if systolic is not None else '?'}/{diastolic if diastolic is not None else '?'} mmHg"
        if crisis:
            triggered.append(TriggeredRule(rule=RULE_BP_CRISIS, detail=f"blood pressure {reading} exceeds crisis threshold"))
        elif stage2:
            triggered.append(TriggeredRule(rule=RULE_BP_STAGE2, detail=f"blood pressure {reading} is Stage 2"))
        elif stage1:
            triggered.append(TriggeredRule(rule=RULE_BP_STAGE1, detail=f"blood pressure {reading} is Stage 1"))

    spo2 = vitals.get("spo2")
    if spo2 is not None:
        if spo2 < 90:
            triggered.append(TriggeredRule(rule=RULE_SPO2_EMERGENCY, detail=f"SpO2 {spo2}% is below 90%"))
        elif spo2 <= 94:
            triggered.append(TriggeredRule(rule=RULE_SPO2_LOW, detail=f"SpO2 {spo2}% is 90-94%"))

    body_temp_f = vitals.get("body_temp_f")
    if body_temp_f is not None and body_temp_f > 100.4:
        triggered.append(TriggeredRule(rule=RULE_TEMP_FEVER, detail=f"temperature {body_temp_f}F exceeds 100.4F"))

    return triggered
