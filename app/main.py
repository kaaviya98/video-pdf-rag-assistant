import ast
import json
import logging
import re
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.ingestion import ingest_pdf, ingest_vtt
from app.models import Asset, Chat, Message, Organization, utc_now
from app.schemas import (
    AssetResponse,
    ChatRequest,
    ChatResponse,
    Citation,
    MessageResponse,
    OrganizationCreate,
    OrganizationResponse,
)
from app.vector_store import ensure_collections

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Document & Video Chat Assistant", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.openai_api_key:
        ensure_collections()


@app.on_event("shutdown")
def shutdown() -> None:
    from app.vector_store import get_weaviate_client

    if get_weaviate_client.cache_info().currsize:
        get_weaviate_client().close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/organizations", response_model=OrganizationResponse)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)):
    organization = Organization(name=payload.name.strip())
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def _save_upload(upload: UploadFile, suffix: str) -> Path:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    destination_dir = Path(settings.upload_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{uuid4()}{suffix}"
    total = 0
    try:
        with destination.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds configured size limit")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _create_asset(
    db: Session, organization_id: str, title: str, asset_type: str, path: Path
) -> Asset:
    if db.get(Organization, organization_id) is None:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Organization not found")
    asset = Asset(
        organization_id=organization_id,
        title=title.strip() or path.stem,
        asset_type=asset_type,
        source_path=str(path),
        status="processing",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@app.post("/api/v1/assets/pdf", response_model=AssetResponse)
def upload_pdf(
    organization_id: str = Form(...),
    title: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Upload a PDF file")
    path = _save_upload(file, ".pdf")
    asset = _create_asset(db, organization_id, title, "pdf", path)
    try:
        ingest_pdf(path, asset.id, organization_id)
        asset.status = "ready"
        db.commit()
        return asset
    except Exception as exc:
        logger.exception("PDF ingestion failed")
        asset.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="PDF ingestion failed") from exc


@app.post("/api/v1/assets/video-transcript", response_model=AssetResponse)
def upload_video_transcript(
    organization_id: str = Form(...),
    title: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or Path(file.filename).suffix.lower() != ".vtt":
        raise HTTPException(status_code=415, detail="Upload a WebVTT (.vtt) transcript")
    path = _save_upload(file, ".vtt")
    asset = _create_asset(db, organization_id, title, "video", path)
    try:
        ingest_vtt(path, asset.id, organization_id)
        asset.status = "ready"
        db.commit()
        return asset
    except Exception as exc:
        logger.exception("Video transcript ingestion failed")
        asset.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Transcript ingestion failed") from exc


def _extract_citations(agent_result: dict) -> list[dict]:
    citations: list[dict] = []
    seen: set[tuple] = set()
    for _action, observation in agent_result.get("intermediate_steps", []):
        for match in re.finditer(r"SOURCE: (\{.*?\})", str(observation)):
            try:
                metadata = ast.literal_eval(match.group(1))
            except (ValueError, SyntaxError):
                continue
            if metadata.get("source_type") == "pdf" and metadata.get("page"):
                item = ("pdf", metadata["page"])
                citation = {"source_type": "pdf", "page": int(metadata["page"])}
            elif metadata.get("source_type") == "video":
                item = ("video", metadata.get("start_sec"), metadata.get("end_sec"))
                citation = {
                    "source_type": "video",
                    "start_sec": float(metadata["start_sec"]),
                    "end_sec": float(metadata["end_sec"]),
                }
            else:
                continue
            if item not in seen:
                seen.add(item)
                citations.append(citation)
    return citations


@app.post("/api/v1/assets/{asset_id}/chats", response_model=ChatResponse)
def chat_with_asset(asset_id: str, payload: ChatRequest, db: Session = Depends(get_db)):
    asset = db.scalar(select(Asset).where(
        Asset.id == asset_id,
        Asset.organization_id == payload.organization_id,
        Asset.status == "ready",
    ))
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found or not ready")

    if payload.chat_id:
        chat = db.scalar(select(Chat).where(
            Chat.id == payload.chat_id,
            Chat.asset_id == asset_id,
            Chat.organization_id == payload.organization_id,
            Chat.user_id == payload.user_id,
        ))
        if chat is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        chat = Chat(
            organization_id=payload.organization_id,
            user_id=payload.user_id,
            asset_id=asset_id,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)

    history_messages = db.scalars(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(Message.created_at.desc())
        .limit(12)
    ).all()
    from langchain_core.messages import AIMessage, HumanMessage

    chat_history = [
        HumanMessage(content=message.content) if message.role == "user"
        else AIMessage(content=message.content)
        for message in reversed(history_messages)
    ]
    try:
        from app.agent import build_asset_agent

        result = build_asset_agent(asset).invoke({
            "input": payload.query,
            "chat_history": chat_history,
        })
    except Exception as exc:
        logger.exception("Agent execution failed")
        raise HTTPException(status_code=502, detail="The assistant could not generate a response") from exc

    answer = result["output"]
    citations = _extract_citations(result)
    db.add(Message(chat_id=chat.id, role="user", content=payload.query))
    db.add(Message(
        chat_id=chat.id,
        role="assistant",
        content=answer,
        citations_json=json.dumps(citations),
    ))
    chat.updated_at = utc_now()
    db.commit()
    return ChatResponse(
        chat_id=chat.id,
        answer=answer,
        citations=[Citation(**citation) for citation in citations],
    )


@app.get("/api/v1/chats/{chat_id}/messages", response_model=list[MessageResponse])
def get_chat_messages(
    chat_id: str,
    organization_id: str,
    user_id: str,
    db: Session = Depends(get_db),
):
    chat = db.scalar(select(Chat).where(
        Chat.id == chat_id,
        Chat.organization_id == organization_id,
        Chat.user_id == user_id,
    ))
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.scalars(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    ).all()
    return [
        MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            citations=[Citation(**citation) for citation in json.loads(message.citations_json or "[]")],
        )
        for message in messages
    ]
