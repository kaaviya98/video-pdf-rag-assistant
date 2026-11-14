from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

from django.conf import settings
from langchain.chat_models import init_chat_model

from app.domain.organization import get_default_organization_llm_settings
from app.models.organization import LLMProvider

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.organization import Organization

DEFAULT_LLM_MODEL = "gpt-4o-mini"

_OPENAI_IMAGE_MODEL_PREFIXES = (
    "chatgpt-4o",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.5",
    "gpt-4-turbo",
    "gpt-5",
    "o1",
    "o3",
    "o4-mini",
)
_OPENAI_TEXT_ONLY_MARKERS = (
    "audio",
    "realtime",
    "search",
    "transcribe",
    "tts",
    "turbo-preview",
    "o1-mini",
    "o1-preview",
    "o3-mini",
)


@dataclass(frozen=True)
class ResolvedLLMConfig:
    api_key: str
    model: str
    provider: int


def _default_llm_model() -> str:
    return getattr(settings, "ORG_DEFAULT_LLM_MODEL", DEFAULT_LLM_MODEL)


def _resolve_env_api_key(scope_key: str | None) -> str:
    return cast("str", settings.OPENAI_API_KEY)


def _env_openai_config(scope_key: str | None) -> ResolvedLLMConfig:
    return ResolvedLLMConfig(
        api_key=_resolve_env_api_key(scope_key),
        model=_default_llm_model(),
        provider=LLMProvider.OPENAI,
    )


def _provider_name(provider: int) -> str:
    if provider == LLMProvider.GOOGLE_GEMINI:
        return "google_genai"
    return "openai"


def resolve_llm_config(
    *,
    organization: Organization | None = None,
    scope_key: str | None = None,
) -> ResolvedLLMConfig:
    """Resolve chat/LLM settings for any supported provider."""
    if organization is not None:
        llm_settings = get_default_organization_llm_settings(organization)
        if llm_settings is not None:
            api_key = (llm_settings.api_key or "").strip()
            if api_key:
                return ResolvedLLMConfig(
                    api_key=api_key,
                    model=(llm_settings.model or "").strip() or _default_llm_model(),
                    provider=llm_settings.provider,
                )

    return _env_openai_config(scope_key)


def supports_image_url_input(config: ResolvedLLMConfig) -> bool:
    """Whether the configured chat model can read images passed by URL."""
    if config.provider != LLMProvider.OPENAI:
        return False
    model = config.model.strip().lower()
    return model.startswith(_OPENAI_IMAGE_MODEL_PREFIXES) and not any(
        marker in model for marker in _OPENAI_TEXT_ONLY_MARKERS
    )


def resolve_openai_runtime_config(
    *,
    organization: Organization | None = None,
    scope_key: str | None = None,
) -> ResolvedLLMConfig:
    """Resolve settings for OpenAI-only clients (embeddings, Marker, langchain_openai).

    Org Gemini keys must not be passed into OpenAI SDKs; fall back to env OpenAI keys.
    """
    config = resolve_llm_config(organization=organization, scope_key=scope_key)
    if config.provider != LLMProvider.OPENAI:
        return _env_openai_config(scope_key)
    return config


def resolve_llm_config_for_asset(asset: Asset) -> ResolvedLLMConfig:
    organization = asset.organization if asset.organization_id else None
    return resolve_llm_config(organization=organization, scope_key=asset.scope_key)


def resolve_openai_runtime_config_for_asset(asset: Asset) -> ResolvedLLMConfig:
    organization = asset.organization if asset.organization_id else None
    return resolve_openai_runtime_config(
        organization=organization,
        scope_key=asset.scope_key,
    )


def resolve_openai_api_key(
    scope_key: str | None = None,
    *,
    organization: Organization | None = None,
) -> str:
    return resolve_openai_runtime_config(
        organization=organization,
        scope_key=scope_key,
    ).api_key


def init_scope_chat_model(
    scope_key: str | None,
    model: str,
    *,
    organization: Organization | None = None,
    config: ResolvedLLMConfig | None = None,
) -> Any:
    resolved = config or resolve_llm_config(
        organization=organization,
        scope_key=scope_key,
    )
    return init_chat_model(
        model,
        model_provider=_provider_name(resolved.provider),
        api_key=resolved.api_key,
    )


def init_asset_chat_model(
    asset: Asset,
    model: str | None = None,
    *,
    config: ResolvedLLMConfig | None = None,
) -> Any:
    resolved = config or resolve_llm_config_for_asset(asset)
    return init_chat_model(
        model or resolved.model,
        model_provider=_provider_name(resolved.provider),
        api_key=resolved.api_key,
    )


def init_generic_chat_model(
    organization: Organization,
    *,
    max_retries: int | None = None,
    timeout: float | None = None,
    config: ResolvedLLMConfig | None = None,
    max_output_tokens: int | None = None,
) -> Any:
    resolved = config or resolve_llm_config(organization=organization)
    options: dict[str, Any] = {}
    if resolved.provider == LLMProvider.OPENAI:
        options["stream_usage"] = True
    if max_output_tokens is not None:
        token_option = (
            "max_output_tokens"
            if resolved.provider == LLMProvider.GOOGLE_GEMINI
            else "max_tokens"
        )
        options[token_option] = max_output_tokens
    if max_retries is not None:
        options["max_retries"] = max_retries
    if timeout is not None:
        options["timeout"] = timeout
    return init_chat_model(
        resolved.model,
        model_provider=_provider_name(resolved.provider),
        api_key=resolved.api_key,
        **options,
    )


def get_model_response_text(response: Any) -> str:
    metadata = getattr(response, "response_metadata", {}) or {}
    finish_reason = str(metadata.get("finish_reason", "")).lower()
    if finish_reason in {
        "length",
        "max_tokens",
        "content_filter",
        "safety",
        "recitation",
        "tool_calls",
        "function_call",
    }:
        message = "Model response did not complete successfully"
        raise ValueError(message)
    content = getattr(response, "content", None)
    if isinstance(content, list):
        content = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    if not isinstance(content, str) or not content.strip():
        message = "Model response contains no text"
        raise ValueError(message)
    return content.strip()


def parse_openai_callback(openai_callback: Any) -> dict[str, Any] | None:
    return {
        "prompt_tokens": openai_callback.prompt_tokens,
        "completion_tokens": openai_callback.completion_tokens,
        "total_tokens": openai_callback.total_tokens,
        "prompt_tokens_cached": getattr(openai_callback, "prompt_tokens_cached", 0),
        "reasoning_tokens": getattr(openai_callback, "reasoning_tokens", 0),
        "successful_requests": openai_callback.successful_requests,
        "total_cost": openai_callback.total_cost,
    }
