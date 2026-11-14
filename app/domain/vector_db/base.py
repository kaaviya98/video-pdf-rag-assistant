from abc import ABC
from abc import abstractmethod
from typing import Any

from langchain_core.vectorstores import VectorStore


class VectorDatabase(ABC):
    """Abstract base class for vector database implementations"""

    @abstractmethod
    def get_client(self) -> "VectorDBClient":
        """Get vector database client"""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Check database health"""

    @abstractmethod
    def migrate(self, collection_name: str) -> None:
        """Create one collection by name. Caller must pass the collection to migrate.

        Raises exception on failure.
        """

    @abstractmethod
    def close(self) -> None:
        """Close connections"""


class VectorDBClient(ABC):
    """Abstract base class for vector database clients"""

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if database is ready."""

    @abstractmethod
    def create_collection(self, name: str, **kwargs: Any) -> None:
        """Create collection.

        Raises exception on failure.
        """

    @abstractmethod
    def get_vector_store(
        self,
        collection_name: str,
        scope_key: str | None = None,
        organization: Any | None = None,
    ) -> VectorStore:
        """Get LangChain vector store for the given collection."""

    @abstractmethod
    def get_retriever(
        self,
        scope_key: str,
        collection_name: str,
        organization: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Get LangChain retriever with scope isolation for the given collection."""

    @abstractmethod
    def get_multi_query_retriever(
        self,
        scope_key: str,
        collection_name: str,
        llm: Any,
        organization: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Get LangChain multi-query retriever for the given collection."""

    @abstractmethod
    def delete_collection(self, name: str) -> None:
        """Delete collection."""

    @abstractmethod
    def close(self) -> None:
        """Close connections"""
