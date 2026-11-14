# LearnLens — Standalone PDF & Video RAG Chat

A standalone PDF and video question-answering service. It keeps the original Marker/Chonkie PDF processing, WebVTT transcript processing, OpenAI embeddings, Weaviate retrieval, LangChain tool-calling AgentExecutor, Django ORM models, PostgreSQL persistence, and Celery ingestion.

The HTTP surface is intentionally small: one FastAPI chat router.

## System architecture

See the [complete system architecture](docs/architecture.md) for:
- End-to-end system component diagram.
- Basic RAG lifecycle.
- PDF ingestion and chunking flow.
- Video transcript ingestion and chunking flow.
- Chat/AgentExecutor/retrieval sequence.
- Weaviate, relational data model, and background processing.
- Direct links to implementation files for each stage.

## Stack

- FastAPI — chat API
- Django ORM + PostgreSQL — organizations, assets, transcript lines
- Marker + Chonkie — PDF parsing and sentence chunking
- WebVTT — transcript parsing
- LangChain + OpenAI — embeddings and tool-calling agent
- Weaviate — PDF/video vector collections
- Redis — conversation history
- Celery + RabbitMQ — asynchronous ingestion

## Run locally

Start PostgreSQL, Weaviate, Redis, and RabbitMQ (RabbitMQ is required for Celery workers). Copy `.env.example` to `.env`, configure credentials, and install dependencies:

```bash
uv sync
uv run python manage.py migrate --run-syncdb
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

Assets must exist in PostgreSQL before ingestion is queued:
- PDF: `async_process_pdf_asset.delay(asset_id)`
- Video: `async_process_video_asset.delay(asset_id)`

Video assets require a VTT `captions_url`. Raw-video speech recognition is not included.
