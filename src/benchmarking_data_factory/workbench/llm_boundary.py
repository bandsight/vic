from __future__ import annotations

from typing import Any, Mapping

LLM_ERROR_PREFIX = "ERROR:"
ANTHROPIC_PROVIDER_ALIASES = {"anthropic", "claude"}
TEXT_ONLY_CODEX_PROVIDERS = {"openclaw_codex", "openai-codex", "openclaw-codex"}


def provider_status(env: Mapping[str, str], default_model: str, default_text_model: str = "gpt-5.4") -> dict[str, Any]:
    provider_raw = (env.get("EXTRACT_PROVIDER") or "anthropic").strip()
    provider = provider_raw.lower()
    status = {
        "provider": provider_raw,
        "model": env.get("EXTRACT_MODEL") or default_model,
        "ready": False,
        "text_capable": False,
        "vision_capable": False,
        "credential": "missing",
        "message": "",
    }
    if provider in ANTHROPIC_PROVIDER_ALIASES:
        key_set = bool(env.get("ANTHROPIC_API_KEY"))
        status["model"] = env.get("ANTHROPIC_MODEL") or env.get("EXTRACT_MODEL") or default_model
        status.update({
            "ready": key_set,
            "text_capable": key_set,
            "vision_capable": key_set,
            "credential": "set" if key_set else "missing",
            "message": "Anthropic vision provider ready" if key_set else "ANTHROPIC_API_KEY not set",
        })
        return status
    if provider in TEXT_ONLY_CODEX_PROVIDERS:
        status["model"] = env.get("EXTRACT_MODEL") or default_text_model
        status.update({
            "ready": True,
            "text_capable": True,
            "vision_capable": False,
            "credential": "managed",
            "message": "OpenClaw Codex provider is text-only in this workbench; table extraction needs vision.",
        })
        return status
    status["message"] = f"Unsupported EXTRACT_PROVIDER: {provider_raw}"
    return status


def is_llm_error(raw: str) -> bool:
    return (raw or "").strip().startswith(LLM_ERROR_PREFIX)


def llm_error_text(reason: str) -> str:
    reason = (reason or "").strip()
    return reason if is_llm_error(reason) else f"{LLM_ERROR_PREFIX} {reason}"


def llm_failure_detail(
    raw: str,
    *,
    action: str,
    message: str,
    provider: str | None = None,
    model: str | None = None,
    status: str = "llm_error",
) -> dict[str, Any]:
    reason = (raw or "").strip()
    if reason.startswith(LLM_ERROR_PREFIX):
        reason = reason[len(LLM_ERROR_PREFIX):].strip()
    return {
        "status": status,
        "action": action,
        "message": message,
        "provider": provider,
        "model": model,
        "reason": reason or "LLM adapter returned an empty failure response.",
    }


def vision_required_detail(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "action": "vision_extraction",
        "message": "Vision-capable LLM provider is required for pay-table extraction.",
        "provider": status.get("provider"),
        "model": status.get("model"),
        "reason": status.get("message"),
    }
