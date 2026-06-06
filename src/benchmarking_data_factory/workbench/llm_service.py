from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, MutableMapping

from fastapi import HTTPException

from benchmarking_data_factory.extraction.llm_output import strip_fences, strip_json_preamble
from benchmarking_data_factory.workbench.llm_boundary import (
    llm_failure_detail,
    provider_status,
    vision_required_detail,
)
from benchmarking_data_factory.workbench.llm_client import (
    LlmConnectionUpdateError,
    anthropic_ssl_context as llm_client_anthropic_ssl_context,
    call_llm as llm_client_call_llm,
    configured_anthropic_model as llm_client_configured_anthropic_model,
    configured_codex_model as llm_client_configured_codex_model,
    configured_llm_model as llm_client_configured_llm_model,
    create_anthropic_client as llm_client_create_anthropic_client,
    create_default_ssl_context_for_anthropic as llm_client_create_default_ssl_context_for_anthropic,
    env_value as llm_client_env_value,
    llm_connection_providers as llm_client_connection_providers,
    llm_connections_status as llm_client_connections_status,
    openai_connection_status as llm_client_openai_connection_status,
    status_for_provider as llm_client_status_for_provider,
    update_env_file as llm_client_update_env_file,
    update_llm_connection as llm_client_update_llm_connection,
)


@dataclass(frozen=True)
class LlmServiceConfig:
    env: MutableMapping[str, str]
    env_file: Path
    default_anthropic_model: str
    default_codex_model: str
    ssl_module: Any


def create_default_ssl_context_for_anthropic(config: LlmServiceConfig) -> Any:
    return llm_client_create_default_ssl_context_for_anthropic(config.ssl_module)


def anthropic_ssl_context(config: LlmServiceConfig, cached_context: Any | None) -> Any:
    return llm_client_anthropic_ssl_context(config.ssl_module, cached_context)


def anthropic_client(config: LlmServiceConfig, ssl_context: Any) -> Any:
    return llm_client_create_anthropic_client(config.env, ssl_context)


def configured_anthropic_model(config: LlmServiceConfig, model: str | None = None) -> str:
    return llm_client_configured_anthropic_model(config.env, config.default_anthropic_model, model)


def configured_codex_model(config: LlmServiceConfig, model: str | None = None) -> str:
    return llm_client_configured_codex_model(config.env, config.default_codex_model, model)


def configured_llm_model(config: LlmServiceConfig, model: str | None = None) -> str:
    return llm_client_configured_llm_model(
        config.env,
        config.default_anthropic_model,
        config.default_codex_model,
        model,
    )


def llm_provider_status(config: LlmServiceConfig) -> dict[str, Any]:
    return provider_status(config.env, config.default_anthropic_model, config.default_codex_model)


def status_for_provider(provider: str, config: LlmServiceConfig) -> dict[str, Any]:
    return llm_client_status_for_provider(
        config.env,
        provider,
        config.default_anthropic_model,
        config.default_codex_model,
    )


def openai_connection_status(config: LlmServiceConfig) -> dict[str, Any]:
    return llm_client_openai_connection_status(config.env)


def llm_connection_providers(config: LlmServiceConfig) -> list[dict[str, Any]]:
    return llm_client_connection_providers(
        config.env,
        config.default_anthropic_model,
        config.default_codex_model,
    )


def env_value(value: str) -> str:
    return llm_client_env_value(value)


def update_env_file(updates: dict[str, str], config: LlmServiceConfig) -> None:
    llm_client_update_env_file(config.env_file, updates)


def llm_connections_status(config: LlmServiceConfig) -> dict[str, Any]:
    return llm_client_connections_status(
        config.env,
        config.env_file,
        config.default_anthropic_model,
        config.default_codex_model,
    )


def update_llm_connection(request: Any, config: LlmServiceConfig) -> dict[str, Any]:
    try:
        return llm_client_update_llm_connection(
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            env=config.env,
            env_file=config.env_file,
            default_anthropic_model=config.default_anthropic_model,
            default_codex_model=config.default_codex_model,
        )
    except LlmConnectionUpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def require_vision_llm(config: LlmServiceConfig) -> dict[str, Any]:
    status = llm_provider_status(config)
    if not status.get("ready") or not status.get("vision_capable"):
        raise HTTPException(status_code=503, detail=vision_required_detail(status))
    return status


def llm_http_failure(raw: str, *, action: str, message: str, config: LlmServiceConfig) -> HTTPException:
    status = llm_provider_status(config)
    blocked = not status.get("ready")
    return HTTPException(
        status_code=503 if blocked else 502,
        detail=llm_failure_detail(
            raw,
            action=action,
            message=message,
            provider=status.get("provider"),
            model=status.get("model"),
            status="blocked" if blocked else "llm_error",
        ),
    )


def call_llm(
    *,
    system: str,
    user_blocks: list[dict[str, Any]],
    max_tokens: int,
    model: str | None,
    config: LlmServiceConfig,
    anthropic_client_factory: Any,
) -> str:
    return llm_client_call_llm(
        system=system,
        user_blocks=user_blocks,
        max_tokens=max_tokens,
        model=model,
        env=config.env,
        default_anthropic_model=config.default_anthropic_model,
        default_codex_model=config.default_codex_model,
        anthropic_client_factory=anthropic_client_factory,
    )
