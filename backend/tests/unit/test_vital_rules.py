from app.safety.vital_rules import (
    RULE_BP_CRISIS,
    RULE_BP_STAGE1,
    RULE_BP_STAGE2,
    RULE_HR_HIGH,
    RULE_HR_LOW,
    RULE_SPO2_EMERGENCY,
    RULE_SPO2_LOW,
    RULE_TEMP_FEVER,
    evaluate_vitals,
)


def test_no_rules_triggered_for_entirely_normal_vitals() -> None:
    vitals = {"heart_rate": 72, "systolic_bp": 110, "diastolic_bp": 70, "spo2": 98, "body_temp_f": 98.6}
    assert evaluate_vitals(vitals) == []


def test_empty_vitals_triggers_nothing() -> None:
    assert evaluate_vitals({}) == []


def test_bradycardia_triggers_hr_low() -> None:
    triggered = evaluate_vitals({"heart_rate": 45})
    assert [t.rule.rule_id for t in triggered] == [RULE_HR_LOW.rule_id]


def test_tachycardia_triggers_hr_high() -> None:
    triggered = evaluate_vitals({"heart_rate": 130})
    assert [t.rule.rule_id for t in triggered] == [RULE_HR_HIGH.rule_id]


def test_hypertensive_crisis_takes_precedence_over_lower_bp_stages() -> None:
    triggered = evaluate_vitals({"systolic_bp": 190, "diastolic_bp": 125})
    assert [t.rule.rule_id for t in triggered] == [RULE_BP_CRISIS.rule_id]
    assert triggered[0].rule.action == "ESCALATE"


def test_bp_stage_2() -> None:
    triggered = evaluate_vitals({"systolic_bp": 150, "diastolic_bp": 95})
    assert [t.rule.rule_id for t in triggered] == [RULE_BP_STAGE2.rule_id]


def test_bp_stage_1() -> None:
    triggered = evaluate_vitals({"systolic_bp": 135, "diastolic_bp": 82})
    assert [t.rule.rule_id for t in triggered] == [RULE_BP_STAGE1.rule_id]


def test_spo2_below_90_is_emergency() -> None:
    triggered = evaluate_vitals({"spo2": 87})
    assert [t.rule.rule_id for t in triggered] == [RULE_SPO2_EMERGENCY.rule_id]
    assert triggered[0].rule.action == "ESCALATE"


def test_spo2_90_to_94_is_low_not_emergency() -> None:
    triggered = evaluate_vitals({"spo2": 92})
    assert [t.rule.rule_id for t in triggered] == [RULE_SPO2_LOW.rule_id]
    assert triggered[0].rule.action == "MODIFY"


def test_fever_above_1004_triggers() -> None:
    triggered = evaluate_vitals({"body_temp_f": 101.2})
    assert [t.rule.rule_id for t in triggered] == [RULE_TEMP_FEVER.rule_id]


def test_temp_at_threshold_boundary_not_triggered() -> None:
    # sourced threshold is "above 100.4F", not "100.4F or above"
    assert evaluate_vitals({"body_temp_f": 100.4}) == []


def test_multiple_abnormal_vitals_all_reported() -> None:
    triggered = evaluate_vitals({"heart_rate": 130, "spo2": 87})
    rule_ids = {t.rule.rule_id for t in triggered}
    assert rule_ids == {RULE_HR_HIGH.rule_id, RULE_SPO2_EMERGENCY.rule_id}


def test_every_rule_cites_a_source() -> None:
    from app.safety.vital_rules import ALL_VITAL_RULES

    for rule in ALL_VITAL_RULES:
        assert rule.source.startswith("http")
        assert rule.version
