from pathlib import Path

import fitz
import webvtt
from chonkie import SentenceChunker
from langchain_core.documents import Document

from app.config import get_settings
from app.vector_store import add_documents


def ingest_pdf(path: Path, asset_id: str, organization_id: str) -> int:
    pdf = fitz.open(path)
    chunker = SentenceChunker(chunk_size=900, chunk_overlap=150)
    documents: list[Document] = []
    try:
        for page_index, page in enumerate(pdf):
            text = page.get_text("text").strip()
            if not text:
                continue
            for chunk in chunker.chunk(text):
                content = chunk.text.strip()
                if content:
                    documents.append(Document(
                        page_content=content,
                        metadata={
                            "asset_id": asset_id,
                            "organization_id": organization_id,
                            "page": page_index + 1,
                            "source_type": "pdf",
                        },
                    ))
    finally:
        pdf.close()
    add_documents(get_settings().pdf_collection, documents)
    return len(documents)


def ingest_vtt(path: Path, asset_id: str, organization_id: str) -> int:
    captions = webvtt.read(str(path))
    chunker = SentenceChunker(chunk_size=500, chunk_overlap=80)
    documents: list[Document] = []
    cues = sorted(captions, key=lambda cue: cue.start_in_seconds)
    for cue in cues:
        text = " ".join((cue.text or "").split())
        if not text:
            continue
        for chunk in chunker.chunk(text):
            content = chunk.text.strip()
            if content:
                documents.append(Document(
                    page_content=content,
                    metadata={
                        "asset_id": asset_id,
                        "organization_id": organization_id,
                        "start_sec": cue.start_in_seconds,
                        "end_sec": cue.end_in_seconds,
                        "source_type": "video",
                    },
                ))
    add_documents(get_settings().video_collection, documents)
    return len(documents)
