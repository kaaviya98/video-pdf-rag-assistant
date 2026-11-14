from .base import VectorDatabase
from .weaviate import WeaviateVectorDatabase


def get_vector_database() -> VectorDatabase:
    """Get vector database instance (currently returns Weaviate)"""
    return WeaviateVectorDatabase()


__all__ = ["get_vector_database", "VectorDatabase"]
