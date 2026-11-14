from typing import Any

from app.domain.prompts import CHAT_AGENT_SYSTEM_MESSAGE
from app.domain.prompts import VIDEO_AI_CHAT_PROMPT
from app.models.asset import Asset
from app.models.asset import AssetFileType


def chat_agent_tools_and_system_message(
    asset: Asset,
    retrieve_from_pdf_tool: Any,
    retrieve_from_transcript_tool: Any,
) -> tuple[list[Any], str]:
    if asset.file_type == AssetFileType.PDF:
        return [retrieve_from_pdf_tool], CHAT_AGENT_SYSTEM_MESSAGE
    if asset.file_type in (AssetFileType.VIDEO, AssetFileType.AUDIO):
        return [retrieve_from_transcript_tool], VIDEO_AI_CHAT_PROMPT
    raise ValueError(f"Unsupported asset type for chat: {asset.file_type}")
