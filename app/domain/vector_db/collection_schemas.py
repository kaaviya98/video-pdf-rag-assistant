from collections.abc import Callable
from typing import Any

import weaviate.classes as wvc

from django.conf import settings

VectorStoreConfig = dict[str, Any]  # text_key: str, attributes: list[str]


def _build_collection_registry() -> dict[str, dict[str, Any]]:
    return {
        settings.VECTOR_DB_PDF_COLLECTION_NAME: {
            "get_properties": pdf_collection_properties,
            "text_key": "content",
            "attributes": ["asset_id", "chunk_type", "title", "pages", "citations"],
        },
        settings.VECTOR_DB_VIDEO_COLLECTION_NAME: {
            "get_properties": video_collection_properties,
            "text_key": "content",
            "attributes": [
                "asset_id",
                "segment_id",
                "segment_order",
                "start_sec",
                "end_sec",
                "transcript_line_numbers",
                "topic_title",
            ],
        },
    }


def get_collection_properties(collection_name: str) -> list[wvc.config.Property]:
    entry = _build_collection_registry().get(collection_name)
    if entry is None:
        raise ValueError(f"Unknown collection name for schema: {collection_name!r}")
    get_properties: Callable[[], list[wvc.config.Property]] = entry["get_properties"]
    return get_properties()


def get_vector_store_config(collection_name: str) -> VectorStoreConfig:
    entry = _build_collection_registry().get(collection_name)
    if entry is None:
        raise ValueError(
            f"Unknown collection name for vector store config: {collection_name!r}"
        )
    return {
        "text_key": entry["text_key"],
        "attributes": list(entry["attributes"]),
    }


def pdf_collection_properties() -> list[wvc.config.Property]:
    return [
        wvc.config.Property(
            name="asset_id",
            data_type=wvc.config.DataType.UUID,
            description="Reference to Django Asset model ID",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="content",
            data_type=wvc.config.DataType.TEXT,
            description="The main text content of the chunk",
            tokenization=wvc.config.Tokenization.WORD,
            index_searchable=True,
        ),
        wvc.config.Property(
            name="chunk_type",
            data_type=wvc.config.DataType.TEXT,
            description="Type of chunk: section, subsection, footnote",
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="title",
            data_type=wvc.config.DataType.TEXT,
            description="Title or heading text for this chunk",
            tokenization=wvc.config.Tokenization.WORD,
            index_searchable=True,
        ),
        wvc.config.Property(
            name="pages",
            data_type=wvc.config.DataType.INT_ARRAY,
            description="List of page numbers this chunk belongs to",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="citations",
            data_type=wvc.config.DataType.OBJECT_ARRAY,
            description="Array of citation objects with page and bbox info",
            skip_vectorization=True,
            nested_properties=[
                wvc.config.Property(
                    name="page",
                    data_type=wvc.config.DataType.INT,
                    description="Page number of the citation",
                ),
                wvc.config.Property(
                    name="bbox",
                    data_type=wvc.config.DataType.NUMBER_ARRAY,
                    description="Bounding box of the citation",
                ),
            ],
        ),
    ]


def video_collection_properties() -> list[wvc.config.Property]:
    return [
        wvc.config.Property(
            name="asset_id",
            data_type=wvc.config.DataType.UUID,
            description="Reference to Django Asset model ID",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="segment_id",
            data_type=wvc.config.DataType.TEXT,
            description="Unique logical id for the segment",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="segment_order",
            data_type=wvc.config.DataType.INT,
            description="Order of the segment within the asset",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="start_sec",
            data_type=wvc.config.DataType.NUMBER,
            description="Segment start timestamp in seconds",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="end_sec",
            data_type=wvc.config.DataType.NUMBER,
            description="Segment end timestamp in seconds",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="transcript_line_numbers",
            data_type=wvc.config.DataType.INT_ARRAY,
            description="Line numbers of the topic in the transcript",
            index_filterable=True,
            skip_vectorization=True,
        ),
        wvc.config.Property(
            name="topic_title",
            data_type=wvc.config.DataType.TEXT,
            description="Short title or topic heading for the segment",
            tokenization=wvc.config.Tokenization.WORD,
            index_searchable=True,
        ),
        wvc.config.Property(
            name="content",
            data_type=wvc.config.DataType.TEXT,
            description="Hybrid embedding text for semantic search",
            tokenization=wvc.config.Tokenization.WORD,
            index_searchable=True,
        ),
    ]
