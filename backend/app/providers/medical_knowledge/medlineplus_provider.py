import html
import re
import xml.etree.ElementTree as ET

import httpx

from app.providers.medical_knowledge.base import MedicalKnowledgeProvider, RawDocument

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _TAG_RE.sub("", html.unescape(text)).strip()


class MedlinePlusProvider(MedicalKnowledgeProvider):
    """https://medlineplus.gov/webservices.html — MedlinePlus health topics web service.
    No API key required. Concrete choice for knowledge_base.approved_sources'
    government_health_guidance category (user decision, Phase 5)."""

    _BASE_URL = "https://wsearch.nlm.nih.gov/ws/query"

    def __init__(self, max_documents: int = 3) -> None:
        self._max_documents = max_documents

    async def fetch(self, topic: str) -> list[RawDocument]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                self._BASE_URL, params={"db": "healthTopics", "term": topic, "retmax": self._max_documents}
            )
            response.raise_for_status()

        root = ET.fromstring(response.text)
        documents: list[RawDocument] = []
        for doc_el in root.findall("list/document"):
            url = doc_el.get("url", "")
            fields = {c.get("name"): c.text for c in doc_el.findall("content")}

            title = _clean(fields.get("title"))
            summary = _clean(fields.get("FullSummary"))
            organization = _clean(fields.get("organizationName")) or "National Library of Medicine"

            if not title or not summary or not url:
                continue

            documents.append(
                RawDocument(
                    title=title,
                    publisher=f"MedlinePlus ({organization})",
                    url=url,
                    content=summary,
                    source_type="government_health_guidance",
                )
            )
        return documents
