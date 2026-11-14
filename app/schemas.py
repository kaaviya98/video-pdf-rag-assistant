from uuid import UUID
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    asset_id: UUID
    query: str = Field(min_length=1, max_length=8000)
    conversation_id: str = Field(min_length=1, max_length=255)


class ChatResponse(BaseModel):
    asset_id: UUID
    conversation_id: str
    answer: str
