import httpx

from app.providers.medication_db.base import DrugLabel, MedicationDBProvider


def _first(record: dict, field: str) -> str | None:
    value = record.get(field)
    return value[0] if isinstance(value, list) and value else None


class OpenFDAProvider(MedicationDBProvider):
    """https://open.fda.gov/apis/drug/label/ — concrete choice for medication_safety's
    MEDICATION_DB step and knowledge_base's official_drug_labels category (user decision,
    Phase 7). No API key required for the query volume this prototype needs."""

    _BASE_URL = "https://api.fda.gov/drug/label.json"

    async def lookup(self, drug_name: str) -> DrugLabel | None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for field in ("generic_name", "brand_name"):
                response = await client.get(
                    self._BASE_URL, params={"search": f'openfda.{field}:"{drug_name}"', "limit": 1}
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                results = response.json().get("results", [])
                if results:
                    return self._parse(results[0])
        return None

    @staticmethod
    def _parse(record: dict) -> DrugLabel:
        openfda = record.get("openfda", {})
        generic_names = openfda.get("generic_name") or []
        return DrugLabel(
            generic_name=generic_names[0] if generic_names else None,
            brand_names=openfda.get("brand_name", []),
            contraindications=_first(record, "contraindications"),
            drug_interactions=_first(record, "drug_interactions"),
            boxed_warning=_first(record, "boxed_warning"),
            warnings=_first(record, "warnings") or _first(record, "warnings_and_cautions") or _first(record, "do_not_use"),
            pediatric_use=_first(record, "pediatric_use"),
            geriatric_use=_first(record, "geriatric_use"),
            source_version=str(record.get("effective_time") or record.get("set_id") or ""),
        )
