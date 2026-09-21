from app.providers.embeddings.base import EmbeddingProvider
from app.providers.embeddings.sentence_transformers_provider import SentenceTransformersProvider

_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Concrete choice: BAAI/bge-large-en-v1.5 via sentence-transformers (user decision,
    Phase 5) — self-hosted, no API key. A single process-wide instance is reused so the model
    is loaded at most once (see SentenceTransformersProvider's lazy load)."""

    global _provider
    if _provider is None:
        _provider = SentenceTransformersProvider()
    return _provider


__all__ = ["EmbeddingProvider", "get_embedding_provider"]
