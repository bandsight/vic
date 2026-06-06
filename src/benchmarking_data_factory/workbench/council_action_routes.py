from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Container

from fastapi import APIRouter

from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module
from benchmarking_data_factory.workbench import uplift_rules_workflow as uplift_rules_workflow_module
from benchmarking_data_factory.workbench.agreement_workspace import AgreementWorkspaceService
from benchmarking_data_factory.workbench.api_models import (
    AcceptUpliftRulesRequest,
    ClearReviewRecordRequest,
    ConfirmSingleCouncilRequest,
    SectionHumanQaRequest,
    SectionStatusRequest,
    SplitCouncilRequest,
    UpdateAcceptedRulesRequest,
)


@dataclass(frozen=True)
class CouncilActionRoutesDependencies:
    clear_review_record: Callable[..., dict[str, Any]]
    list_councils: Callable[[bool], list[dict[str, Any]]]
    get_council: Callable[[str], dict[str, Any]]
    intake_workflow_dependencies: Callable[[], intake_workflow_module.IntakeWorkflowDependencies]
    sections: Container[str]
    valid_section_statuses: Container[str]
    get_canonical: Callable[[str], dict[str, Any]]
    apply_section_status: Callable[..., Any]
    now_iso: Callable[[], str]
    save_canonical: Callable[[str, dict[str, Any]], None]
    uplift_workflow_dependencies: Callable[[], uplift_rules_workflow_module.UpliftRulesWorkflowDependencies]
    scenario_governance_dependencies: Callable[[], scenario_governance_module.ScenarioGovernanceDependencies]


CouncilActionRoutesDependenciesFactory = Callable[[], CouncilActionRoutesDependencies]
AgreementWorkspaceServiceFactory = Callable[[], AgreementWorkspaceService]


def build_council_action_router(
    dependencies: CouncilActionRoutesDependenciesFactory,
) -> APIRouter:
    return build_council_action_router_for_service(lambda: _workspace_service_from_council_deps(dependencies()))


def build_council_action_router_for_service(
    workspace: AgreementWorkspaceService | AgreementWorkspaceServiceFactory,
) -> APIRouter:
    router = APIRouter()

    def service() -> AgreementWorkspaceService:
        return workspace() if callable(workspace) else workspace

    @router.post("/api/councils/{ae_id}/clear-review-record")
    def api_clear_review_record(ae_id: str, request: ClearReviewRecordRequest) -> dict[str, Any]:
        return service().clear_review(
            ae_id,
            reason=request.reason,
            include_related=request.include_related,
        )

    @router.get("/api/councils")
    def api_councils(include_split_parents: bool = False) -> list[dict[str, Any]]:
        return service().councils(include_split_parents)

    @router.get("/api/pipeline/matrix")
    def api_pipeline_matrix() -> list[dict[str, Any]]:
        return service().pipeline_matrix()

    @router.get("/api/councils/{ae_id}")
    def api_council(ae_id: str) -> dict[str, Any]:
        return service().council(ae_id)

    @router.post("/api/councils/{ae_id}/split")
    def api_split_council(ae_id: str, request: SplitCouncilRequest) -> dict[str, Any]:
        return service().split_council(ae_id, request)

    @router.post("/api/councils/{ae_id}/confirm-single")
    def api_confirm_single_council(ae_id: str, request: ConfirmSingleCouncilRequest) -> dict[str, Any]:
        return service().confirm_single_council(ae_id, request)

    @router.delete("/api/councils/{ae_id}/split")
    def api_unsplit_council(ae_id: str) -> dict[str, Any]:
        return service().unsplit_council(ae_id)

    @router.patch("/api/councils/{ae_id}/sections/{section}/status")
    def api_section_status(ae_id: str, section: str, request: SectionStatusRequest) -> dict[str, Any]:
        return service().update_section_status(ae_id, section, request.status)

    @router.patch("/api/councils/{ae_id}/sections/{section}/human-qa")
    def api_section_human_qa(ae_id: str, section: str, request: SectionHumanQaRequest) -> dict[str, Any]:
        return service().update_section_human_qa(
            ae_id,
            section,
            enabled=request.enabled,
            notes=request.notes,
            summary=request.summary,
        )

    @router.post("/api/councils/{ae_id}/uplift-rules/suggest")
    def api_uplift_rules_suggest(ae_id: str, force_refresh: bool = False) -> dict[str, Any]:
        return service().suggest_uplift_rules(ae_id, force_refresh=force_refresh)

    @router.get("/api/councils/{ae_id}/uplift-rules/suggestion")
    def api_uplift_rules_get_suggestion(ae_id: str) -> dict[str, Any]:
        return service().uplift_rule_suggestion(ae_id)

    @router.delete("/api/councils/{ae_id}/uplift-rules/suggestion")
    def api_uplift_rules_discard_suggestion(ae_id: str) -> dict[str, Any]:
        return service().discard_uplift_rule_suggestion(ae_id)

    @router.post("/api/councils/{ae_id}/uplift-rules/accept")
    def api_uplift_rules_accept(ae_id: str, request: AcceptUpliftRulesRequest) -> dict[str, Any]:
        return service().accept_uplift_rules(ae_id, rules=request.rules)

    @router.patch("/api/councils/{ae_id}/uplift-rules/accepted/rules")
    def api_uplift_rules_update_accepted_rules(
        ae_id: str,
        request: UpdateAcceptedRulesRequest,
    ) -> dict[str, Any]:
        return service().update_accepted_uplift_rules(ae_id, request.rules)

    return router


def _missing_workspace_dependency(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("AgreementWorkspaceService dependency not configured for this route group")


def _workspace_service_from_council_deps(deps: CouncilActionRoutesDependencies) -> AgreementWorkspaceService:
    return AgreementWorkspaceService(
        clear_review_record=deps.clear_review_record,
        list_councils=deps.list_councils,
        get_council=deps.get_council,
        intake_workflow_dependencies=deps.intake_workflow_dependencies,
        sections=deps.sections,
        valid_section_statuses=deps.valid_section_statuses,
        get_canonical=deps.get_canonical,
        apply_section_status=deps.apply_section_status,
        now_iso=deps.now_iso,
        save_canonical=deps.save_canonical,
        uplift_workflow_dependencies=deps.uplift_workflow_dependencies,
        fetch_metadata_for_ae_id=_missing_workspace_dependency,
        find_pdf=_missing_workspace_dependency,
        extract_page_text=_missing_workspace_dependency,
        render_page_png=_missing_workspace_dependency,
        agreement_dependencies=_missing_workspace_dependency,
        pay_table_dependencies=_missing_workspace_dependency,
        scenario_governance_dependencies=deps.scenario_governance_dependencies,
    )
