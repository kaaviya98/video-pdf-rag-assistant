from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    database_url: str = "sqlite:///./assistant.db"
    weaviate_url: str = "http://localhost:8080"
    weaviate_api_key: str = ""
    pdf_collection: str = "PdfChunks"
    video_collection: str = "VideoTranscriptChunks"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
