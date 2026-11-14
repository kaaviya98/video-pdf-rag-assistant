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

See [the architecture and code map](docs/architecture.md). The documentation
links directly to each implementation file on GitHub so the code can be
opened while walking through the system.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture and code map](docs/architecture.md)
- [PDF ingestion and retrieval](docs/pdf-pipeline.md)
- [Video transcript ingestion and retrieval](docs/video-pipeline.md)
- [Agent execution and chat lifecycle](docs/agent-and-chat.md)
- [API reference](docs/api.md)
- [Configuration and local setup](docs/setup.md)
- [Five-minute technical walkthrough](docs/interview-walkthrough.md)

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

## Configuration

See `.env.example`. OpenAI is used for chat and embeddings; Weaviate is
the vector database; SQLAlchemy persists organizations, assets, chats,
and messages. SQLite is convenient for local development. Use PostgreSQL,
managed Weaviate, authentication, object storage, and background workers
for a production deployment.
