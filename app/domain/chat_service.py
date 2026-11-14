import re
from functools import lru_cache

import redis
from django.conf import settings
from langchain_community.callbacks.manager import get_openai_callback
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_redis import RedisChatMessageHistory

from app.domain.agents import create_agent_executor
from app.domain.citations import extract_citations_from_documents
from app.domain.vector_db import get_vector_database
from app.models.asset import Asset, AssetFileType
from app.utils.openai import init_asset_chat_model, resolve_llm_config_for_asset
from app.utils.transcript_timestamps import replace_line_refs_with_timestamps

CHAT_HISTORY_TTL_SECONDS = 4 * 60 * 60


class ChatServiceError(Exception):
    """Raised when asset chat cannot be completed."""


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _get_session_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(
        session_id=session_id,
        redis_client=_redis_client(),
        ttl=CHAT_HISTORY_TTL_SECONDS,
        key_prefix="learnlens:chat:",
    )


def _clean_agent_output(raw_output: str) -> tuple[str, bool]:
    include_citations = bool(
        re.search(r"<include_citations:\s*yes>", raw_output, re.IGNORECASE)
    )
    answer = re.sub(
        r"<include_citations:\s*(yes|no)>", "", raw_output, flags=re.IGNORECASE
    )
    answer = re.sub(
        r"<query_classification:\s*[^>]+>", "", answer, flags=re.IGNORECASE
    )
    return answer.strip(), include_citations


def _get_pdf_citations(answer: str, asset: Asset, client, llm) -> list[dict]:
    retriever = client.get_retriever(
        scope_key=asset.scope_key,
        collection_name=settings.VECTOR_DB_PDF_COLLECTION_NAME,
        organization=asset.organization if asset.organization_id else None,
        llm=llm,
        k=1,
        score_threshold=0.7,
        filters={"asset_id": str(asset.id)},
    )
    documents = retriever.get_relevant_documents(answer)
    return [citation.model_dump() for citation in extract_citations_from_documents(documents)]


def chat_with_asset(*, asset: Asset, query: str, conversation_id: str) -> tuple[str, list[dict]]:
    vector_db = get_vector_database()
    client = None
    try:
        client = vector_db.get_client()
        llm_config = resolve_llm_config_for_asset(asset)
        llm = init_asset_chat_model(asset, config=llm_config)
        executor = create_agent_executor(asset, llm, client)
        agent = RunnableWithMessageHistory(
            executor,
            _get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )
        with get_openai_callback():
            response = agent.invoke(
                {"input": query},
                config={"configurable": {"session_id": f"chat_session:{asset.id}:{conversation_id}"}},
            )

        answer, include_citations = _clean_agent_output(
            (response.get("output") or "").strip()
        )
        citations: list[dict] = []
        if asset.file_type == AssetFileType.VIDEO:
            answer = replace_line_refs_with_timestamps(
                asset, answer, prepend_style=False
            )
        elif asset.file_type == AssetFileType.PDF and include_citations:
            citations = _get_pdf_citations(answer, asset, client, llm)

        if not answer:
            raise ChatServiceError("Agent returned an empty answer")
        return answer, citations
    except ChatServiceError:
        raise
    except Exception as exc:
        raise ChatServiceError("Asset chat failed") from exc
    finally:
        if client is not None:
            client.close()
