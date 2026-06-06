from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from benchmarking_data_factory.workbench.agreement_workspace import AgreementWorkspaceService


@dataclass(frozen=True)
class DocumentRoutesDependencies:
    fetch_metadata_for_ae_id: Callable[[str], dict[str, Any] | None]
    find_pdf: Callable[[str], Path | None]
    extract_page_text: Callable[[str, int], str]
    render_page_png: Callable[[str, int], bytes]


DocumentRoutesDependenciesFactory = Callable[[], DocumentRoutesDependencies]
AgreementWorkspaceServiceFactory = Callable[[], AgreementWorkspaceService]


def build_document_router(dependencies: DocumentRoutesDependenciesFactory) -> APIRouter:
    return build_document_router_for_service(lambda: _workspace_service_from_document_deps(dependencies()))


def build_document_router_for_service(
    workspace: AgreementWorkspaceService | AgreementWorkspaceServiceFactory,
) -> APIRouter:
    router = APIRouter()

    def service() -> AgreementWorkspaceService:
        return workspace() if callable(workspace) else workspace

    @router.get("/api/councils/{ae_id}/fetch-metadata")
    def api_council_fetch_metadata(ae_id: str) -> dict[str, Any]:
        return service().fetch_metadata(ae_id)

    @router.get("/api/councils/{ae_id}/pdf")
    def api_council_pdf(ae_id: str) -> FileResponse:
        pdf_path = service().pdf_path(ae_id)
        headers = {"Content-Disposition": f'inline; filename="{pdf_path.name}"'}
        return FileResponse(pdf_path, media_type="application/pdf", headers=headers)

    @router.get("/api/councils/{ae_id}/pages/{page_num}/text")
    def api_page_text(ae_id: str, page_num: int) -> dict[str, Any]:
        return service().page_text(ae_id, page_num)

    @router.get("/api/councils/{ae_id}/pages/{page_num}/image")
    def api_page_image(ae_id: str, page_num: int) -> Response:
        content = service().page_image(ae_id, page_num)
        return Response(content=content, media_type="image/png")

    return router


def _missing_workspace_dependency(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("AgreementWorkspaceService dependency not configured for this route group")


def _workspace_service_from_document_deps(deps: DocumentRoutesDependencies) -> AgreementWorkspaceService:
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
        fetch_metadata_for_ae_id=deps.fetch_metadata_for_ae_id,
        find_pdf=deps.find_pdf,
        extract_page_text=deps.extract_page_text,
        render_page_png=deps.render_page_png,
        agreement_dependencies=_missing_workspace_dependency,
        pay_table_dependencies=_missing_workspace_dependency,
        scenario_governance_dependencies=_missing_workspace_dependency,
    )
