# Architecture

Client -> FastAPI `/api/v1/chat` -> chat service -> Django ORM Asset lookup -> LangChain AgentExecutor -> asset-specific retrieval tool -> Weaviate and/or PostgreSQL transcript lines. Redis stores conversation history.

Celery ingestion: PDF -> Marker JSON -> block parsing -> Chonkie sentence chunks -> OpenAI embeddings -> Weaviate. Video VTT -> TranscriptLine rows -> 2-minute windows -> embedding-similarity boundaries -> 2–5 minute chunk limits -> character-based rechunking -> embeddings -> Weaviate.

FastAPI is the only HTTP layer. Django ORM owns relational persistence. Domain parsing and retrieval code is kept separate from API code. LMS authentication, quizzes, admin routers, and webhooks are intentionally removed.
