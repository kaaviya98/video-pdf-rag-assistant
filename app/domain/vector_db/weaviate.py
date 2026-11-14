from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

import weaviate
import weaviate.classes as wvc
from django.conf import settings
from langchain.retrievers import MultiQueryRetriever, RePhraseQueryRetriever
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_weaviate import WeaviateVectorStore
from weaviate.classes.init import Auth
from weaviate.classes.query import Filter as WeaviateFilter

from app.domain.vector_db.base import VectorDatabase
from app.domain.vector_db.base import VectorDBClient
from app.domain.vector_db.collection_schemas import get_collection_properties
from app.domain.vector_db.collection_schemas import get_vector_store_config
from app.utils.embeddings import _get_embeddings_model
from app.utils.openai import resolve_openai_runtime_config

if TYPE_CHECKING:
    from app.models.organization import Organization


class WeaviateDatabaseMigrationError(Exception):
    pass


class WeaviateConfigurationError(Exception):
    """Raised when Weaviate configuration is invalid or missing."""


class WeaviateClientError(Exception):
    pass


def _get_openai_embeddings(
    scope_key: str | None = None,
    organization: Organization | None = None,
) -> OpenAIEmbeddings:
    api_key = resolve_openai_runtime_config(
        organization=organization,
        scope_key=scope_key,
    ).api_key
    if not api_key:
        error_message = "No OpenAI API key resolved for embeddings"
        raise WeaviateConfigurationError(error_message)
    return _get_embeddings_model(
        "text-embedding-3-small",
        120,
        api_key,
    )


class WeaviateVectorDatabase(VectorDatabase):
    def __init__(self) -> None:
        self._client: WeaviateVectorDBClient | None = None

    def migrate(self, collection_name: str) -> None:
        client = self.get_client()
        try:
            client.create_collection(
                name=collection_name,
                multi_tenancy_config=wvc.config.Configure.multi_tenancy(
                    enabled=True,
                    auto_tenant_creation=True,
                    auto_tenant_activation=True,
                ),
                properties=self._get_collection_properties(
                    collection_name=collection_name
                ),
            )
        except WeaviateClientError as e:
            raise WeaviateDatabaseMigrationError(e) from e

    def health_check(self) -> dict[str, Any]:
        client = self.get_client()

        return {
            "status": "healthy" if client.is_ready() else "unhealthy",
        }

    def get_client(self) -> "WeaviateVectorDBClient":
        if self._client is None:
            self._client = WeaviateVectorDBClient()

        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _get_collection_properties(
        self, collection_name: str
    ) -> list[wvc.config.Property]:
        try:
            return get_collection_properties(collection_name)
        except ValueError as e:
            raise WeaviateConfigurationError(str(e)) from e


