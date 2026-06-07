"""Abstract embedding client interface — mirrors the LLM client pattern."""

from typing import Protocol, runtime_checkable


class EmbeddingError(Exception):
    """Raised when the embedding API returns an error response.

    Carries the HTTP status and API error message.
    """

    def __init__(self, status: int, message: str, details: str | None = None):
        self.status = status
        self.details = details
        msg = f"Embedding API error ({status}): {message}"
        if details:
            msg += f" — {details}"
        super().__init__(msg)


@runtime_checkable
class EmbeddingClient(Protocol):
    """Abstract embedding client interface.

    Every provider implementation satisfies this protocol.
    """

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into vectors.

        Returns a list of vectors in the same order as ``texts``.
        Each vector dimension is determined by the provider/model.
        """
        ...
