from functools import lru_cache

import redis
from django.conf import settings
from langchain_community.callbacks.manager import get_openai_callback
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_redis import RedisChatMessageHistory

from app.domain.agents import create_agent_executor
from app.domain.vector_db import get_vector_database
from app.models.asset import Asset
from app.utils.openai import init_asset_chat_model, resolve_llm_config_for_asset

CHAT_HISTORY_TTL_SECONDS = 4 * 60 * 60


class ChatServiceError(Exception):
    """Raised when asset chat cannot be completed."""


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _get_session_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(session_id=session_id, redis_client=_redis_client(), ttl=CHAT_HISTORY_TTL_SECONDS, key_prefix="learnlens:chat:")


def chat_with_asset(*, asset: Asset, query: str, conversation_id: str) -> str:
    vector_db = get_vector_database()
    client = None
    try:
        client = vector_db.get_client()
        llm = init_asset_chat_model(asset, config=resolve_llm_config_for_asset(asset))
        executor = create_agent_executor(asset, llm, client)
        agent = RunnableWithMessageHistory(executor, _get_session_history, input_messages_key="input", history_messages_key="chat_history")
        with get_openai_callback():
            response = agent.invoke({"input": query}, config={"configurable": {"session_id": conversation_id}})
        answer = (response.get("output") or "").strip()
        if not answer:
            raise ChatServiceError("Agent returned an empty answer")
        return answer
    except ChatServiceError:
        raise
    except Exception as exc:
        raise ChatServiceError("Asset chat failed") from exc
    finally:
        if client is not None:
            client.close()
