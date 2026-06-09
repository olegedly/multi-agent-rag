"""OpenRouter embedding client — OpenAI-compatible ``POST /v1/embeddings``.

Uses ``HttpTransport`` from the shared HTTP client layer.
"""

from backend.embeddings.protocol import EmbeddingError
from backend.http_client import HttpTransport, Transport, TransportError


class OpenRouterEmbeddingClient:
    """An embedding client for OpenAI-compatible embedding endpoints.

    Parameters
    ----------
    model : str
        The embedding model name (e.g. ``"qwen/qwen3-embedding-768"``).
    api_key : str
        API key for the embedding provider.
    base_url : str
        Base URL of the API (e.g. ``"https://openrouter.ai/api/v1"``).
    dimensions : int
        Output vector dimensionality (MRL). Default 768.
    transport : Transport, optional
        HTTP transport. When omitted, creates a fresh ``HttpTransport``.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        dimensions: int = 768,
        transport: Transport | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.dimensions = dimensions
        self._transport = transport or HttpTransport()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into 768-dim vectors.

        Parameters
        ----------
        texts : list[str]
            Texts to embed.

        Returns
        -------
        list[list[float]]
            Embedding vectors in the same order as ``texts``.

        Raises
        ------
        EmbeddingError
            On API errors (4xx/5xx).
        """
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimensions,
        }

        try:
            response = await self._transport.send(url, headers, body)
        except TransportError as exc:
            raise EmbeddingError(
                status=exc.status,
                message=str(exc),
            ) from exc
        except Exception as exc:
            raise EmbeddingError(
                status=0,
                message=str(exc),
            ) from exc

        data = response.json()
        # Sort by index to preserve order (API may return out of order)
        sorted_data = sorted(data["data"], key=lambda d: d["index"])
        return [entry["embedding"] for entry in sorted_data]
