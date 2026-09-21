from app.providers.vector_store.base import VectorStore
from app.providers.vector_store.pgvector_store import PgVectorStore


def get_vector_store() -> VectorStore:
    return PgVectorStore()


__all__ = ["VectorStore", "get_vector_store"]
