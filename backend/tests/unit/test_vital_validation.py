from datetime import datetime, timedelta, timezone

from app.vitals.schema import NormalizedMeasurement
from app.vitals.validation import validate_measurement


def _measurement(**overrides) -> NormalizedMeasurement:
    base = dict(
        type="heart_rate",
        value=72,
        unit="bpm",
        timestamp=datetime.now(timezone.utc),
        source="manual",
        quality="good",
    )
    base.update(overrides)
    return NormalizedMeasurement(**base)


def test_valid_measurement_is_accepted() -> None:
    outcome = validate_measurement(_measurement())
    assert outcome.status == "accepted"
    assert outcome.measurement is not None


def test_unrecognised_type_is_unreliable() -> None:
    # VitalType is a pydantic Literal, so a real bogus type can't be constructed normally —
    # model_construct() bypasses validation to exercise validate_measurement's own defensive
    # format check directly.
    bogus = NormalizedMeasurement.model_construct(
        type="not_a_real_vital_type",
        value=1,
        unit="x",
        timestamp=datetime.now(timezone.utc),
        source="manual",
        quality="good",
        device_id=None,
        confidence=None,
    )
    outcome = validate_measurement(bogus)
    assert outcome.status == "unreliable"
    assert "unrecognised" in outcome.reason


def test_wrong_unit_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(unit="beats per minute"))
    assert outcome.status == "unreliable"
    assert "unit" in outcome.reason


def test_future_timestamp_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(timestamp=datetime.now(timezone.utc) + timedelta(hours=1)))
    assert outcome.status == "unreliable"
    assert "future" in outcome.reason


def test_implausibly_old_timestamp_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(timestamp=datetime.now(timezone.utc) - timedelta(days=400)))
    assert outcome.status == "unreliable"


def test_negative_value_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(value=-5))
    assert outcome.status == "unreliable"
    assert "plausible range" in outcome.reason


def test_spo2_above_100_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(type="oxygen_saturation", value=105, unit="%"))
    assert outcome.status == "unreliable"


def test_spo2_genuinely_low_is_still_accepted_not_rejected() -> None:
    # A real, dangerously low SpO2 must be accepted and recorded — rejecting it here would
    # suppress exactly the data the safety engine needs to escalate on. See module docstring.
    outcome = validate_measurement(_measurement(type="oxygen_saturation", value=82, unit="%"))
    assert outcome.status == "accepted"


def test_extreme_heart_rate_during_real_exercise_is_still_accepted() -> None:
    outcome = validate_measurement(_measurement(value=190))
    assert outcome.status == "accepted"


def test_poor_signal_quality_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(quality="poor"))
    assert outcome.status == "unreliable"
    assert "signal quality" in outcome.reason


def test_grossly_implausible_value_is_unreliable() -> None:
    outcome = validate_measurement(_measurement(value=9999))
    assert outcome.status == "unreliable"
