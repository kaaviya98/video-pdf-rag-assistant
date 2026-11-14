import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from fastapi import FastAPI
from app.api.router import router
from app.domain.vector_db import get_vector_database
from django.conf import settings

app = FastAPI(title="LearnLens Asset Chat API", description="Chat with PDF and video assets using the original RAG pipeline.", version="1.0.0")
app.include_router(router)


@app.on_event("startup")
def initialize_vector_collections() -> None:
    database = get_vector_database()
    client = database.get_client()
    try:
        for collection_name in (
            settings.VECTOR_DB_PDF_COLLECTION_NAME,
            settings.VECTOR_DB_VIDEO_COLLECTION_NAME,
        ):
            if not client.collection_exists(collection_name):
                database.migrate(collection_name)
    finally:
        database.close()


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
