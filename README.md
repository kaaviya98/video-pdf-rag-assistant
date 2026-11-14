# LearnLens — Standalone PDF & Video RAG Chat

Standalone extraction of the LearnLens PDF/video question-answering architecture. It retains the original parsing, chunking, embedding, Weaviate retrieval, LangChain AgentExecutor, Django ORM models, and Celery ingestion. The HTTP surface is intentionally reduced to one FastAPI chat router.

## Architecture

- FastAPI: one `/api/v1/chat` endpoint.
- PostgreSQL + Django ORM: Organization, Asset, TranscriptLine.
- PDF: Marker JSON parsing, block-aware extraction, Chonkie SentenceChunker.
- Video: WebVTT parsing, transcript persistence, time-window grouping, embedding-similarity boundary detection, character-based rechunking.
- Embeddings: LangChain OpenAI embeddings.
- Vector store: Weaviate with separate PDF and video collections.
- Agent: LangChain tool-calling `AgentExecutor`, with PDF and transcript retrieval tools.
- Chat memory: Redis-backed LangChain message history.
- Ingestion: Celery PDF/video processing tasks.

LMS authentication, quizzes, LMS-specific fields, external status webhooks, and the original admin/router surface are excluded. Organization scoping and asset models remain.

## Run

Start PostgreSQL, Weaviate, Redis, and RabbitMQ (RabbitMQ is required for Celery workers). Copy `.env.example` to `.env`, configure credentials, install with `uv sync`, initialize tables using `uv run python manage.py migrate --run-syncdb`, then start `uv run uvicorn app.main:app --reload`. API docs are at `/docs`.

Assets are created in PostgreSQL and then queued with `async_process_pdf_asset.delay(asset_id)` or `async_process_video_asset.delay(asset_id)`. Video assets require a VTT `captions_url`; speech-to-text is not included.
