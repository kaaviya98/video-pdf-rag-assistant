from functools import lru_cache
from typing import Any

import weaviate
from langchain_openai import OpenAIEmbeddings
from langchain_weaviate import WeaviateVectorStore
from weaviate.classes.init import Auth

from app.config import get_settings


@lru_cache
def get_weaviate_client():
    settings = get_settings()
    if settings.weaviate_api_key:
        return weaviate.connect_to_weaviate_cloud(
            cluster_url=settings.weaviate_url,
            auth_credentials=Auth.api_key(settings.weaviate_api_key),
        )
    return weaviate.connect_to_local(
        host=settings.weaviate_url.replace("http://", "").replace("https://", "").split(":")[0],
        port=int(settings.weaviate_url.rsplit(":", 1)[-1]),
    )


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(model=settings.embedding_model, api_key=settings.openai_api_key)


def get_vector_store(collection_name: str) -> WeaviateVectorStore:
    return WeaviateVectorStore(
        client=get_weaviate_client(),
        index_name=collection_name,
        text_key="text",
        embedding=get_embeddings(),
    )


def ensure_collections() -> None:
    client = get_weaviate_client()
    settings = get_settings()
    for name in (settings.pdf_collection, settings.video_collection):
        if not client.collections.exists(name):
            client.collections.create(
                name=name,
                vector_config=weaviate.classes.config.Configure.Vectors.self_provided(),
            )


def add_documents(collection_name: str, documents: list[Any]) -> None:
    if documents:
        get_vector_store(collection_name).add_documents(documents)
