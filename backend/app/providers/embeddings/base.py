from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """architecture.provider_interfaces: EmbeddingProvider.

    BGE-family models (the concrete choice here) are trained with asymmetric instructions —
    queries get a "represent this for searching" prefix, indexed passages get none — so the
    interface keeps the two paths separate rather than one generic embed().
    """

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...
