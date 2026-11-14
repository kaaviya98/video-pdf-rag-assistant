from collections.abc import Iterator
from enum import Enum
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import Self

from langchain_core.documents import Document
from marker.renderers.json import JSONBlockOutput
from pydantic import BaseModel
from pydantic import Field


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    class Config:
        json_encoders: ClassVar = {
            Self: lambda b: list(b),
        }

    def __iter__(self) -> Iterator[float]:  # type: ignore [override]
        return iter((self.x0, self.y0, self.x1, self.y1))

    @classmethod
    def from_list(cls, bbox: list[float]) -> "BoundingBox":
        return cls(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BoundingBox):
            return False
        return (
            self.x0 == other.x0
            and self.y0 == other.y0
            and self.x1 == other.x1
            and self.y1 == other.y1
        )

    def __add__(self, other: "BoundingBox") -> "BoundingBox":
        return BoundingBox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def horizontal_overlap(self, other: "BoundingBox") -> float:
        overlap_start = max(self.x0, other.x0)
        overlap_end = min(self.x1, other.x1)
        return max(0, overlap_end - overlap_start)

    def vertical_overlap(self, other: "BoundingBox") -> float:
        overlap_start = max(self.y0, other.y0)
        overlap_end = min(self.y1, other.y1)
        return max(0, overlap_end - overlap_start)

    def horizontal_gap(self, other: "BoundingBox") -> float:
        if self.horizontal_overlap(other) > 0:
            return 0
        return min(abs(self.x0 - other.x1), abs(self.x1 - other.x0))

    def vertical_gap(self, other: "BoundingBox") -> float:
        if self.vertical_overlap(other) > 0:
            return 0
        return min(abs(self.y0 - other.y1), abs(self.y1 - other.y0))

    def has_similar_start_position(
        self,
        other: "BoundingBox",
        max_position_diff: float = 60.0,
    ) -> bool:
        return abs(self.x0 - other.x0) <= max_position_diff

    def has_major_overlap(
        self,
        other: "BoundingBox",
        min_overlap_ratio: float = 0.75,
    ) -> bool:
        overlap = self.horizontal_overlap(other)
        current_width = self.width
        other_width = other.width

        if current_width <= 0 or other_width <= 0:
            return False

        # Both boxes must have at least 75% of their width overlapping
        overlap_ratio_current = overlap / current_width
        overlap_ratio_other = overlap / other_width
        return (
            overlap_ratio_current >= min_overlap_ratio
            and overlap_ratio_other >= min_overlap_ratio
        )

    def is_in_same_column(self, other: "BoundingBox") -> bool:
        return self.has_similar_start_position(other) and self.has_major_overlap(other)

    def can_combine(
        self,
        other: "BoundingBox",
        max_vertical_gap: float = 90.0,
    ) -> bool:
        if not self.is_in_same_column(other):
            return False
        gap = self.vertical_gap(other)
        return gap <= max_vertical_gap


class ChunkType(Enum):
    SECTION = "section"
    SUBSECTION = "subsection"
    FOOTNOTE = "footnote"


class Citation(BaseModel):
    source_type: Literal["pdf", "video"] = "pdf"
    page: int | None = None
    bbox: BoundingBox | None = None
    start_sec: float | None = None
    end_sec: float | None = None

    class Config:
        json_encoders: ClassVar = {
            BoundingBox: lambda b: list(b),
        }


class Title(BaseModel):
    title: str = Field(default_factory=str)
    citation: Citation | None = None
    level: int = Field(default=0)


class Content(BaseModel):
    text: str = Field(default_factory=str)
    citations: list[Citation] = Field(default_factory=list)

    def update_citations(self, citation: Citation) -> None:
        updated_existing_citation = False

        for existing_citation in self.citations:
            if (
                existing_citation.page == citation.page
                and existing_citation.bbox.can_combine(citation.bbox)
            ):
                existing_citation.bbox = existing_citation.bbox + citation.bbox
                updated_existing_citation = True
                break

        if not updated_existing_citation:
            self.citations.append(citation)


class Chunk(BaseModel):
    chunk_type: ChunkType = Field(default=ChunkType.SECTION)
    title: Title | None = None
    content: Content = Field(default_factory=Content)
    pages: list[int] = Field(default_factory=list)

    @property
    def text_representation(self) -> str:
        formatted_text = ""

        if self.title and self.title.title:
            formatted_text += "Title: " + self.title.title + "\n\n"
        formatted_text += self.content.text

        return formatted_text

    @property
    def citations(self) -> list[Citation]:
        citations = []
        if self.title and self.title.citation:
            citations.append(self.title.citation)
        citations.extend(self.content.citations)

        return citations

    def to_langchain_document(
        self,
        additional_metadata: dict[str, Any] | None = None,
    ) -> Document:
        if not self.content.text:
            error_message = "Cannot create document from chunk with empty content"
            raise ValueError(error_message)

        metadata = {
            "title": self.title.title if self.title and self.title.title else None,
            "chunk_type": self.chunk_type.value,
            "pages": self.pages,
            "citations": [
                {
                    "page": citation.page,
                    "bbox": list(citation.bbox),
                }
                for citation in self.citations
            ],
        }

        if additional_metadata:
            metadata.update(additional_metadata)

        return Document(
            page_content=self.text_representation,
            metadata=metadata,
        )


class ChunkBuffer(BaseModel):
    title_block: JSONBlockOutput | None = None
    content_blocks: list[JSONBlockOutput] = Field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return self.title_block is not None or len(self.content_blocks) > 0
