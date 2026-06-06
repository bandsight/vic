from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body

from benchmarking_data_factory.workbench import agreement_extraction as agreement_extraction_module
from benchmarking_data_factory.workbench import pay_table_workflow as pay_table_workflow_module
from benchmarking_data_factory.workbench.agreement_workspace import AgreementWorkspaceService
from benchmarking_data_factory.workbench.api_models import (
    PayTableExtractRequest,
    PayTableRangeRequest,
    PayTableRecalcDatesRequest,
    PayTableSaveRequest,
    ReviewHintsRequest,
    SuggestDatesRequest,
)


AgreementExtractionDependenciesFactory = Callable[
    [],
    agreement_extraction_module.AgreementExtractionDependencies,
]
PayTableWorkflowDependenciesFactory = Callable[
    [],
    pay_table_workflow_module.PayTableWorkflowDependencies,
]
AgreementWorkspaceServiceFactory = Callable[[], AgreementWorkspaceService]


def build_agreement_pay_table_router(
    agreement_dependencies: AgreementExtractionDependenciesFactory,
    pay_table_dependencies: PayTableWorkflowDependenciesFactory,
) -> APIRouter:
    return build_agreement_pay_table_router_for_service(
        lambda: _workspace_service_from_pay_table_deps(agreement_dependencies, pay_table_dependencies)
    )


def build_agreement_pay_table_router_for_service(
    workspace: AgreementWorkspaceService | AgreementWorkspaceServiceFactory,
) -> APIRouter:
    router = APIRouter()

    def service() -> AgreementWorkspaceService:
        return workspace() if callable(workspace) else workspace

    @router.post("/api/councils/{ae_id}/overview/generate")
    def api_generate_overview(ae_id: str) -> dict[str, Any]:
        return service().generate_overview(ae_id)

    @router.post("/api/councils/{ae_id}/pay-tables/find-candidates")
    def api_pay_candidates(ae_id: str) -> dict[str, Any]:
        return service().pay_table_candidate_pages(ae_id)

    @router.post("/api/councils/{ae_id}/pay-tables/extract")
    def api_pay_extract(ae_id: str, request: PayTableExtractRequest) -> dict[str, Any]:
        return service().extract_pay_table_page(ae_id, request)

    @router.post("/api/councils/{ae_id}/pay-tables/extract-range")
    def api_pay_extract_range(ae_id: str, request: PayTableRangeRequest) -> dict[str, Any]:
        return service().extract_pay_table_range(ae_id, request)

    @router.post("/api/councils/{ae_id}/entitlements/extract")
    def api_entitlements_extract(ae_id: str) -> dict[str, Any]:
        return service().extract_entitlements(ae_id)

    @router.post("/api/councils/{ae_id}/pay-tables/save")
    def api_pay_save(ae_id: str, request: PayTableSaveRequest) -> dict[str, Any]:
        return service().save_pay_tables(ae_id, request)

    @router.post("/api/councils/{ae_id}/pay-tables/validate")
    def api_pay_validate(ae_id: str) -> dict[str, Any]:
        return service().validate_pay_tables(ae_id)

    @router.post("/api/councils/{ae_id}/pay-tables/recalc-dates")
    def api_pay_recalc(
        ae_id: str,
        request: PayTableRecalcDatesRequest | None = Body(default=None),
    ) -> dict[str, Any]:
        return service().recalc_pay_table_dates(ae_id, request)

    @router.post("/api/councils/{ae_id}/pay-tables/suggest-effective-dates")
    def api_suggest_effective_dates(ae_id: str, request: SuggestDatesRequest) -> dict[str, Any]:
        return service().suggest_effective_dates(ae_id, request)

    @router.post("/api/councils/{ae_id}/pay-tables/review-hints")
    def api_pay_table_review_hints(ae_id: str, request: ReviewHintsRequest) -> dict[str, Any]:
        return service().pay_table_review_hints(ae_id, request)

    return router


def _missing_workspace_dependency(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("AgreementWorkspaceService dependency not configured for this route group")


def _workspace_service_from_pay_table_deps(
    agreement_dependencies: AgreementExtractionDependenciesFactory,
    pay_table_dependencies: PayTableWorkflowDependenciesFactory,
) -> AgreementWorkspaceService:
    return AgreementWorkspaceService(
        clear_review_record=_missing_workspace_dependency,
        list_councils=_missing_workspace_dependency,
        get_council=_missing_workspace_dependency,
        intake_workflow_dependencies=_missing_workspace_dependency,
        sections=(),
        valid_section_statuses=(),
        get_canonical=_missing_workspace_dependency,
        apply_section_status=_missing_workspace_dependency,
        now_iso=_missing_workspace_dependency,
        save_canonical=_missing_workspace_dependency,
        uplift_workflow_dependencies=_missing_workspace_dependency,
        fetch_metadata_for_ae_id=_missing_workspace_dependency,
        find_pdf=_missing_workspace_dependency,
        extract_page_text=_missing_workspace_dependency,
        render_page_png=_missing_workspace_dependency,
        agreement_dependencies=agreement_dependencies,
        pay_table_dependencies=pay_table_dependencies,
        scenario_governance_dependencies=_missing_workspace_dependency,
    )
