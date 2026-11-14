from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from langchain_core.documents import Document

from app.models.transcript import TranscriptLine


@dataclass(slots=True)
class VideoTranscriptChunk:
    chunk_order: int
    start_sec: Decimal
    end_sec: Decimal
    lines: list[TranscriptLine]

    def to_langchain_document(
        self,
        *,
        asset_id: str,
        topic_title: str = "",
    ) -> Document:
        content = " ".join(line.text for line in self.lines).strip()
        if not content:
            raise ValueError("Cannot create document from chunk with empty content")

        return Document(
            page_content=content,
            metadata={
                "asset_id": asset_id,
                "segment_id": f"{asset_id}_{self.chunk_order}",
                "segment_order": int(self.chunk_order),
                "start_sec": float(self.start_sec),
                "end_sec": float(self.end_sec),
                "transcript_line_numbers": [line.line_number for line in self.lines],
                "topic_title": topic_title,
            },
        )
