from app.providers.medication_db.base import DrugLabel, MedicationDBProvider
from app.providers.medication_db.openfda_provider import OpenFDAProvider


def get_medication_db_provider() -> MedicationDBProvider:
    return OpenFDAProvider()


__all__ = ["DrugLabel", "MedicationDBProvider", "get_medication_db_provider"]
