from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter

from benchmarking_data_factory.workbench import intake_workflow as intake_workflow_module
from benchmarking_data_factory.workbench.job_intake import (
    accumulate_checked_jobs_from_snapshot,
    job_pipeline_stage1_payload,
    job_intake_endpoint_resolution_preview,
    load_checked_job_accumulator,
    load_job_intake_snapshot,
    refresh_checked_job_accumulator,
    refresh_job_intake_snapshot,
    job_intake_scrape_preview,
    job_intake_secondary_preview,
    job_intake_wide_fetch_preview,
)
from benchmarking_data_factory.workbench.application_core import IntakeService
from benchmarking_data_factory.workbench.api_models import IntakeDecisionRequest


@dataclass(frozen=True)
class IntakeAuditReferenceRoutesDependencies:
    load_canonical_councils: Callable[[], list[dict[str, str]]]
    canonical_council_reference_payload: Callable[[], dict[str, Any]]
    council_master_reference_payload: Callable[[], dict[str, Any]]
    council_job_source_registry_payload: Callable[[], dict[str, Any]]
    build_intake_quality_summary: Callable[..., dict[str, Any]]
    build_pay_tables_analysis: Callable[..., dict[str, Any]]
    build_intake_candidate_rows: Callable[[], list[dict[str, Any]]]
    build_council_audit_report: Callable[[str], dict[str, Any]]
    fetch_fair_work_registry_intake: Callable[..., dict[str, Any]]
    load_intake_decisions: Callable[[], dict[str, dict[str, Any]]]
    intake_workflow_dependencies: Callable[[], intake_workflow_module.IntakeWorkflowDependencies]


IntakeAuditReferenceRoutesDependenciesFactory = Callable[
    [],
    IntakeAuditReferenceRoutesDependencies,
]


