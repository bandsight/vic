from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from benchmarking_data_factory.workbench.application_core import (
    AnalysisAssetService,
    ReportAssetService,
    ReportExportService,
)
from benchmarking_data_factory.workbench.pay_horizon_explorer import PayHorizonCurveStore


@dataclass(frozen=True)
class AnalysisSpatialRoutesDependencies:
    build_uplift_rules_analysis: Callable[..., dict[str, Any]]
    build_pay_tables_analysis: Callable[..., dict[str, Any]]
    build_end_of_band_dollars_analysis: Callable[..., dict[str, Any]]
    build_review_learning_snapshot: Callable[..., dict[str, Any]]
    load_distribution_point_analysis_asset: Callable[[], dict[str, Any] | None]
    materialize_distribution_point_analysis: Callable[..., dict[str, Any]]
    rebuild_analysis_data_set: Callable[..., dict[str, Any]]
    build_council_geography_payload: Callable[[], dict[str, Any]]
    pay_horizon_curve_store: PayHorizonCurveStore | None = None
    report_assets: ReportAssetService | None = None
    report_exports: ReportExportService | None = None


AnalysisSpatialRoutesDependenciesFactory = Callable[[], AnalysisSpatialRoutesDependencies]


def build_analysis_spatial_router(
    dependencies: AnalysisSpatialRoutesDependenciesFactory,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/analysis/uplift-rules")
    def api_analysis_uplift_rules(include_split_parents: bool = False) -> dict[str, Any]:
        return _analysis_service(dependencies()).uplift_rules(include_split_parents=include_split_parents)

    @router.get("/api/analysis/pay-tables")
    def api_analysis_pay_tables(include_split_parents: bool = False) -> dict[str, Any]:
        return _analysis_service(dependencies()).pay_tables(include_split_parents=include_split_parents)

    @router.get("/api/analysis/end-of-band-dollars")
    def api_analysis_end_of_band_dollars(include_split_parents: bool = False) -> dict[str, Any]:
        return _analysis_service(dependencies()).end_of_band_dollars(include_split_parents=include_split_parents)

    @router.get("/api/analysis/review-learning")
    def api_analysis_review_learning(include_split_parents: bool = False) -> dict[str, Any]:
        return _analysis_service(dependencies()).review_learning(include_split_parents=include_split_parents)

    @router.get("/api/analysis/distribution-point-analysis")
    def api_analysis_distribution_point_analysis(
        include_split_parents: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return _analysis_service(dependencies()).distribution_point_analysis(
            include_split_parents=include_split_parents,
            force_refresh=force_refresh,
        )

    @router.get("/api/analysis/pay-service-horizon-curve/options")
    def api_analysis_pay_service_horizon_curve_options() -> dict[str, Any]:
        store = dependencies().pay_horizon_curve_store
        if store is None:
            raise HTTPException(status_code=503, detail="Pay horizon curve view is not available.")
        return store.options_response()

    @router.get("/api/analysis/pay-service-horizon-curve")
    def api_analysis_pay_service_horizon_curve(
        standard_band: str | None = None,
        effective_from: str | None = None,
        quarter_start: str | None = None,
        cohort_id: str | None = None,
        selected_council_id: str | None = None,
        service_horizon_window_id: str | None = None,
        limit: int = 250,
    ) -> dict[str, Any]:
        store = dependencies().pay_horizon_curve_store
        if store is None:
            raise HTTPException(status_code=503, detail="Pay horizon curve view is not available.")
        return store.response(
            standard_band=standard_band,
            effective_from=effective_from,
            quarter_start=quarter_start,
            cohort_id=cohort_id,
            selected_council_id=selected_council_id,
            service_horizon_window_id=service_horizon_window_id,
            limit=limit,
        )

    @router.post("/api/analysis/distribution-point-analysis/rebuild")
    def api_analysis_distribution_point_analysis_rebuild(
        include_split_parents: bool = False,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "analysis": dependencies().materialize_distribution_point_analysis(
                include_split_parents=include_split_parents
            ),
        }

    @router.get("/api/analysis/distribution-point-analysis/exports")
    def api_analysis_distribution_point_analysis_exports() -> dict[str, Any]:
        report_exports = dependencies().report_exports
        if report_exports is None:
            raise HTTPException(status_code=503, detail="Report export service is not available.")
        return report_exports.catalog()

    @router.post("/api/analysis/distribution-point-analysis/exports")
    def api_analysis_distribution_point_analysis_export(row_limit: int | None = None) -> dict[str, Any]:
        report_exports = dependencies().report_exports
        if report_exports is None:
            raise HTTPException(status_code=503, detail="Report export service is not available.")
        try:
            return {"ok": True, "exports": report_exports.materialize_distribution_point_exports(row_limit=row_limit)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/analysis/distribution-point-analysis/report-asset/status")
    def api_analysis_distribution_point_analysis_report_asset_status(body: dict[str, Any]) -> dict[str, Any]:
        report_assets = dependencies().report_assets
        if report_assets is None:
            raise HTTPException(status_code=503, detail="Report asset service is not available.")
        try:
            manifest = report_assets.update_distribution_point_analysis_status(
                str(body.get("status") or ""),
                operator_note=body.get("operator_note") if isinstance(body.get("operator_note"), str) else None,
            )
            return {
                "ok": True,
                "manifest": manifest,
                "report_asset": report_assets.manifest_summary(manifest),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/analysis/distribution-point-analysis/exports/{format_name}")
    def api_analysis_distribution_point_analysis_export_file(format_name: str) -> FileResponse:
        report_exports = dependencies().report_exports
        if report_exports is None:
            raise HTTPException(status_code=503, detail="Report export service is not available.")
        media_types = {
            "csv": "text/csv",
            "svg": "image/svg+xml",
            "png": "image/png",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "manifest": "application/json",
        }
        try:
            path = report_exports.export_file_path(format_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"Report export has not been generated: {format_name}") from exc
        headers = {"Content-Disposition": f'attachment; filename="{path.name}"'}
        return FileResponse(path, media_type=media_types.get(format_name.lower()), headers=headers)

    @router.post("/api/analysis/{data_set}/rebuild")
    def api_analysis_rebuild(data_set: str, include_split_parents: bool = False) -> dict[str, Any]:
        try:
            return _analysis_service(dependencies()).rebuild(data_set, include_split_parents=include_split_parents)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/spatial/council-geography")
    def api_spatial_council_geography() -> dict[str, Any]:
        return dependencies().build_council_geography_payload()

    return router


def _analysis_service(deps: AnalysisSpatialRoutesDependencies) -> AnalysisAssetService:
    return AnalysisAssetService(
        build_uplift_rules_analysis=deps.build_uplift_rules_analysis,
        build_pay_tables_analysis=deps.build_pay_tables_analysis,
        build_end_of_band_dollars_analysis=deps.build_end_of_band_dollars_analysis,
        build_review_learning_snapshot=deps.build_review_learning_snapshot,
        load_distribution_point_analysis_asset=deps.load_distribution_point_analysis_asset,
        materialize_distribution_point_analysis=deps.materialize_distribution_point_analysis,
        rebuild_analysis_data_set=deps.rebuild_analysis_data_set,
        report_assets=deps.report_assets,
    )
