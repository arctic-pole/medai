from abc import ABC, abstractmethod

from app.vitals.schema import NormalizedMeasurement, VitalType


class DeviceUnavailable(Exception):
    """vital_system.rules: "If device fails: return {status: unavailable, reason: DEVICE_ERROR};
    conversation manager may ask user to provide manually." Raising this — never returning
    fabricated data — is how a DeviceAdapter signals that failure."""


class DeviceAdapter(ABC):
    """architecture.provider_interfaces: DeviceAdapter. vital_system.device_pipeline's
    DEVICE -> DEVICE_ADAPTER step: turns one raw device reading into a NormalizedMeasurement.

    No concrete implementation exists yet — real device/health-platform integration is Phase
    10 ("Do not manufacture hardware"). Manual entry, the only path reachable via the API
    today, is deliberately NOT built as a DeviceAdapter: there is no device to read from, only
    a user-provided value, so forcing it through this interface would misrepresent it as a
    device reading it isn't — see app/api/vitals.py, which constructs a NormalizedMeasurement
    with source="manual" directly instead.
    """

    @abstractmethod
    async def read(self, vital_type: VitalType) -> NormalizedMeasurement: ...
