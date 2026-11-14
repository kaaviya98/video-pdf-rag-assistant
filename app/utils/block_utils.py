import re
from typing import cast

from marker.renderers.json import BlockTypes
from marker.renderers.json import JSONBlockOutput


def extract_page_number(block: JSONBlockOutput) -> int:
    match = re.match(r"/page/(\d+)/", block.id)
    if match is None:
        error_message = f"Block ID {block.id} does not contain a page number"
        raise ValueError(error_message)

    return int(match.group(1))


def is_section_header(block: JSONBlockOutput) -> bool:
    return cast(bool, block.block_type == str(BlockTypes.SectionHeader))


def is_footnote(block: JSONBlockOutput) -> bool:
    return cast(bool, block.block_type == str(BlockTypes.Footnote))


def get_section_level(block: JSONBlockOutput) -> int:
    level = {v: k for k, v in block.section_hierarchy.items()}[block.id]

    return int(level)
