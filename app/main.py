import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from fastapi import FastAPI
from app.api.router import router

app = FastAPI(title="LearnLens Asset Chat API", description="Chat with PDF and video assets using the original RAG pipeline.", version="1.0.0")
app.include_router(router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
