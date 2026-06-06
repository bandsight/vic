from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from benchmarking_data_factory.workbench import agreement_pay_table_utils as agreement_pay_table_utils_module
from benchmarking_data_factory.workbench import llm_service as llm_service_module


def bind_llm_facade(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def _create_default_ssl_context_for_anthropic():
        return llm_service_module.create_default_ssl_context_for_anthropic(ctx._llm_service_config())

    def anthropic_ssl_context():
        ctx._anthropic_ssl_context = llm_service_module.anthropic_ssl_context(
            ctx._llm_service_config(),
            ctx._anthropic_ssl_context,
        )
        return ctx._anthropic_ssl_context

    def anthropic_client():
        return llm_service_module.anthropic_client(ctx._llm_service_config(), ctx.anthropic_ssl_context())

    def configured_anthropic_model(model: str | None = None) -> str:
        return llm_service_module.configured_anthropic_model(ctx._llm_service_config(), model)

    def configured_codex_model(model: str | None = None) -> str:
        return llm_service_module.configured_codex_model(ctx._llm_service_config(), model)

    def configured_llm_model(model: str | None = None) -> str:
        return llm_service_module.configured_llm_model(ctx._llm_service_config(), model)

    def llm_provider_status() -> dict[str, Any]:
        return llm_service_module.llm_provider_status(ctx._llm_service_config())

    def _status_for_provider(provider: str) -> dict[str, Any]:
        return llm_service_module.status_for_provider(provider, ctx._llm_service_config())

    def _openai_connection_status() -> dict[str, Any]:
        return llm_service_module.openai_connection_status(ctx._llm_service_config())

    def _llm_connection_providers() -> list[dict[str, Any]]:
        return llm_service_module.llm_connection_providers(ctx._llm_service_config())

    def _env_value(value: str) -> str:
        return llm_service_module.env_value(value)

    def _update_env_file(updates: dict[str, str]) -> None:
        llm_service_module.update_env_file(updates, ctx._llm_service_config())

    def llm_connections_status() -> dict[str, Any]:
        return llm_service_module.llm_connections_status(ctx._llm_service_config())

    def update_llm_connection(request: Any) -> dict[str, Any]:
        return llm_service_module.update_llm_connection(request, ctx._llm_service_config())

    def require_vision_llm() -> dict[str, Any]:
        return llm_service_module.require_vision_llm(ctx._llm_service_config())

    def llm_http_failure(raw: str, *, action: str, message: str):
        return llm_service_module.llm_http_failure(
            raw,
            action=action,
            message=message,
            config=ctx._llm_service_config(),
        )

    def call_llm(
        system: str,
        user_blocks: list[dict[str, Any]],
        max_tokens: int = 4000,
        model: str | None = None,
    ) -> str:
        return llm_service_module.call_llm(
            system=system,
            user_blocks=user_blocks,
            max_tokens=max_tokens,
            model=model,
            config=ctx._llm_service_config(),
            anthropic_client_factory=ctx.anthropic_client,
        )

    def strip_fences(text: str) -> str:
        return llm_service_module.strip_fences(text)

    def strip_json_preamble(text: str) -> str:
        return llm_service_module.strip_json_preamble(text)

    namespace.update({
        "_create_default_ssl_context_for_anthropic": _create_default_ssl_context_for_anthropic,
        "anthropic_ssl_context": anthropic_ssl_context,
        "anthropic_client": anthropic_client,
        "configured_anthropic_model": configured_anthropic_model,
        "configured_codex_model": configured_codex_model,
        "configured_llm_model": configured_llm_model,
        "llm_provider_status": llm_provider_status,
        "_status_for_provider": _status_for_provider,
        "_openai_connection_status": _openai_connection_status,
        "_llm_connection_providers": _llm_connection_providers,
        "_env_value": _env_value,
        "_update_env_file": _update_env_file,
        "llm_connections_status": llm_connections_status,
        "update_llm_connection": update_llm_connection,
        "require_vision_llm": require_vision_llm,
        "llm_http_failure": llm_http_failure,
        "call_llm": call_llm,
        "strip_fences": strip_fences,
        "strip_json_preamble": strip_json_preamble,
    })


def bind_pay_table_utility_facade(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def get_uplift_rule_dates(canonical: dict[str, Any]) -> list[str]:
        return agreement_pay_table_utils_module.get_uplift_rule_dates(canonical)

    def get_nominated_expiry(canonical: dict[str, Any], fetch_metadata_for_ae_id: Any | None = None) -> str | None:
        lookup = fetch_metadata_for_ae_id or ctx.fetch_metadata_for_ae_id
        return agreement_pay_table_utils_module.get_nominated_expiry(canonical, lookup)

    def _parse_iso_date(value: Any) -> str | None:
        return agreement_pay_table_utils_module.parse_iso_date(value)

    def _prepare_source_date_fields(table: dict[str, Any]) -> str | None:
        return agreement_pay_table_utils_module.prepare_source_date_fields(table)

    def _nearest_rule_date(source_iso: str, rule_dates: list[Any]) -> tuple[str | None, str | None]:
        return agreement_pay_table_utils_module.nearest_rule_date(source_iso, rule_dates)

    def apply_timeline_policy_to_tables(
        tables: list[dict[str, Any]],
        timeline_policy: str,
        uplift_rule_dates: list[str] | None,
    ) -> dict[str, Any]:
        return agreement_pay_table_utils_module.apply_timeline_policy_to_tables(
            tables,
            timeline_policy,
            uplift_rule_dates,
        )

    def recalc_to_dates(
        tables: list[dict[str, Any]],
        nominated_expiry: str | None,
        uplift_rule_dates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return agreement_pay_table_utils_module.recalc_to_dates(tables, nominated_expiry, uplift_rule_dates)

    def validate_pay_tables(
        tables: list[dict[str, Any]],
        nominated_expiry: str | None = None,
    ) -> list[dict[str, Any]]:
        return agreement_pay_table_utils_module.validate_pay_tables(tables, nominated_expiry)

    def _expand_table_rows(table: dict[str, Any]) -> dict[str, Any]:
        return agreement_pay_table_utils_module.expand_table_rows(table)

    def _normalise_effective_from(table: dict[str, Any]) -> dict[str, Any]:
        return agreement_pay_table_utils_module.normalise_effective_from(table)

    def _is_hourly_only_table(table: dict[str, Any]) -> bool:
        return agreement_pay_table_utils_module.is_hourly_only_table(table)

    def _candidate_table_rate_kind(table: dict[str, Any]) -> str:
        return agreement_pay_table_utils_module.candidate_table_rate_kind(table)

    def normalise_extracted_pay_table_candidates(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return agreement_pay_table_utils_module.normalise_extracted_pay_table_candidates(tables)

    def resolve_fwc(canonical: dict[str, Any], fetch_metadata: dict[str, Any]) -> dict[str, Any]:
        return agreement_pay_table_utils_module.resolve_fwc(canonical, fetch_metadata)

    def build_provenance_stamp(canonical: dict[str, Any], fetch_metadata: dict[str, Any], ae_id: str) -> dict[str, Any]:
        return agreement_pay_table_utils_module.build_provenance_stamp(
            canonical,
            fetch_metadata,
            ae_id,
            ctx.resolve_canonical_lga_short_name,
        )

    namespace.update({
        "get_uplift_rule_dates": get_uplift_rule_dates,
        "get_nominated_expiry": get_nominated_expiry,
        "_parse_iso_date": _parse_iso_date,
        "_prepare_source_date_fields": _prepare_source_date_fields,
        "_nearest_rule_date": _nearest_rule_date,
        "apply_timeline_policy_to_tables": apply_timeline_policy_to_tables,
        "recalc_to_dates": recalc_to_dates,
        "validate_pay_tables": validate_pay_tables,
        "_expand_table_rows": _expand_table_rows,
        "_normalise_effective_from": _normalise_effective_from,
        "_is_hourly_only_table": _is_hourly_only_table,
        "PAY_TABLE_EXTRACTION_RATE_PRIORITY": agreement_pay_table_utils_module.PAY_TABLE_EXTRACTION_RATE_PRIORITY,
        "_candidate_table_rate_kind": _candidate_table_rate_kind,
        "normalise_extracted_pay_table_candidates": normalise_extracted_pay_table_candidates,
        "resolve_fwc": resolve_fwc,
        "build_provenance_stamp": build_provenance_stamp,
    })
