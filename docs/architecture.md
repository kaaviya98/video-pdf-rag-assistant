# System architecture

## End-to-end architecture

This is the single system view for the standalone PDF and video RAG
assistant. It shows both indexing paths and the shared conversational
RAG path. The agent is created for the selected asset type, so a PDF
chat receives the PDF retrieval tool and a video chat receives the
transcript retrieval tool.

```mermaid
flowchart LR
    U["User / Client"]

    subgraph API["FastAPI application"]
        A["Asset upload endpoints"]
        C["Chat endpoint"]
        V["Validate file type and size"]
        H["Load or create conversation"]
    end

    subgraph INGEST["Ingestion pipelines"]
        direction TB
        PDF["PDF file"]
        PDFP["PyMuPDF page text extraction"]
        PDFCH["Sentence chunking + page metadata"]
        VTT["WebVTT transcript"]
        VTT_P["Parse and order caption cues"]
        VTTCH["Chunk captions + time metadata"]
    end

    subgraph EMBED["Embedding and vector indexing"]
        E["OpenAI embedding model"]
        W["Weaviate vector database"]
        PC[("PDF collection")]
        VC[("Video transcript collection")]
    end

    subgraph CHAT["Agentic RAG chat"]
        direction TB
        HIST["Recent chat history"]
        AG["LangChain tool-calling agent / AgentExecutor"]
        SELECT{"Asset type?"}
        PT["retrieve_from_pdf tool"]
        VT["retrieve_from_transcript tool"]
        PR["PDF semantic retrieval + optional page filter"]
        VR["Transcript semantic retrieval + optional time filter"]
        FULL["Whole-video question: read timestamped VTT transcript"]
        LLM["OpenAI chat model"]
        ANS["Grounded answer + source citations"]
    end

    subgraph DATA["Relational persistence"]
        direction TB
        DB[("SQL database")]
        ORG["Organization and asset records"]
        CHATDB["Chat and message history"]
    end

    U --> A
    A --> V
    V --> PDF
    V --> VTT
    PDF --> PDFP --> PDFCH
    VTT --> VTT_P --> VTTCH
    PDFCH --> E
    VTTCH --> E
    E --> PC
    E --> VC
    PC --- W
    VC --- W

    A --> ORG
    ORG --> DB

    U --> C
    C --> H
    H <--> CHATDB
    CHATDB --> DB
    H --> HIST
    HIST --> AG
    C --> AG
    AG --> SELECT
    SELECT -->|PDF asset| PT
    SELECT -->|Video asset| VT
    PT --> PR
    PR --> PC
    PC --> W
    VT --> VR
    VT --> FULL
    VR --> VC
    VC --> W
    FULL --> LLM
    PR --> LLM
    VR --> LLM
    AG --> LLM
    LLM --> ANS
    ANS --> CHATDB
    ANS --> U

    classDef api fill:#e8f0ff,stroke:#4263a5,color:#172b4d
    classDef process fill:#e9f7ef,stroke:#39845a,color:#173b27
    classDef store fill:#fff4cc,stroke:#b18a22,color:#46370b
    classDef agent fill:#f1eaff,stroke:#7952a8,color:#33204a
    class A,C,V,H api
    class PDFP,PDFCH,VTT_P,VTTCH,E,PR,VR,FULL,LLM,ANS process
    class W,PC,VC,DB,ORG,CHATDB store
    class AG,SELECT,PT,VT,HIST agent
```

## Architecture walkthrough

### 1. Upload and indexing

The client uploads either a PDF or a WebVTT transcript. FastAPI validates
the upload, creates an asset record, and calls the matching ingestion
pipeline.

- **PDF RAG:** PyMuPDF extracts text page by page. Text is chunked and
  each chunk retains its original page number.
- **Video RAG:** WebVTT cues are parsed in chronological order. Chunks
  retain the cue start and end times, so retrieval can refer back to a
  point or interval in the video.
- Both pipelines create embeddings and store vectors with
  `asset_id`, `organization_id`, and source metadata in Weaviate.

### 2. Chat and agent execution

The chat endpoint checks that the asset is ready and belongs to the
requested organization. It loads the latest 12 messages from SQL and
passes them to the LangChain agent.

The agent is configured according to the asset type:

- For a PDF, it registers `retrieve_from_pdf`.
- For a video, it registers `retrieve_from_transcript`.

The model can call the registered tool to retrieve supporting context.
The transcript tool supports semantic search, timestamp/range filters,
and a whole-video mode that reads the stored VTT transcript. The model
then produces an answer grounded in the retrieved content.

### 3. Persistence and isolation

SQLAlchemy stores organizations, assets, chats, and messages.
Weaviate stores the embedded chunks. Retrieval filters by both
`asset_id` and `organization_id`; chat history is scoped to the
conversation, user, and organization.

The current API accepts user and organization identifiers in request
data. They are used for scoping, not authentication. A public deployment
must authenticate callers and derive these identifiers from verified
identity.

## Code map — open these files during the explanation

| Component in the diagram | Implementation | What to explain |
|---|---|---|
| FastAPI application, upload and chat endpoints | [app/main.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/main.py) | Request lifecycle, validation, orchestration, history and citations |
| Configuration | [app/config.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/config.py) | Environment-backed model, database and vector settings |
| SQLAlchemy engine and sessions | [app/database.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/database.py) | Database connection and request-scoped session |
| Organization, asset, chat and message records | [app/models.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/models.py) | Relational data model |
| API request and response schemas | [app/schemas.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/schemas.py) | Input validation and response contracts |
| PDF and video transcript ingestion | [app/ingestion.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/ingestion.py) | Extraction, chunking and source metadata |
| Agent, tool registration and retrieval | [app/agent.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py) | Tool definitions, filters, prompt and AgentExecutor |
| Embeddings and Weaviate | [app/vector_store.py](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/vector_store.py) | Embedding model, collections and vector-store adapter |

## Important scope notes

- Video RAG in this project is **transcript-based**. The input is a
  WebVTT captions file; this service does not extract audio from raw
  video or perform speech-to-text transcription.
- Whole-video questions use the complete stored VTT transcript as
  context. This implementation does not generate or persist video notes.
- Ingestion currently runs synchronously in the upload request.
- The project is a proof of concept: authentication, background workers,
  durable object storage, database migrations and production monitoring
  are not yet implemented.
