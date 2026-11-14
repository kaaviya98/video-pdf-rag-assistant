# Document & Video Chat Assistant

A standalone FastAPI application for asking grounded questions about PDF
documents and video transcripts. It uses a tool-calling LangChain agent:
the model chooses the relevant retrieval tool, retrieves source material,
and answers with citations.

## Capabilities

- Upload and ingest PDF documents.
- Ingest WebVTT captions for a video and retrieve by topic or timestamp.
- Separate PDF and transcript retrieval tools selected by the agent.
- Multi-turn conversations with persisted messages and bounded history.
- PDF page and video time-range citations.
- Asset-level and organization-level scoping in vector metadata.
- OpenAPI documentation at `/docs`.

Video understanding is transcript-based: provide a `.vtt` captions file
when creating a video asset. This service does not perform speech-to-text
transcription or store/play the original video.

## Architecture

```text
Client
  |
  v
FastAPI routes
  |-- asset upload + ingestion
  |      |-- PDF parser / VTT parser
  |      |-- chunking + embeddings
  |      '-- Weaviate collections
  |
  '-- chat service
         |-- conversation history (SQL database)
         |-- LangChain tool-calling agent
         |     |-- retrieve_from_pdf
         |     '-- retrieve_from_transcript
         '-- answer + source citations
```

The HTTP layer, domain services, persistence, and vector-store adapter are
separated so providers can be replaced without changing agent behavior.

## Run locally

Requirements: Python 3.11+, an OpenAI API key, and a running Weaviate
instance.

```bash
cp .env.example .env
# Set OPENAI_API_KEY and Weaviate connection details in .env
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

For local Weaviate, start the official Weaviate container separately.
The application creates its two collections on startup.

## API

- `POST /api/v1/organizations` — register an organization.
- `POST /api/v1/assets/pdf` — upload and index a PDF.
- `POST /api/v1/assets/video-transcript` — upload a VTT transcript.
- `POST /api/v1/assets/{asset_id}/chats` — ask a question or continue a chat.
- `GET /api/v1/chats/{chat_id}/messages` — read conversation history.
- `GET /health` — service health.

Pass `organization_id` and `user_id` on chat requests. Asset and chat
queries are scoped to the organization and user; do not expose these
identifiers as authorization by themselves in a public deployment. Add
authentication and rate limiting at the API boundary before production use.

## Agent behavior

The agent has two retrieval tools. For PDF assets it can call
`retrieve_from_pdf`, including optional page filters. For video assets it
can call `retrieve_from_transcript`, including a point timestamp or a
time interval. Whole-video questions can use the complete transcript as
context. Answers are grounded in retrieved material and return citations.

## Configuration

See `.env.example`. OpenAI is used for chat and embeddings; Weaviate is
the vector database; SQLAlchemy persists organizations, assets, chats,
and messages. SQLite is convenient for local development. Use PostgreSQL,
managed Weaviate, authentication, object storage, and background workers
for a production deployment.