def build_intake_audit_reference_router(
    dependencies: IntakeAuditReferenceRoutesDependenciesFactory,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/reference/canonical-councils")
    def api_reference_canonical_councils() -> list[dict[str, str]]:
        return _intake_service(dependencies()).active_canonical_councils()

    @router.get("/api/reference/councils")
    def api_reference_councils() -> dict[str, Any]:
        return _intake_service(dependencies()).canonical_council_reference()

    @router.get("/api/reference/council-master")
    def api_reference_council_master() -> dict[str, Any]:
        return _intake_service(dependencies()).council_master_reference()

    @router.get("/api/reference/council-job-sources")
    def api_reference_council_job_sources() -> dict[str, Any]:
        return _intake_service(dependencies()).council_job_source_registry()

    @router.get("/api/job-intake/scrape-preview")
    def api_job_intake_scrape_preview(
        source_limit: int = 0,
        job_limit: int = 500,
        timeout: int = 8,
        enrich_pay_tables: bool = True,
        enrich_details: bool = True,
        detail_job_limit: int = 1000,
        enrich_attachments: bool = False,
        attachment_job_limit: int = 1000,
        resolve_missing_documents: bool = True,
    ) -> dict[str, Any]:
        pay_table_rows: list[dict[str, Any]] = []
        if enrich_pay_tables:
            try:
                pay_table_rows = dependencies().build_pay_tables_analysis().get("rows") or []
            except Exception:
                pay_table_rows = []
        return job_intake_scrape_preview(
            source_limit=max(0, min(source_limit, 79)),
            job_limit=max(1, min(job_limit, 1000)),
            timeout=max(3, min(timeout, 20)),
            max_workers=8,
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=max(0, min(detail_job_limit, 1000)),
            enrich_attachments=enrich_attachments,
            attachment_job_limit=max(0, min(attachment_job_limit, 1000)),
            resolve_missing_documents=resolve_missing_documents,
        )

    @router.get("/api/job-intake/wide-fetch-preview")
    def api_job_intake_wide_fetch_preview(
        source_limit: int = 0,
        job_limit: int = 0,
        timeout: int = 8,
        enrich_pay_tables: bool = True,
        enrich_details: bool = True,
        detail_job_limit: int = 1000,
        enrich_attachments: bool = False,
        attachment_job_limit: int = 1000,
        resolve_missing_documents: bool = True,
        candidate_limit_per_council: int = 12,
        candidate_priority_limit: int = 3,
    ) -> dict[str, Any]:
        pay_table_rows: list[dict[str, Any]] = []
        if enrich_pay_tables:
            try:
                pay_table_rows = dependencies().build_pay_tables_analysis().get("rows") or []
            except Exception:
                pay_table_rows = []
        return job_intake_wide_fetch_preview(
            source_limit=max(0, min(source_limit, 5000)),
            job_limit=max(0, min(job_limit, 10000)),
            timeout=max(3, min(timeout, 20)),
            max_workers=8,
            registry_payload=dependencies().council_job_source_registry_payload(),
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=max(0, min(detail_job_limit, 3000)),
            enrich_attachments=enrich_attachments,
            attachment_job_limit=max(0, min(attachment_job_limit, 3000)),
            resolve_missing_documents=resolve_missing_documents,
            candidate_limit_per_council=max(0, min(candidate_limit_per_council, 50)),
            candidate_priority_limit=max(1, min(candidate_priority_limit, 4)),
        )

    @router.get("/api/job-intake/snapshot")
    def api_job_intake_snapshot() -> dict[str, Any]:
        return load_job_intake_snapshot()

    @router.get("/api/job-intake/accumulator")
    def api_job_intake_accumulator() -> dict[str, Any]:
        return load_checked_job_accumulator(
            registry_payload=dependencies().council_job_source_registry_payload(),
        )

    @router.post("/api/job-intake/accumulator/ingest-snapshot")
    def api_job_intake_accumulator_ingest_snapshot() -> dict[str, Any]:
        return accumulate_checked_jobs_from_snapshot(
            registry_payload=dependencies().council_job_source_registry_payload(),
        )

    @router.post("/api/job-intake/accumulator/refresh")
    def api_job_intake_accumulator_refresh(
        source_limit: int = 0,
        job_limit: int = 0,
        timeout: int = 8,
        enrich_pay_tables: bool = True,
        enrich_details: bool = True,
        detail_job_limit: int = 1000,
        enrich_attachments: bool = False,
        attachment_job_limit: int = 1000,
        resolve_missing_documents: bool = True,
        include_secondary: bool = True,
        secondary_job_limit: int = 0,
        wide_fetch: bool = True,
        candidate_limit_per_council: int = 12,
        candidate_priority_limit: int = 3,
    ) -> dict[str, Any]:
        pay_table_rows: list[dict[str, Any]] = []
        if enrich_pay_tables:
            try:
                pay_table_rows = dependencies().build_pay_tables_analysis().get("rows") or []
            except Exception:
                pay_table_rows = []
        return refresh_checked_job_accumulator(
            source_limit=max(0, min(source_limit, 5000)),
            job_limit=max(0, min(job_limit, 5000)),
            timeout=max(3, min(timeout, 20)),
            max_workers=8,
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=max(0, min(detail_job_limit, 2000)),
            enrich_attachments=enrich_attachments,
            attachment_job_limit=max(0, min(attachment_job_limit, 2000)),
            resolve_missing_documents=resolve_missing_documents,
            include_secondary=include_secondary,
            secondary_job_limit=max(0, min(secondary_job_limit, 5000)),
            wide_fetch=wide_fetch,
            candidate_limit_per_council=max(0, min(candidate_limit_per_council, 50)),
            candidate_priority_limit=max(1, min(candidate_priority_limit, 4)),
            registry_payload=dependencies().council_job_source_registry_payload(),
        )

    @router.post("/api/job-intake/refresh")
    def api_job_intake_refresh(
        source_limit: int = 0,
        job_limit: int = 500,
        timeout: int = 8,
        enrich_pay_tables: bool = True,
        enrich_details: bool = True,
        detail_job_limit: int = 1000,
        enrich_attachments: bool = False,
        attachment_job_limit: int = 1000,
        resolve_missing_documents: bool = True,
    ) -> dict[str, Any]:
        pay_table_rows: list[dict[str, Any]] = []
        if enrich_pay_tables:
            try:
                pay_table_rows = dependencies().build_pay_tables_analysis().get("rows") or []
            except Exception:
                pay_table_rows = []
        return refresh_job_intake_snapshot(
            source_limit=max(0, min(source_limit, 79)),
            job_limit=max(1, min(job_limit, 1000)),
            timeout=max(3, min(timeout, 20)),
            max_workers=8,
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=max(0, min(detail_job_limit, 1000)),
            enrich_attachments=enrich_attachments,
            attachment_job_limit=max(0, min(attachment_job_limit, 1000)),
            resolve_missing_documents=resolve_missing_documents,
        )

    @router.get("/api/job-pipeline/stage1")
    def api_job_pipeline_stage1() -> dict[str, Any]:
        return job_pipeline_stage1_payload()

    @router.get("/api/job-intake/endpoint-resolution-preview")
    def api_job_intake_endpoint_resolution_preview(
        candidate_limit: int = 500,
        job_limit: int = 100,
        timeout: int = 6,
    ) -> dict[str, Any]:
        return job_intake_endpoint_resolution_preview(
            candidate_limit=max(0, min(candidate_limit, 3000)),
            job_limit=max(1, min(job_limit, 200)),
            timeout=max(3, min(timeout, 12)),
        )

    @router.get("/api/job-intake/secondary-preview")
    def api_job_intake_secondary_preview(
        source_limit: int = 0,
        job_limit: int = 200,
        timeout: int = 8,
        enrich_pay_tables: bool = True,
        enrich_details: bool = True,
        detail_job_limit: int = 250,
        expand_sector_board_council_pages: bool = True,
    ) -> dict[str, Any]:
        pay_table_rows: list[dict[str, Any]] = []
        if enrich_pay_tables:
            try:
                pay_table_rows = dependencies().build_pay_tables_analysis().get("rows") or []
            except Exception:
                pay_table_rows = []
        return job_intake_secondary_preview(
            source_limit=max(0, min(source_limit, 200)),
            job_limit=max(1, min(job_limit, 5000)),
            timeout=max(3, min(timeout, 20)),
            max_workers=6,
            registry_payload=dependencies().council_job_source_registry_payload(),
            pay_table_rows=pay_table_rows,
            enrich_details=enrich_details,
            detail_job_limit=max(0, min(detail_job_limit, 1000)),
            expand_sector_board_council_pages=expand_sector_board_council_pages,
        )

    @router.get("/api/reference/canonical-councils/count")
    def api_canonical_council_count() -> dict[str, int]:
        return _intake_service(dependencies()).canonical_council_count()

    @router.get("/api/canonical-councils")
    def api_canonical_councils() -> list[dict[str, str]]:
        return _intake_service(dependencies()).active_canonical_councils()

    @router.get("/api/intake/quality")
    def api_intake_quality(force_refresh: bool = False) -> dict[str, Any]:
        return _intake_service(dependencies()).intake_quality(force_refresh=force_refresh)

    @router.get("/api/intake/candidates")
    def api_intake_candidates() -> list[dict[str, Any]]:
        return _intake_service(dependencies()).intake_candidates()

    @router.get("/api/audit/councils/{council_name}")
    def api_council_audit(council_name: str) -> dict[str, Any]:
        return _intake_service(dependencies()).council_audit(council_name)

    @router.post("/api/intake/fetch-registry")
    def api_intake_fetch_registry(
        force_refresh: bool = True,
        fetch_pdfs: bool = False,
        pdf_limit: int | None = None,
    ) -> dict[str, Any]:
        return _intake_service(dependencies()).fetch_registry(
            force_refresh=force_refresh,
            fetch_pdfs=fetch_pdfs,
            pdf_limit=pdf_limit,
        )

    @router.get("/api/intake/decisions")
    def api_intake_decisions() -> dict[str, dict[str, Any]]:
        return _intake_service(dependencies()).intake_decisions()

    @router.post("/api/intake/candidates/{ae_id}/decision")
    def api_intake_decision(ae_id: str, request: IntakeDecisionRequest) -> dict[str, Any]:
        return _intake_service(dependencies()).record_candidate_decision(
            ae_id,
            status=request.status,
            reason=request.reason,
            notes=request.notes,
        )

    @router.post("/api/intake/candidates/{ae_id}/freeze")
    def api_intake_freeze_candidate(ae_id: str, force_refresh: bool = False) -> dict[str, Any]:
        return _intake_service(dependencies()).freeze_candidate(
            ae_id,
            force_refresh=force_refresh,
        )

    return router


def _intake_service(deps: IntakeAuditReferenceRoutesDependencies) -> IntakeService:
    return IntakeService(
        load_canonical_councils=deps.load_canonical_councils,
        canonical_council_reference_payload=deps.canonical_council_reference_payload,
        council_master_reference_payload=deps.council_master_reference_payload,
        council_job_source_registry_payload=deps.council_job_source_registry_payload,
        build_intake_quality_summary=deps.build_intake_quality_summary,
        build_intake_candidate_rows=deps.build_intake_candidate_rows,
        build_council_audit_report=deps.build_council_audit_report,
        fetch_fair_work_registry_intake=deps.fetch_fair_work_registry_intake,
        load_intake_decisions=deps.load_intake_decisions,
        intake_workflow_dependencies=deps.intake_workflow_dependencies,
    )
