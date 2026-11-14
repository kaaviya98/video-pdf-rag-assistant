from fastapi import APIRouter, HTTPException, status

from app.domain.chat_service import ChatServiceError, chat_with_asset
from app.models.asset import Asset, AssetFileType
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        asset = Asset.objects.select_related("organization").get(id=payload.asset_id)
    except (Asset.DoesNotExist, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        ) from exc

    supported_types = (AssetFileType.PDF, AssetFileType.VIDEO)
    if asset.file_type not in supported_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat supports PDF and video assets only",
        )

    if not asset.is_processed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset ingestion is not complete")

    try:
        answer, citations = chat_with_asset(
            asset=asset,
            query=payload.query,
            conversation_id=payload.conversation_id,
        )
    except ChatServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to generate an answer from this asset",
        ) from exc

    return ChatResponse(
        asset_id=asset.id,
        conversation_id=payload.conversation_id,
        answer=answer,
        citations=citations,
    )
