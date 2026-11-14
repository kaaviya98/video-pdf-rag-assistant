# PDF ingestion and retrieval

## 1. Goal

Convert a PDF into searchable chunks while retaining page metadata.
At question time, retrieve the chunks relevant to the user's query and
let the agent construct a grounded answer with page citations.

## 2. Ingestion workflow

```text
PDF upload
   |
   v
FastAPI validates extension and size
   |
   v
Temporary/local file storage
   |
   v
PyMuPDF extracts text page by page
   |
   v
SentenceChunker splits text with overlap
   |
   v
LangChain Document objects
   |
   v
OpenAI embedding model
   |
   v
Weaviate PDF collection
```

Implementation: [ingest_pdf()](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/ingestion.py).

### Step-by-step

1. The API accepts a PDF and creates an asset record.
2. PyMuPDF opens the document and extracts text from each page.
3. Empty pages are skipped.
4. SentenceChunker splits each page into overlapping text chunks.
5. Each chunk becomes a LangChain Document.
6. Metadata includes asset ID, organization ID, page number, and
   source type.
7. The vector store embeds and indexes the documents.

The current implementation uses a chunk size of 900 and overlap of 150
in the configured SentenceChunker call. This differs from the older
LearnLens implementation's Marker-based structured parser and its
1536/384 chunking defaults; this standalone version currently uses
PyMuPDF text extraction.

## 3. Retrieval workflow

When the agent invokes `retrieve_from_pdf`:

1. It receives a search query and optional page numbers.
2. It creates a filter for the current asset and organization.
3. If the user specified pages, it adds a page filter.
4. It asks the PDF collection for the top matching chunks.
5. It returns the text and source metadata to the agent.

Implementation: [retrieve_from_pdf()](https://github.com/kaaviya98/video-pdf-rag-assistant/blob/main/app/agent.py).

## 4. Citation metadata

Each indexed PDF chunk includes:

- `source_type`: identifies the source as a PDF.
- `page`: original one-based PDF page number.
- `asset_id`: the source asset.
- `organization_id`: the tenant scope.

The agent receives metadata alongside the chunk text. The API extracts
page references from retrieval observations and returns structured
citation objects.

## 5. Trade-offs and limitations

PyMuPDF text extraction is intentionally simple and fast. It does not
preserve the richer layout structure, bounding boxes, tables, or image
understanding provided by a layout-aware parser. Scanned PDFs require
OCR, which is not currently implemented. Chunking is performed page by
page, so a sentence spanning page boundaries is not merged.