class WeaviateVectorDBClient(VectorDBClient):
    def __init__(self) -> None:
        self._weaviate = _get_weaviate_client()

    def is_ready(self) -> bool:
        return bool(self._weaviate.is_ready())

    def create_collection(self, name: str, **kwargs: Any) -> None:
        if self._weaviate.collections.exists(name):
            error_message = f"Collection {name} already exists"
            raise WeaviateClientError(error_message)

        try:
            self._weaviate.collections.create(
                name=name,
                **kwargs,
            )
        except Exception as e:
            error_message = f"Failed to create collection {name}: {e}"
            raise WeaviateClientError(error_message) from e

    def get_vector_store(
        self,
        collection_name: str,
        scope_key: str | None = None,
        organization: Organization | None = None,
    ) -> VectorStore:
        config = get_vector_store_config(collection_name)
        return self._get_vector_store(
            index_name=collection_name,
            text_key=config["text_key"],
            attributes=config["attributes"],
            scope_key=scope_key,
            organization=organization,
        )

    def _get_vector_store(
        self,
        *,
        index_name: str,
        text_key: str,
        attributes: list[str],
        scope_key: str | None = None,
        organization: Organization | None = None,
    ) -> VectorStore:
        return WeaviateVectorStore(
            client=self._weaviate,
            index_name=index_name,
            text_key=text_key,
            attributes=attributes,
            embedding=_get_openai_embeddings(scope_key, organization),
            use_multi_tenancy=True,
        )

    def add_documents(
        self,
        vector_store: VectorStore,
        documents: list[Document],
        *,
        tenant: str,
    ) -> None:
        """Insert documents and raise with Weaviate's own batch error details on failure."""
        prior_failed_count = len(self._weaviate.batch.failed_objects)
        vector_store.add_documents(documents, tenant=tenant)
        self._raise_on_batch_insert_failures(
            expected_count=len(documents),
            prior_failed_count=prior_failed_count,
        )

    def _raise_on_batch_insert_failures(
        self,
        *,
        expected_count: int,
        prior_failed_count: int = 0,
    ) -> None:
        current_failed_objects = self._weaviate.batch.failed_objects
        failed_objects = (
            current_failed_objects
            if len(current_failed_objects) < prior_failed_count
            else current_failed_objects[prior_failed_count:]
        )
        if not failed_objects:
            return

        details = [
            f"Failed to add object: {obj.original_uuid}\nReason: {obj.message}"
            for obj in failed_objects
        ]
        error_message = (
            f"Weaviate failed to store {len(failed_objects)} of {expected_count} objects. "
            + " | ".join(details)
        )
        raise WeaviateClientError(error_message)

    def get_retriever(
        self,
        scope_key: str,
        collection_name: str,
        organization: Organization | None = None,
        **kwargs: Any,
    ) -> Any:
        vector_store = self.get_vector_store(
            collection_name,
            scope_key=scope_key,
            organization=organization,
        )
        filters = kwargs.pop("filters", None)
        score_threshold = kwargs.pop("score_threshold", 0.9)

        return vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "tenant": scope_key,
                "k": kwargs.get("k", 3),
                "score_threshold": score_threshold,
                "filters": self._create_weaviate_filter(filters) if filters else None,
            },
        )

    def get_multi_query_retriever(
        self,
        scope_key: str,
        collection_name: str,
        llm: Any,
        organization: Organization | None = None,
        **kwargs: Any,
    ) -> Any:
        vector_store = self.get_vector_store(
            collection_name,
            scope_key=scope_key,
            organization=organization,
        )
        filters = kwargs.pop("filters", None)
        k = kwargs.get("k", 10)

        base_retriever = vector_store.as_retriever(
            search_kwargs={
                "tenant": scope_key,
                "k": k,
                "filters": self._create_weaviate_filter(filters) if filters else None,
            },
        )
        return MultiQueryRetriever.from_llm(
            retriever=base_retriever,
            llm=llm,
        )

    def get_rephrase_query_retriever(
        self,
        scope_key: str,
        collection_name: str,
        llm: Any,
        organization: Organization | None = None,
        **kwargs: Any,
    ) -> Any:
        vector_store = self.get_vector_store(
            collection_name,
            scope_key=scope_key,
            organization=organization,
        )
        filters = kwargs.pop("filters", None)
        k = kwargs.get("k", 10)

        base_retriever = vector_store.as_retriever(
            search_kwargs={
                "tenant": scope_key,
                "k": k,
                "filters": self._create_weaviate_filter(filters) if filters else None,
            },
        )
        return RePhraseQueryRetriever.from_llm(
            retriever=base_retriever,
            llm=llm,
        )

    def get_documents(
        self,
        scope_key: str,
        collection_name: str,
        filters: dict[str, Any],
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        config = get_vector_store_config(collection_name)
        text_key = config["text_key"]
        attributes = config["attributes"]
        weaviate_filter = self._create_weaviate_filter(filters)
        response = (
            self._weaviate.collections.get(collection_name)
            .with_tenant(scope_key)
            .query.fetch_objects(
                filters=weaviate_filter,
                limit=limit,
            )
        )

        docs = []
        for obj in response.objects:
            props = obj.properties
            doc = {text_key: props.get(text_key, "")}
            for attr in attributes:
                if attr != text_key:
                    doc[attr] = props.get(attr)
            docs.append(doc)
        return docs

    def _create_weaviate_filter(self, filters: dict[str, Any]) -> Any:
        if not filters:
            return None

        from functools import reduce

        filter_objects = [
            self._build_filter(key, value) for key, value in filters.items()
        ]
        return reduce(lambda x, y: x & y, filter_objects)

    def _build_filter(self, key: str, value: Any) -> Any:
        if isinstance(value, dict):
            return self._build_operator_filter(key, value)
        return WeaviateFilter.by_property(key).equal(value)

    def _build_operator_filter(self, key: str, operator_dict: dict[str, Any]) -> Any:
        if len(operator_dict) != 1:
            raise ValueError(f"Only one operator allowed per field: {operator_dict}")

        op, val = next(iter(operator_dict.items()))

        if op == "$eq":
            return WeaviateFilter.by_property(key).equal(val)
        elif op == "$containsAny":
            return WeaviateFilter.by_property(key).contains_any(val)
        else:
            raise ValueError(f"Unsupported filter operator: {op}")

    def delete_collection(self, name: str) -> None:
        if not self._weaviate.collections.exists(name):
            error_message = f"Collection {name} does not exist"
            raise WeaviateClientError(error_message)

        try:
            self._weaviate.collections.delete(name)
        except Exception as e:
            error_message = f"Failed to delete collection {name}: {e}"
            raise WeaviateClientError(error_message) from e

    def close(self) -> None:
        if self._weaviate is not None:
            self._weaviate.close()
            self._weaviate = None


def _get_weaviate_client() -> weaviate.WeaviateClient:
    if not settings.WEAVIATE_HOST:
        msg = "WEAVIATE_HOST is not set"
        raise WeaviateConfigurationError(msg)

    if not settings.WEAVIATE_PORT:
        msg = "WEAVIATE_PORT is not set"
        raise WeaviateConfigurationError(msg)

    if not settings.WEAVIATE_API_KEY:
        msg = "WEAVIATE_API_KEY is not set"
        raise WeaviateConfigurationError(msg)

    return weaviate.connect_to_custom(
        http_host=settings.WEAVIATE_HOST,
        http_port=settings.WEAVIATE_PORT,
        http_secure=settings.WEAVIATE_USE_SSL,
        grpc_host=settings.WEAVIATE_HOST,
        grpc_port=50051,
        grpc_secure=settings.WEAVIATE_USE_SSL,
        auth_credentials=Auth.api_key(settings.WEAVIATE_API_KEY),
    )
