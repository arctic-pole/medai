from abc import ABC, abstractmethod

from pydantic import BaseModel


class DrugLabel(BaseModel):
    """Whatever sections an FDA label actually has — OTC "drug facts" labels and prescription
    labels expose different section sets, so every field here is optional."""

    generic_name: str | None = None
    brand_names: list[str] = []
    contraindications: str | None = None
    drug_interactions: str | None = None
    boxed_warning: str | None = None
    warnings: str | None = None
    pediatric_use: str | None = None
    geriatric_use: str | None = None
    source_version: str | None = None


class MedicationDBProvider(ABC):
    """architecture.provider_interfaces doesn't name this interface explicitly, but
    medication_safety.pipeline's MEDICATION_DB step needs one — added following the same
    provider-abstraction pattern as everything else."""

    @abstractmethod
    async def lookup(self, drug_name: str) -> DrugLabel | None: ...
