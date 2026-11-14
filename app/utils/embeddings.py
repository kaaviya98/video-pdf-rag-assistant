from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING
from typing import Callable

from langchain_openai import OpenAIEmbeddings

from app.utils.openai import resolve_openai_runtime_config

if TYPE_CHECKING:
    from app.models.organization import Organization

EmbedderFn = Callable[[list[str]], list[list[float]]]


@lru_cache(maxsize=16)
def _get_embeddings_model(
    model: str,
    chunk_size: int,
    api_key: str,
) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        openai_api_key=api_key,
        model=model,
        chunk_size=chunk_size,
    )


def embed_texts(
    texts: list[str],
    *,
    embedder: EmbedderFn | None = None,
    model: str = "text-embedding-3-small",
    chunk_size: int = 64,
    api_key: str | None = None,
    scope_key: str | None = None,
    organization: Organization | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    if embedder is not None:
        return embedder(texts)

    resolved_api_key = (
        api_key
        or resolve_openai_runtime_config(
            organization=organization,
            scope_key=scope_key,
        ).api_key
    )
    if not resolved_api_key:
        raise RuntimeError("OPENAI_API_KEY must be set to compute embeddings")

    embeddings_model = _get_embeddings_model(model, chunk_size, resolved_api_key)
    return embeddings_model.embed_documents(texts)


def embed_video_transcript_window_texts(
    texts: list[str],
    *,
    embedder: EmbedderFn | None = None,
    scope_key: str | None = None,
    organization: Organization | None = None,
) -> list[list[float]]:
    return embed_texts(
        texts,
        embedder=embedder,
        scope_key=scope_key,
        organization=organization,
    )
