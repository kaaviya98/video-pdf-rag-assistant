from __future__ import annotations

from typing import TYPE_CHECKING

from chonkie import SentenceChunker
from marker.renderers.json import BlockTypes
from marker.renderers.json import JSONBlockOutput
from marker.renderers.json import JSONOutput
from pydantic import BaseModel
from pydantic import PositiveInt

from app.domain.pdf.data_classes import BoundingBox
from app.domain.pdf.data_classes import Chunk
from app.domain.pdf.data_classes import ChunkBuffer
from app.domain.pdf.data_classes import ChunkType
from app.domain.pdf.data_classes import Citation
from app.domain.pdf.data_classes import Content
from app.domain.pdf.data_classes import Title
from app.utils import document_parsers
from app.utils.block_parsers import parse_block
from app.utils.block_utils import extract_page_number
from app.utils.block_utils import get_section_level
from app.utils.block_utils import is_footnote
from app.utils.block_utils import is_section_header
from app.utils.html import parse_html
from app.utils.logger import get_logger
from app.utils.openai import resolve_openai_runtime_config

if TYPE_CHECKING:
    from app.models.organization import Organization

logger = get_logger()


class PdfChunkingOptions(BaseModel):
    max_tokens: PositiveInt = 512
    overlap_tokens: PositiveInt = 128
    min_sentences_per_chunk: PositiveInt = 1

    @property
    def sentence_chunker(self) -> SentenceChunker:
        return SentenceChunker(
            chunk_size=self.max_tokens,
            chunk_overlap=self.overlap_tokens,
            min_sentences_per_chunk=self.min_sentences_per_chunk,
        )


def parse_pdf_into_chunks(
    pdf_path: str,
    chunking_options: PdfChunkingOptions,
    document_parser_config: document_parsers.DocumentParserConfig | None = None,
    *,
    scope_key: str | None = None,
    organization: Organization | None = None,
) -> list[Chunk]:
    logger.info(f"[PARSER] Starting PDF parsing: {pdf_path}")

    json_output = _parse_pdf_into_json_output(
        pdf_path,
        document_parser_config,
        scope_key=scope_key,
        organization=organization,
    )
    pages = json_output.children
    chunks: list[Chunk] = []
    pending_chunk_buffer: ChunkBuffer | None = None
    sentence_chunker = chunking_options.sentence_chunker

    for page in pages:
        page_chunks, remaining_buffer = _parse_page_into_chunks(
            sentence_chunker,
            page,
            pending_chunk_buffer,
        )
        pending_chunk_buffer = remaining_buffer
        chunks.extend(page_chunks)

    if pending_chunk_buffer:
        chunks.extend(_flush_buffer_to_chunks(pending_chunk_buffer, sentence_chunker))

    logger.info(f"[PARSER] Completed: {len(pages)} pages -> {len(chunks)} chunks")
    return chunks


def _parse_pdf_into_json_output(
    pdf_path: str,
    document_parser_config: document_parsers.DocumentParserConfig | None = None,
    *,
    scope_key: str | None = None,
    organization: Organization | None = None,
) -> JSONOutput:
    if document_parser_config is None:
        llm_config = resolve_openai_runtime_config(
            organization=organization,
            scope_key=scope_key,
        )
        document_parser_config = document_parsers.DocumentParserConfig(
            output_format="json",
            page_range=None,
            use_llm=True,
            disable_image_extraction=True,
            llm_service="marker.services.openai.OpenAIService",
            extra_kwargs={
                "openai_api_key": llm_config.api_key,
                "openai_model": llm_config.model,
            },
        )

    return document_parsers.parse_pdf(pdf_path, document_parser_config)


def _parse_page_into_chunks(
    sentence_chunker: SentenceChunker,
    page: JSONBlockOutput,
    incoming_buffer: ChunkBuffer | None = None,
) -> tuple[list[Chunk], ChunkBuffer | None]:
    chunks: list[Chunk] = []
    blocks = page.children
    footnote_blocks = []
    on_going_buffer = incoming_buffer or ChunkBuffer()

    for block in blocks:
        if not _should_include_block(block):
            continue

        if is_footnote(block):
            footnote_blocks.append(block)
            continue

        if is_section_header(block):
            if on_going_buffer.has_content:
                chunks.extend(
                    _flush_buffer_to_chunks(on_going_buffer, sentence_chunker),
                )
                on_going_buffer = ChunkBuffer()

            on_going_buffer.title_block = block
            continue

        on_going_buffer.content_blocks.append(block)

    if len(footnote_blocks) > 0:
        buffer = ChunkBuffer(content_blocks=footnote_blocks)
        chunks.extend(_flush_buffer_to_chunks(buffer, sentence_chunker))

    return chunks, on_going_buffer


def _should_include_block(block: JSONBlockOutput) -> bool:
    if block.block_type in [str(BlockTypes.PageFooter), str(BlockTypes.PageHeader)]:
        return False

    return bool(parse_html(block.html)) or (block.children and len(block.children) > 0)


def _flush_buffer_to_chunks(
    chunk_buffer: ChunkBuffer,
    sentence_chunker: SentenceChunker,
) -> list[Chunk]:
    title = (
        _create_title(chunk_buffer.title_block) if chunk_buffer.title_block else None
    )
    contents = _extract_contents(chunk_buffer.content_blocks, sentence_chunker)
    chunk_type = (
        ChunkType.SECTION
        if chunk_buffer.title_block is not None
        else ChunkType.FOOTNOTE
    )

    return [
        Chunk(
            chunk_type=chunk_type,
            title=title,
            content=content,
            pages=sorted(list({citation.page for citation in content.citations})),
        )
        for content in contents
    ]


def _create_title(block: JSONBlockOutput) -> Title:
    citation = _get_citation(block)

    return Title(
        title=parse_html(block.html),
        level=get_section_level(block),
        citation=citation,
    )


def _extract_contents(
    content_blocks: list[JSONBlockOutput],
    sentence_chunker: SentenceChunker,
) -> list[Content]:
    contents = []
    current_content = Content()

    for block in content_blocks:
        parsed_block_text = parse_block(block)

        if _would_exceed_chunk_size(
            current_content,
            parsed_block_text,
            sentence_chunker,
        ):
            if current_content.text:
                contents.append(current_content)
            current_content = _create_content(block, parsed_block_text)
        else:
            current_content = _append_block_to_content(
                current_content,
                block,
                parsed_block_text,
            )

    if current_content.text:
        contents.append(current_content)

    return contents


def _would_exceed_chunk_size(
    current_content: Content,
    parsed_block_text: str,
    sentence_chunker: SentenceChunker,
) -> bool:
    combined_text = _get_combined_text(current_content, parsed_block_text)
    chunks = sentence_chunker.chunk(combined_text)

    return len(chunks) > 1


def _create_content(block: JSONBlockOutput, block_text: str) -> Content:
    return Content(
        text=block_text,
        citations=[_get_citation(block)],
    )


def _append_block_to_content(
    content: Content,
    block: JSONBlockOutput,
    parsed_block_text: str,
) -> Content:
    content.text = _get_combined_text(content, parsed_block_text)
    content.update_citations(_get_citation(block))

    return content


def _get_combined_text(current_content: Content, parsed_block_text: str) -> str:
    if not current_content.text:
        return parsed_block_text
    return f"{current_content.text}\n\n{parsed_block_text}"


def _get_citation(block: JSONBlockOutput) -> Citation:
    return Citation(
        page=extract_page_number(block),
        bbox=BoundingBox.from_list(block.bbox),
    )
