# Five-minute technical walkthrough

Use this page as a navigation guide while screen sharing. Each code
link opens the corresponding file on GitHub.

## 0:00–0:35 — Product and architecture

Say: "This is a document and video transcript chat backend. A user
uploads a PDF or a timestamped transcript, the service indexes its
content, and a tool-calling agent answers questions with source
references."

Open [README architecture](../README.md) and
[architecture diagram/code map](architecture.md).

## 0:35–1:20 — API and asset lifecycle

Open [app/main.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py).

Explain:
- FastAPI routes and Pydantic request validation.
- Upload size and file-type validation.
- Asset lifecycle: processing → ready/failed.
- Organization-scoped asset lookup before chat.

## 1:20–2:05 — Ingestion and embeddings

Open [app/ingestion.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/ingestion.py)
and [app/vector_store.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/vector_store.py).

Explain:
- PDF text is extracted page by page.
- VTT cues preserve start/end timestamps.
- Text is chunked with overlap.
- Metadata is attached before indexing.
- Embeddings are generated and stored in Weaviate.

## 2:05–3:20 — Agent and tools

Open [app/agent.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py).

Explain:
- The agent is built for the asset type.
- PDF assets expose the PDF retrieval tool.
- Video assets expose the transcript retrieval tool.
- The model chooses tool arguments based on intent.
- Filters constrain retrieval to the current asset and organization.
- AgentExecutor orchestrates tool calls and final answer generation.

## 3:20–4:15 — Conversation history and citations

Return to [app/main.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py).

Explain:
- The latest 12 messages are loaded from SQL.
- History is converted to LangChain messages.
- The agent receives history and the new question.
- User and assistant messages are persisted.
- Citation metadata is extracted from retrieval observations.

## 4:15–5:00 — Trade-offs and next steps

Be transparent about the current POC boundaries:
- Transcript-based video chat, not raw video understanding.
- Synchronous ingestion, not background jobs yet.
- SQL-backed recent history, not Redis memory or summarization.
- Authentication and production hardening are future work.

Close with: "The key design decision is separating ingestion, retrieval,
agent orchestration, and persistence. That keeps the retrieval tools
and vector store replaceable without putting those concerns in the API
handlers."
