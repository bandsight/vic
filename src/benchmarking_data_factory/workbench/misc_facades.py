from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from benchmarking_data_factory.workbench import app_bootstrap as app_bootstrap_module
from benchmarking_data_factory.workbench import council_read_model as council_read_model_module
from benchmarking_data_factory.workbench import extraction_orchestration as extraction_orchestration_module
from benchmarking_data_factory.workbench import intake_quality as intake_quality_module
from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench import review_learning as review_learning_module
from benchmarking_data_factory.workbench import uplift_rules_workflow as uplift_rules_workflow_module


def intake_quality_service(ctx: Any) -> intake_quality_module.IntakeQualityService:
    service = getattr(ctx, "_intake_quality_service", None)
    if service is None:
        service = intake_quality_module.IntakeQualityService(
            deps_factory=ctx._intake_workflow_dependencies,
            now=ctx.now_iso,
        )
        setattr(ctx, "_intake_quality_service", service)
    return service


def bind_intake_workflow_facades(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def build_intake_quality_summary(
        council_rows: list[dict[str, Any]] | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return intake_quality_service(ctx).summary(council_rows, force_refresh=force_refresh)

    def build_intake_candidate_rows() -> list[dict[str, Any]]:
        return intake_workflow_module.build_intake_candidate_rows(ctx._intake_workflow_dependencies())

    def fetch_fair_work_registry_intake(
        *,
        force_registry: bool = True,
        fetch_pdfs: bool = False,
        pdf_limit: int | None = None,
    ) -> dict[str, Any]:
        result = intake_workflow_module.fetch_fair_work_registry_intake(
            force_registry=force_registry,
            fetch_pdfs=fetch_pdfs,
            pdf_limit=pdf_limit,
            deps=ctx._intake_workflow_dependencies(),
        )
        intake_quality_service(ctx).invalidate("fair_work_registry_fetch")
        return result

    def clear_review_record(
        ae_id: str,
        *,
        reason: str = "",
        include_related: bool = True,
    ) -> dict[str, Any]:
        return intake_workflow_module.clear_review_record(
            ae_id,
            reason=reason,
            include_related=include_related,
            deps=ctx._intake_workflow_dependencies(),
        )

    namespace.update({
        "build_intake_quality_summary": build_intake_quality_summary,
        "build_intake_candidate_rows": build_intake_candidate_rows,
        "fetch_fair_work_registry_intake": fetch_fair_work_registry_intake,
        "clear_review_record": clear_review_record,
    })


def bind_uplift_facades(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def _serialise_suggestion(suggestion) -> dict[str, Any]:
        return uplift_rules_workflow_module.serialise_suggestion(suggestion)

    def _suggestion_status(payload: dict[str, Any]) -> str:
        return uplift_rules_workflow_module.suggestion_status(payload)

    def _failed_suggestion_detail(payload: dict[str, Any]) -> dict[str, str]:
        return uplift_rules_workflow_module.failed_suggestion_detail(payload)

    def _uplift_adapter():
        return uplift_rules_workflow_module.uplift_adapter(ctx._uplift_workflow_dependencies())

    namespace.update({
        "_serialise_suggestion": _serialise_suggestion,
        "_suggestion_status": _suggestion_status,
        "_failed_suggestion_detail": _failed_suggestion_detail,
        "_uplift_adapter": _uplift_adapter,
    })


def bind_council_api_facades(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def build_council_summary(
        ae_id: str,
        registry: dict[str, str] | None = None,
        decisions: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return council_read_model_module.build_council_summary(
            ae_id,
            registry=registry,
            decisions=decisions,
            deps=ctx._council_read_model_dependencies(),
        )

    def api_llm_status() -> dict[str, Any]:
        return ctx.llm_provider_status()

    def api_connections() -> dict[str, Any]:
        return ctx.llm_connections_status()

    def api_update_llm_connection(request: Any) -> dict[str, Any]:
        return ctx.update_llm_connection(request)

    def api_councils(include_split_parents: bool = False) -> list[dict[str, Any]]:
        return council_read_model_module.list_councils(include_split_parents, ctx._council_read_model_dependencies())

    def api_pipeline_matrix() -> list[dict[str, Any]]:
        return ctx.api_councils()

    def api_council(ae_id: str) -> dict[str, Any]:
        return council_read_model_module.get_council(ae_id, ctx._council_read_model_dependencies())

    namespace.update({
        "build_council_summary": build_council_summary,
        "api_llm_status": api_llm_status,
        "api_connections": api_connections,
        "api_update_llm_connection": api_update_llm_connection,
        "api_councils": api_councils,
        "api_pipeline_matrix": api_pipeline_matrix,
        "api_council": api_council,
    })


def bind_extraction_facades(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def parse_overview_response(
        raw: str,
        page_count: int,
        pay_pages: list[int],
        uplift_pages: list[int],
        alteration_pages: list[int],
    ) -> dict[str, Any]:
        return extraction_orchestration_module.parse_overview_response(
            raw,
            page_count,
            pay_pages,
            uplift_pages,
            alteration_pages,
            strip_json_preamble=ctx.strip_json_preamble,
        )

    def _conditions_candidate_page_blocks(ae_id: str, *, max_pages: int = 28) -> tuple[list[dict[str, Any]], list[int]]:
        return extraction_orchestration_module.conditions_candidate_page_blocks(
            ae_id,
            max_pages=max_pages,
            deps=ctx._extraction_orchestration_dependencies(),
        )

    def _normalise_conditions_extraction_payload(
        parsed: Any,
        *,
        ae_id: str,
        council_name: str,
        candidate_pages: list[int],
    ) -> dict[str, Any]:
        return extraction_orchestration_module.normalise_conditions_extraction_payload(
            parsed,
            ae_id=ae_id,
            council_name=council_name,
            candidate_pages=candidate_pages,
            deps=ctx._extraction_orchestration_dependencies(),
        )

    namespace.update({
        "parse_overview_response": parse_overview_response,
        "_conditions_candidate_page_blocks": _conditions_candidate_page_blocks,
        "_normalise_conditions_extraction_payload": _normalise_conditions_extraction_payload,
    })


def bind_app_facades(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def compute_asset_version() -> str:
        return app_bootstrap_module.compute_asset_version(ctx.STATIC_DIR, ctx.ASSET_FILES)

    def root():
        return app_bootstrap_module.root_response(ctx)

    namespace.update({
        "compute_asset_version": compute_asset_version,
        "root": root,
    })


def bind_review_learning_facade(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def build_review_learning_snapshot(include_split_parents: bool = False) -> dict[str, Any]:
        visible_ids = ctx.analysis_visible_ae_ids(include_split_parents=include_split_parents)
        records: list[tuple[str, dict[str, Any]]] = []
        scenario_states: dict[str, dict[str, Any]] = {}
        for ae_id in visible_ids:
            try:
                records.append((ae_id, ctx.get_canonical(ae_id)))
                scenario_states[ae_id] = ctx._read_scenario_override_state(ae_id)
            except Exception:
                continue
        return review_learning_module.build_review_learning_snapshot(records, scenario_states=scenario_states)

    namespace["build_review_learning_snapshot"] = build_review_learning_snapshot
