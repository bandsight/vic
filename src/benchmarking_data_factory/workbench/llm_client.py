from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, MutableMapping

from benchmarking_data_factory.workbench.llm_boundary import (
    ANTHROPIC_PROVIDER_ALIASES,
    TEXT_ONLY_CODEX_PROVIDERS,
    llm_error_text,
    provider_status,
)


class LlmConnectionUpdateError(ValueError):
    """Raised when an LLM connection update request is unsupported."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


AnthropicClientFactory = Callable[[], Any]


def create_default_ssl_context_for_anthropic(ssl_module: Any) -> Any:
    context = ssl_module.SSLContext(ssl_module.PROTOCOL_TLS_CLIENT)
    try:
        import certifi

        context.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError, ssl_module.SSLError):
        pass
    try:
        context.load_default_certs(ssl_module.Purpose.SERVER_AUTH)
    except (OSError, ssl_module.SSLError):
        pass
    return context


def anthropic_ssl_context(ssl_module: Any, cached_context: Any | None = None) -> Any:
    if cached_context is not None:
        return cached_context

    context = create_default_ssl_context_for_anthropic(ssl_module)
    enum_certificates = getattr(ssl_module, "enum_certificates", None)
    if enum_certificates is not None:
        for store_name in ("ROOT", "CA"):
            try:
                certificates = enum_certificates(store_name)
            except OSError:
                continue
            for cert_bytes, encoding, _trust in certificates:
                if encoding != "x509_asn":
                    continue
                try:
                    context.load_verify_locations(cadata=ssl_module.DER_cert_to_PEM_cert(cert_bytes))
                except ssl_module.SSLError:
                    continue
    return context


def create_anthropic_client(env: MutableMapping[str, str], ssl_context: Any) -> Any | None:
    import anthropic

    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return anthropic.Anthropic(
        api_key=key,
        http_client=anthropic.DefaultHttpxClient(verify=ssl_context),
    )


def configured_anthropic_model(
    env: MutableMapping[str, str],
    default_model: str,
    model: str | None = None,
) -> str:
    return (model or env.get("ANTHROPIC_MODEL") or env.get("EXTRACT_MODEL") or default_model).strip()


def configured_codex_model(
    env: MutableMapping[str, str],
    default_model: str,
    model: str | None = None,
) -> str:
    return (model or env.get("EXTRACT_MODEL") or default_model).strip()


def configured_llm_model(
    env: MutableMapping[str, str],
    default_anthropic_model: str,
    default_codex_model: str,
    model: str | None = None,
) -> str:
    if model:
        return model.strip()
    provider = (env.get("EXTRACT_PROVIDER") or "anthropic").strip().lower()
    if provider in ANTHROPIC_PROVIDER_ALIASES:
        return configured_anthropic_model(env, default_anthropic_model)
    if provider in TEXT_ONLY_CODEX_PROVIDERS:
        return configured_codex_model(env, default_codex_model)
    return (env.get("EXTRACT_MODEL") or env.get("ANTHROPIC_MODEL") or default_anthropic_model).strip()


def status_for_provider(
    env: MutableMapping[str, str],
    provider: str,
    default_anthropic_model: str,
    default_codex_model: str,
) -> dict[str, Any]:
    scoped_env = dict(env)
    scoped_env["EXTRACT_PROVIDER"] = provider
    return provider_status(scoped_env, default_anthropic_model, default_codex_model)


def openai_connection_status(env: MutableMapping[str, str]) -> dict[str, Any]:
    key_set = bool(env.get("OPENAI_API_KEY"))
    return {
        "provider": "openai",
        "model": env.get("OPENAI_MODEL") or "not configured",
        "ready": False,
        "text_capable": False,
        "vision_capable": False,
        "credential": "set" if key_set else "missing",
        "message": "OpenAI key detected; the GPT vision extraction adapter is not wired in this workbench yet."
        if key_set
        else "OPENAI_API_KEY not set; GPT vision extraction adapter is not wired yet.",
    }


def llm_connection_providers(
    env: MutableMapping[str, str],
    default_anthropic_model: str,
    default_codex_model: str,
) -> list[dict[str, Any]]:
    active_provider = (env.get("EXTRACT_PROVIDER") or "anthropic").strip().lower()
    providers = [
        {
            "id": "anthropic",
            "label": "Anthropic Claude",
            "description": "Vision-capable extraction path used for pay tables and page-image review.",
            "capability_label": "Text + vision",
            "adapter_state": "supported",
            "can_activate": True,
            "credential_env": "ANTHROPIC_API_KEY",
            "model_env": "ANTHROPIC_MODEL",
            "default_model": default_anthropic_model,
            "status": status_for_provider(env, "anthropic", default_anthropic_model, default_codex_model),
        },
        {
            "id": "openclaw_codex",
            "label": "OpenClaw Codex CLI",
            "description": "Local text-only fallback. Useful for narrative helpers, blocked for image extraction.",
            "capability_label": "Text only",
            "adapter_state": "supported_text_only",
            "can_activate": True,
            "credential_env": "",
            "model_env": "EXTRACT_MODEL",
            "default_model": default_codex_model,
            "status": status_for_provider(env, "openclaw_codex", default_anthropic_model, default_codex_model),
        },
        {
            "id": "openai",
            "label": "OpenAI GPT vision",
            "description": "Reserved provider slot for GPT image/PDF extraction once the backend adapter is added.",
            "capability_label": "Planned",
            "adapter_state": "planned",
            "can_activate": False,
            "credential_env": "OPENAI_API_KEY",
            "model_env": "OPENAI_MODEL",
            "default_model": "",
            "status": openai_connection_status(env),
        },
    ]
    for provider in providers:
        aliases = {"anthropic": {"anthropic", "claude"}, "openclaw_codex": TEXT_ONLY_CODEX_PROVIDERS}.get(
            provider["id"],
            {provider["id"]},
        )
        provider["active"] = active_provider in aliases
    return providers


def env_value(value: str) -> str:
    text = str(value or "")
    if text == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:@+\-=]+", text):
        return text
    return json.dumps(text)


def update_env_file(env_file: Path, updates: dict[str, str]) -> None:
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            output.append(f"{key}={env_value(remaining.pop(key, ''))}")
        else:
            output.append(line)
    if output and remaining:
        output.append("")
    for key, value in remaining.items():
        output.append(f"{key}={env_value(value)}")
    env_file.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def llm_connections_status(
    env: MutableMapping[str, str],
    env_file: Path,
    default_anthropic_model: str,
    default_codex_model: str,
) -> dict[str, Any]:
    return {
        "llm": {
            "active": provider_status(env, default_anthropic_model, default_codex_model),
            "providers": llm_connection_providers(env, default_anthropic_model, default_codex_model),
        },
        "env_file": {
            "exists": env_file.exists(),
            "path": str(env_file),
        },
    }


def update_llm_connection(
    *,
    provider: str,
    model: str = "",
    api_key: str = "",
    env: MutableMapping[str, str],
    env_file: Path,
    default_anthropic_model: str,
    default_codex_model: str,
) -> dict[str, Any]:
    provider_normalised = (provider or "").strip().lower()
    if provider_normalised in ANTHROPIC_PROVIDER_ALIASES:
        selected_model = (model or "").strip() or default_anthropic_model
        updates = {
            "EXTRACT_PROVIDER": "anthropic",
            "ANTHROPIC_MODEL": selected_model,
        }
        env["EXTRACT_PROVIDER"] = "anthropic"
        env["ANTHROPIC_MODEL"] = selected_model
        cleaned_key = (api_key or "").strip()
        if cleaned_key:
            updates["ANTHROPIC_API_KEY"] = cleaned_key
            env["ANTHROPIC_API_KEY"] = cleaned_key
        update_env_file(env_file, updates)
        return llm_connections_status(env, env_file, default_anthropic_model, default_codex_model)

    if provider_normalised in TEXT_ONLY_CODEX_PROVIDERS:
        selected_model = (model or "").strip() or default_codex_model
        updates = {
            "EXTRACT_PROVIDER": "openclaw_codex",
            "EXTRACT_MODEL": selected_model,
        }
        env["EXTRACT_PROVIDER"] = "openclaw_codex"
        env["EXTRACT_MODEL"] = selected_model
        update_env_file(env_file, updates)
        return llm_connections_status(env, env_file, default_anthropic_model, default_codex_model)

    if provider_normalised in {"openai", "gpt"}:
        raise LlmConnectionUpdateError(
            "OpenAI configuration is visible in Settings, but GPT vision extraction is not wired yet."
        )

    raise LlmConnectionUpdateError(f"Unsupported LLM provider: {provider}")


def call_llm(
    *,
    system: str,
    user_blocks: list[dict[str, Any]],
    max_tokens: int = 4000,
    model: str | None = None,
    env: MutableMapping[str, str],
    default_anthropic_model: str,
    default_codex_model: str,
    anthropic_client_factory: AnthropicClientFactory,
) -> str:
    provider_raw = (env.get("EXTRACT_PROVIDER") or "anthropic").strip()
    provider = provider_raw.lower()
    print(f"[extract] provider={provider_raw}")

    if provider in ANTHROPIC_PROVIDER_ALIASES:
        model_name = configured_anthropic_model(env, default_anthropic_model, model)
        client = anthropic_client_factory()
        if client is None:
            return llm_error_text("ANTHROPIC_API_KEY not set")
        try:
            resp = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_blocks}],
            )
            return resp.content[0].text if resp.content else ""
        except Exception as exc:
            return llm_error_text(f"{type(exc).__name__}: {exc}")

    if provider in TEXT_ONLY_CODEX_PROVIDERS:
        model_name = configured_codex_model(env, default_codex_model, model)
        full_model = f"openai-codex/{model_name}"

        text_parts: list[str] = []
        for block in user_blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                raise RuntimeError(
                    "OpenClaw Codex CLI provider currently supports text-only calls; image extraction requires Anthropic or a media-capable route."
                )
            text_parts.append(str(block.get("text") or ""))

        joined_text = "\n\n".join(text_parts)
        prompt_text = (
            "IGNORE ALL PRIOR CONTEXT.\n"
            "You are executing a stateless EBA Workbench extraction call.\n"
            "Follow only the instructions in this prompt.\n"
            "Return only the requested machine-readable output.\n"
            "Do not explain.\n"
            "Do not answer conversationally.\n"
            "Do not use markdown fences.\n\n"
            f"System (untrusted):\n{system}\n\n"
            f"USER:\n{joined_text}\n\n"
            "FINAL OUTPUT RULE:\n"
            "Return only the requested output. No commentary. No markdown fences."
        )
        cmd = [
            "openclaw",
            "infer",
            "model",
            "run",
            "--gateway",
            "--model",
            full_model,
            "--prompt",
            prompt_text,
            "--json",
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()

        if proc.returncode != 0:
            raise RuntimeError(
                f"OpenClaw Codex command failed: cmd={cmd!r} returncode={proc.returncode} stdout={stdout!r} stderr={stderr!r}"
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"OpenClaw Codex returned non-JSON output: cmd={cmd!r} stdout={stdout!r} stderr={stderr!r}"
            ) from exc

        if data.get("ok") is not True:
            raise RuntimeError(
                f"OpenClaw Codex returned ok!=true: cmd={cmd!r} stdout={stdout!r} stderr={stderr!r}"
            )

        outputs = data.get("outputs")
        if not isinstance(outputs, list) or not outputs or not isinstance(outputs[0], dict) or not isinstance(outputs[0].get("text"), str):
            raise RuntimeError(
                f"OpenClaw Codex returned missing outputs[0].text: cmd={cmd!r} stdout={stdout!r} stderr={stderr!r}"
            )

        return outputs[0]["text"]

    return llm_error_text(f"Unsupported EXTRACT_PROVIDER: {provider_raw}")


__all__ = [
    "LlmConnectionUpdateError",
    "anthropic_ssl_context",
    "call_llm",
    "configured_anthropic_model",
    "configured_codex_model",
    "configured_llm_model",
    "create_anthropic_client",
    "create_default_ssl_context_for_anthropic",
    "env_value",
    "llm_connection_providers",
    "llm_connections_status",
    "openai_connection_status",
    "status_for_provider",
    "update_env_file",
    "update_llm_connection",
]
