from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationResponse(BaseModel):
    id: str
    name: str


class ChatRequest(BaseModel):
    organization_id: str
    user_id: str = Field(min_length=1, max_length=255)
    query: str = Field(min_length=1, max_length=4000)
    chat_id: str | None = None


class Citation(BaseModel):
    source_type: str
    page: int | None = None
    start_sec: float | None = None
    end_sec: float | None = None


class ChatResponse(BaseModel):
    chat_id: str
    answer: str
    citations: list[Citation]


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    citations: list[Citation]


class AssetResponse(BaseModel):
    id: str
    organization_id: str
    title: str
    asset_type: str
    status: str
