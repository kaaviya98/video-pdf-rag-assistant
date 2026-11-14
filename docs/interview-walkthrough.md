# Technical walkthrough

1. Start with the simple FastAPI surface: one chat router and one endpoint.
2. Explain Django ORM models: Organization, Asset, and TranscriptLine in PostgreSQL.
3. Trace PDF ingestion: Marker JSON blocks, block-aware parsing, Chonkie sentence chunking, citation metadata, OpenAI embeddings, and Weaviate.
4. Trace video ingestion: WebVTT normalization, TranscriptLine persistence, time-window grouping, embedding similarity boundaries, and Weaviate.
5. Explain the LangChain AgentExecutor: PDF and transcript tools are registered according to asset type; the model selects the retrieval tool and arguments.
6. Explain Redis-backed conversation history and Celery background ingestion.

This standalone version deliberately omits LMS authentication, quizzes, external webhooks, and the LMS admin API surface.
