import asyncio

from app.providers.embeddings.base import EmbeddingProvider

# Per the BAAI/bge-large-en-v1.5 model card (https://huggingface.co/BAAI/bge-large-en-v1.5):
# "For retrieval task, please use `Represent this sentence for searching relevant passages:`
# as instruction for query text -- no instruction needed for passage text."
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class SentenceTransformersProvider(EmbeddingProvider):
    """Self-hosted, no API key required. Loads lazily on first use (not at import/app-startup
    time) so tests and unrelated requests aren't slowed down by a ~1.3GB model load."""

    _MODEL_NAME = "BAAI/bge-large-en-v1.5"
    _DIMENSIONS = 1024

    def __init__(self) -> None:
        self._model = None

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._MODEL_NAME)
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(self._encode, [_QUERY_INSTRUCTION + text])
        return vectors[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [vec.tolist() for vec in embeddings]
