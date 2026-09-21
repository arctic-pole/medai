"""vital_system.validation_stages (1-7), each a clearly-labeled step so the mapping from spec
to code is auditable. Stage 5 (physiological_plausibility) is deliberately NOT the same as
Phase 7's clinical safety thresholds (app/safety/vital_rules.py) — a clinically abnormal but
real reading (e.g. a true SpO2 of 82%) must be accepted and recorded, not rejected as
"unreliable"; rejecting it here would actively suppress the exact data safety_engine needs to
escalate on. This stage only catches objectively-implausible/garbage values (negative numbers,
percentages over 100, readings far beyond any recorded human physiology) — generous sanity
bounds for detecting sensor error or unit confusion, not sourced clinical judgment about what's
healthy. Where a bound below isn't a mathematical/definitional truth (percentages, positivity),
it is deliberately set far wider than any real clinical threshold so it never second-guesses a
genuine extreme reading — see the module-level comment on each bound.
"""

from datetime import datetime, timedelta, timezone

from app.vitals.schema import NormalizedMeasurement, ValidationOutcome

EXPECTED_UNITS: dict[str, str] = {
    "heart_rate": "bpm",
    "oxygen_saturation": "%",
    "blood_pressure_systolic": "mmHg",
    "blood_pressure_diastolic": "mmHg",
    "body_temperature": "F",
    "respiratory_rate": "breaths/min",
    "weight": "kg",
}

# (min, max) — generous garbage-detection bounds, not clinical thresholds (see module docstring).
# oxygen_saturation's bounds are definitional (a percentage cannot be outside 0-100); the rest
# are deliberately far wider than any real clinical concern, chosen only to catch sensor
# error/unit confusion (e.g. a temperature entered in Celsius by mistake).
_SANITY_BOUNDS: dict[str, tuple[float, float]] = {
    "heart_rate": (0, 400),
    "oxygen_saturation": (0, 100),
    "blood_pressure_systolic": (0, 400),
    "blood_pressure_diastolic": (0, 300),
    "body_temperature": (70, 115),
    "respiratory_rate": (0, 100),
    "weight": (0, 700),
}

_MAX_TIMESTAMP_SKEW = timedelta(minutes=5)  # allow for minor clock drift, not future-dated data
_MAX_TIMESTAMP_AGE = timedelta(days=365)  # a "current" reading shouldn't be a year old


def _unreliable(reason: str) -> ValidationOutcome:
    return ValidationOutcome(status="unreliable", reason=reason)


def validate_measurement(measurement: NormalizedMeasurement) -> ValidationOutcome:
    # 1. format — type is a real, recognised measurement type (Literal already enforces this at
    # the pydantic layer; re-checked here so the stage exists explicitly, per the spec's list).
    if measurement.type not in EXPECTED_UNITS:
        return _unreliable(f"unrecognised measurement type: {measurement.type}")

    # 2. unit
    expected_unit = EXPECTED_UNITS[measurement.type]
    if measurement.unit != expected_unit:
        return _unreliable(f"unexpected unit {measurement.unit!r} for {measurement.type} (expected {expected_unit!r})")

    # 3. timestamp
    now = datetime.now(timezone.utc)
    timestamp = measurement.timestamp if measurement.timestamp.tzinfo else measurement.timestamp.replace(tzinfo=timezone.utc)
    if timestamp > now + _MAX_TIMESTAMP_SKEW:
        return _unreliable("timestamp is in the future")
    if timestamp < now - _MAX_TIMESTAMP_AGE:
        return _unreliable("timestamp is implausibly old for a current reading")

    # 4. missing_values — pydantic already requires value/unit/timestamp to be present; this
    # stage exists explicitly so a future optional-value use case still has a named check point.
    if measurement.value is None:  # pragma: no cover — pydantic makes this unreachable today
        return _unreliable("value is missing")

    # 5. physiological_plausibility — see module docstring.
    low, high = _SANITY_BOUNDS[measurement.type]
    if not (low <= measurement.value <= high):
        return _unreliable(f"{measurement.value} is outside the plausible range [{low}, {high}] for {measurement.type}")

    # 6. device_signal_quality
    if measurement.quality == "poor":
        return _unreliable("device-reported signal quality is poor")

    # 7. repeat_measurement_if_required — this is the caller's responsibility once it sees
    # status="unreliable" (vital_system.on_suspicious_measurement: request_another_measurement);
    # nothing to do at this stage beyond having already returned "unreliable" above.

    return ValidationOutcome(status="accepted", measurement=measurement)
