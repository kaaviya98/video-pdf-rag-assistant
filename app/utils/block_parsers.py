from abc import ABC
from abc import abstractmethod
from typing import cast

import htmltabletomd
from marker.renderers.json import BlockTypes
from marker.renderers.json import JSONBlockOutput

from app.utils.html import parse_html


class BlockParser(ABC):
    """Abstract base class for block parsers."""

    @abstractmethod
    def can_parse(self, block: JSONBlockOutput) -> bool:
        """Check if this parser can handle the given block."""

    @abstractmethod
    def parse(self, block: JSONBlockOutput) -> str:
        """Parse the block and return formatted text."""


class SectionHeaderParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return bool(block.block_type == str(BlockTypes.SectionHeader))

    def parse(self, block: JSONBlockOutput) -> str:
        return "Title: " + parse_html(block.html)


class TableGroupParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return bool(block.block_type == str(BlockTypes.TableGroup))

    def parse(self, block: JSONBlockOutput) -> str:
        text = ""
        for child in block.children:
            if child.block_type == str(BlockTypes.Table):
                text += TableParser().parse(child)
            else:
                text += parse_html(child.html) + "\n"
        return text


class TableParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return bool(block.block_type == str(BlockTypes.Table))

    def parse(self, block: JSONBlockOutput) -> str:
        try:
            return cast(str, htmltabletomd.convert_table(block.html))
        except ValueError:
            # Fall back to plain text extraction if table structure is invalid
            return parse_html(block.html)


class FigureGroupParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return bool(block.block_type == str(BlockTypes.FigureGroup))

    def parse(self, block: JSONBlockOutput) -> str:
        text = ""
        for child in block.children:
            if child.block_type == str(BlockTypes.Figure):
                text += FigureParser().parse(child) + "\n\n"
            else:
                text += parse_html(child.html) + "\n\n"
        return text


class FigureParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return bool(block.block_type == str(BlockTypes.Figure))

    def parse(self, block: JSONBlockOutput) -> str:
        text = parse_html(block.html)
        parts = text.split("description: ", 1)
        description = parts[1] if len(parts) == 2 else text  # noqa: PLR2004
        return "Picture Description: " + description


class ListGroupParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return bool(block.block_type == str(BlockTypes.ListGroup))

    def parse(self, block: JSONBlockOutput) -> str:
        text = ""
        for child in block.children:
            text += "- " + parse_html(child.html) + "\n"
        return text


class DefaultParser(BlockParser):
    def can_parse(self, block: JSONBlockOutput) -> bool:
        return True

    def parse(self, block: JSONBlockOutput) -> str:
        return parse_html(block.html)


class BlockParserFactory:
    def __init__(self) -> None:
        self._parsers = [
            SectionHeaderParser(),
            TableGroupParser(),
            TableParser(),
            FigureGroupParser(),
            ListGroupParser(),
        ]

    def get_parser(self, block: JSONBlockOutput) -> BlockParser:
        for parser in self._parsers:
            if parser.can_parse(block):
                return parser
        return DefaultParser()


_parser_factory = BlockParserFactory()


def parse_block(block: JSONBlockOutput) -> str:
    parser = _parser_factory.get_parser(block)

    return parser.parse(block)
