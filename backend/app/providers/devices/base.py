from abc import ABC, abstractmethod

from app.vitals.schema import NormalizedMeasurement, VitalType


class DeviceUnavailable(Exception):
    """vital_system.rules: "If device fails: return {status: unavailable, reason: DEVICE_ERROR};
    conversation manager may ask user to provide manually." Raising this — never returning
    fabricated data — is how a DeviceAdapter signals that failure."""


class DeviceAdapter(ABC):
    """architecture.provider_interfaces: DeviceAdapter. vital_system.device_pipeline's
    DEVICE -> DEVICE_ADAPTER step: turns one raw device reading into a NormalizedMeasurement.

    Manual entry, the only path reachable via the API before Phase 10, is deliberately NOT
    built as a DeviceAdapter: there is no device to read from, only a user-provided value, so
    forcing it through this interface would misrepresent it as a device reading it isn't — see
    app/api/vitals.py, which constructs a NormalizedMeasurement with source="manual" directly
    instead.

    Still no backend-side (Python) concrete implementation as of Phase 10, and — for Health
    Connect specifically — there never can be one: Health Connect's data lives in an OS-level
    store on the user's own device, gated by that device's own runtime permission grants, so
    only the app process running on that device can ever call its SDK. This class's read(type)
    -> NormalizedMeasurement shape assumes a backend-callable adapter (e.g. a cloud REST API
    like Fitbit/Withings would fit here); Health Connect can't implement it at all. Its real
    concrete adapter is client-side: mobile/lib/services/health_connect_adapter.dart, using the
    `health` package (https://pub.dev/packages/health) to read from Health Connect on Android
    and posting the resulting readings to POST /vitals/sync (app/api/vitals.py) — the
    VITAL_SERVICE entry point for this data, since this class's read() cannot be.
    """

    @abstractmethod
    async def read(self, vital_type: VitalType) -> NormalizedMeasurement: ...
