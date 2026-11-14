from typing import Any

from app.domain.pdf.data_classes import Citation, BoundingBox


def extract_citations_from_documents(documents: list[Any]) -> list[Citation]:
    citations = []
    for document in documents:
        for citation_data in document.metadata.get("citations", []):
            bbox = BoundingBox.from_list(citation_data["bbox"])
            citations.append(
                Citation(
                    page=citation_data["page"],
                    bbox=bbox,
                ),
            )
    return citations
