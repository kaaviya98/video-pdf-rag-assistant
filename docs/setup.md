# Configuration and local setup

## Requirements

- Python 3.11 or newer.
- An OpenAI API key.
- A running Weaviate instance.
- Network access from the application to Weaviate.

## Environment

Copy the example file:

```bash
cp .env.example .env
```

Set at least `OPENAI_API_KEY`, and configure the Weaviate URL and
credentials for the environment.

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | LLM and embedding API key |
| `OPENAI_MODEL` | Chat model name |
| `EMBEDDING_MODEL` | Embedding model name |
| `DATABASE_URL` | SQLAlchemy database URL |
| `WEAVIATE_URL` | Weaviate endpoint |
| `WEAVIATE_API_KEY` | Optional Weaviate Cloud API key |
| `PDF_COLLECTION` | PDF vector collection |
| `VIDEO_COLLECTION` | Video transcript vector collection |
| `UPLOAD_DIR` | Local upload directory |
| `MAX_UPLOAD_MB` | Maximum upload size |

## Install and run

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload
```

The application creates SQLAlchemy tables on startup and creates the
two vector collections when an OpenAI key is configured.

Open:

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Local Weaviate

Run Weaviate using its official container or a managed Weaviate
instance. Ensure the URL in `WEAVIATE_URL` is reachable from the
application process. For a local instance, the default is
`http://localhost:8080`.

## Production considerations

Before production use:

- Use PostgreSQL and schema migrations.
- Move uploaded files to durable object storage.
- Move parsing and indexing to retryable background workers.
- Add authentication and authorization.
- Add request and per-organization rate limits.
- Validate vector filter semantics with integration tests.
- Add observability for ingestion, retrieval latency, and LLM usage.
- Add cleanup and retention policies for uploaded files and vectors.
