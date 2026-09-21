import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SafetyEvent
from app.safety.schema import MedicationCheckResult, SafetyDecision, SafetyEvaluation
from app.safety.vital_rules import evaluate_vitals

# medication decision -> safety_engine.outputs vocabulary
_MEDICATION_DECISION_TO_SAFETY_DECISION = {"BLOCKED": "BLOCK", "REQUIRES_REVIEW": "MODIFY"}

# app/patient_state/schema.py's PatientState.vitals is keyed by Phase 9's vital_system.
# initial_measurements vocabulary (app/vitals/schema.py:VitalType); vital_rules.evaluate_vitals
# expects a different, older key set chosen before Phase 9 existed. Translate rather than
# rename either — vital_rules' keys are already load-bearing in tests and the live-verified
# Phase 7/8 demos.
_PATIENT_STATE_TO_VITAL_RULES_KEY = {
    "heart_rate": "heart_rate",
    "blood_pressure_systolic": "systolic_bp",
    "blood_pressure_diastolic": "diastolic_bp",
    "oxygen_saturation": "spo2",
    "body_temperature": "body_temp_f",
}


def vitals_from_patient_state(patient_state_vitals: dict) -> dict[str, float]:
    """Translates PatientState.vitals (Phase 9's snapshot, keyed by vital_system's own vital
    names, each value a dict with a "value" field per assembler.py) into the flat
    {rule_key: float} shape evaluate_vitals()/evaluate_safety() expect. Silently drops any
    vital type vital_rules.py has no rule for (e.g. respiratory_rate, weight) rather than
    guessing at a mapping — nothing invented, per this module's rules."""

    result: dict[str, float] = {}
    for vital_type, entry in patient_state_vitals.items():
        rule_key = _PATIENT_STATE_TO_VITAL_RULES_KEY.get(vital_type)
        if rule_key is not None:
            result[rule_key] = entry["value"]
    return result


async def evaluate_safety(
    db: AsyncSession,
    *,
    patient_id: uuid.UUID,
    vitals: dict[str, float],
    medication_findings: list[MedicationCheckResult] | None = None,
) -> SafetyEvaluation:
    """safety_engine: runs_independently_of_llm — every input here is plain data (vitals,
    medication check results), never the LLM's own self-reported status. Hard rules take
    precedence over anything an LLM assessment might claim (safety_engine.rule): a caller
    passing an Assessment that says "normal" while SpO2 is 88 still gets ESCALATE from this
    function, because this function never looks at the Assessment's own status field.

    on_failure (an exception propagating out of this function): callers must treat that as
    "not safe to release", not as PASS — this function does not swallow errors into a default
    decision (error_handling.fail_closed_principle).
    """

    medication_findings = medication_findings or []
    triggered_vital_rules = evaluate_vitals(vitals)

    decision: SafetyDecision
    if any(r.rule.action == "ESCALATE" for r in triggered_vital_rules):
        decision = "ESCALATE"
    elif any(f.decision == "BLOCKED" for f in medication_findings):
        decision = "BLOCK"
    elif triggered_vital_rules or any(f.decision == "REQUIRES_REVIEW" for f in medication_findings):
        decision = "MODIFY"
    else:
        decision = "PASS"

    evaluation = SafetyEvaluation(
        decision=decision, triggered_rules=triggered_vital_rules, medication_findings=medication_findings
    )
    await _log_safety_events(db, patient_id, evaluation)
    return evaluation


async def _log_safety_events(db: AsyncSession, patient_id: uuid.UUID, evaluation: SafetyEvaluation) -> None:
    if evaluation.decision == "PASS":
        return

    for triggered in evaluation.triggered_rules:
        db.add(
            SafetyEvent(
                patient_id=patient_id,
                rule_id=triggered.rule.rule_id,
                rule_version=triggered.rule.version,
                decision=triggered.rule.action if triggered.rule.action == "ESCALATE" else "MODIFY",
                detail=triggered.detail,
            )
        )

    for finding in evaluation.medication_findings:
        event_decision = _MEDICATION_DECISION_TO_SAFETY_DECISION.get(finding.decision)
        if event_decision is None:
            continue  # ALLOWED — nothing to log
        db.add(
            SafetyEvent(
                patient_id=patient_id,
                rule_id=f"MEDICATION_SAFETY:{finding.candidate_name}",
                rule_version=finding.source_version or "unknown",
                decision=event_decision,
                detail="; ".join(finding.reasons) or event_decision,
            )
        )

    await db.commit()
