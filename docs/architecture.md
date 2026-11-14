# Architecture and code map

## 1. What the service does

The application lets a user upload a PDF or a video's WebVTT transcript,
then ask questions grounded in that source. A tool-calling LLM chooses
the retrieval tool appropriate to the asset. Retrieved chunks carry
metadata used to identify the source in the response.

The service is split into four responsibilities:

- HTTP/API: validation, upload handling, request orchestration.
- Ingestion: extract text, chunk it, attach metadata, and index it.
- Retrieval and agent: select the right retrieval tool and synthesize an
  answer from retrieved evidence.
- Persistence: store organizations, assets, chats, and messages.

## 2. High-level architecture

```text
                       Client
                         |
                         v
                 FastAPI application
                         |
             +-----------+------------+
             |                        |
             v                        v
       Asset endpoints             Chat endpoint
             |                        |
             v                        v
      File validation           Load conversation
      and local storage         and recent messages
             |                        |
        +----+-----+                  v
        |          |           LangChain AgentExecutor
        v          v                  |
       PDF        VTT           +------+------+
        |          |            |             |
        v          v            v             v
     PyMuPDF    WebVTT      PDF retrieval  Video retrieval
        |          |            |             |
     Chunking   Chunking         +------+------+
        |          |                    |
        +-----+----+                    v
              |                    Weaviate search
              v                         |
       OpenAI embeddings                v
              |                   Retrieved evidence
              v                         |
           Weaviate                     v
                                  LLM final answer
                                         |
                                         v
                              citations + SQL history
```

## 3. Code map — open files while explaining

The links below open the exact source files on the repository's main
branch.

| Concern | File | What to explain |
|---|---|---|
| FastAPI entry point and routes | [app/main.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py) | Application startup, endpoints, upload lifecycle, chat orchestration |
| Runtime configuration | [app/config.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/config.py) | Environment-backed settings and defaults |
| SQLAlchemy engine/session | [app/database.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/database.py) | Database lifecycle and request-scoped sessions |
| Domain persistence models | [app/models.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/models.py) | Organization, Asset, Chat, and Message relationships |
| Request/response contracts | [app/schemas.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/schemas.py) | Pydantic validation and API response shapes |
| PDF/VTT ingestion | [app/ingestion.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/ingestion.py) | Text extraction, chunking, and metadata |
| Agent and tools | [app/agent.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py) | Tool definitions, filters, prompt, AgentExecutor |
| Vector database adapter | [app/vector_store.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/vector_store.py) | Weaviate connection, embeddings, collections, vector store |

## 4. Asset ingestion flow

1. The client uploads a PDF or VTT file to FastAPI.
2. The API validates the extension and enforces the configured upload
   size limit.
3. The file is stored under the configured upload directory.
4. An Asset row is created with its organization, type, source path,
   and processing status.
5. The matching ingestion function extracts text and splits it into
   chunks.
6. Each chunk is indexed with asset and organization metadata.
7. The asset status becomes ready only after indexing succeeds.

Start at [the upload routes and orchestration](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py)
and follow calls into [ingestion.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/ingestion.py)
and [vector_store.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/vector_store.py).

## 5. Chat request flow

1. The API verifies that the asset is ready and belongs to the requested
   organization.
2. It finds the conversation for the same asset, organization, and user,
   or creates a new conversation.
3. It loads the most recent 12 messages and converts them into LangChain
   message objects.
4. The agent is built for the asset type: PDF assets receive the PDF
   retrieval tool; video assets receive the transcript retrieval tool.
5. The model decides when and how to call the available tool.
6. The tool searches only the current asset and organization.
7. The LLM writes the final answer from retrieved material.
8. The API stores both messages and returns the answer with citations.

Code: [chat endpoint](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py)
→ [agent construction](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py).

## 6. Isolation boundaries

The vector metadata contains both `asset_id` and
`organization_id`. Retrieval applies both filters. SQL lookups for
assets and chats also include organization ownership; chat lookups
include the user identifier.

These identifiers are scoping inputs, not authentication. A public
deployment must authenticate the caller and derive the user and
organization from verified identity rather than trusting request fields.

## 7. Important implementation boundaries

- FastAPI owns transport concerns; the ingestion and agent code are
  separate modules.
- SQLAlchemy owns relational persistence.
- Weaviate owns semantic vector search.
- OpenAI supplies chat completions and embeddings.
- LangChain coordinates tool selection and agent execution.
- Video processing here means transcript ingestion and transcript
  retrieval. It does not extract audio from a video or run ASR.
- Whole-video questions use the stored VTT transcript as context;
  they do not currently use generated video notes.

## 8. Current limitations

This is a focused proof of concept, not a production-hardened service.
It currently uses synchronous request handlers and performs ingestion
inside the upload request. It has no user authentication, upload object
storage, retryable background job queue, or automated migrations.
The chat API's citation extraction and vector-store filter behavior
should be covered by integration tests against a live Weaviate instance.
