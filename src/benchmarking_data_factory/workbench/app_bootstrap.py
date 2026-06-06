from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.responses import HTMLResponse

from benchmarking_data_factory.workbench import agent_routes as agent_routes_module
from benchmarking_data_factory.workbench import analysis_spatial_routes as analysis_spatial_routes_module
from benchmarking_data_factory.workbench import agreement_pay_table_routes as agreement_pay_table_routes_module
from benchmarking_data_factory.workbench import council_action_routes as council_action_routes_module
from benchmarking_data_factory.workbench import document_routes as document_routes_module
from benchmarking_data_factory.workbench import intake_audit_reference_routes as intake_audit_reference_routes_module
from benchmarking_data_factory.workbench import llm_connection_routes as llm_connection_routes_module
from benchmarking_data_factory.workbench import wiki_routes as wiki_routes_module
from benchmarking_data_factory.workbench.application_core import build_workbench_services
from benchmarking_data_factory.workbench.app_factory import create_workbench_app
from benchmarking_data_factory.workbench.scenario_governance_routes import build_scenario_governance_router_for_service


def compute_asset_version(static_dir: Path, asset_files: list[str]) -> str:
    mtimes = []
    for name in asset_files:
        path = static_dir / name
        if path.exists():
            mtimes.append(int(path.stat().st_mtime))
    return str(max(mtimes)) if mtimes else "0"


def root_response(ctx: Any) -> HTMLResponse:
    html = (ctx.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{ASSET_VERSION}}", ctx.compute_asset_version())
    return HTMLResponse(content=html, media_type="text/html")


def create_bootstrapped_app(ctx: Any):
    app = create_workbench_app(static_dir=ctx.STATIC_DIR)
    services = build_workbench_services(ctx, app)
    app.state.workbench_services = services
    app.get("/", response_class=HTMLResponse)(ctx.root)
    app.include_router(
        intake_audit_reference_routes_module.build_intake_audit_reference_router(
            ctx._intake_audit_reference_routes_dependencies
        )
    )
    app.include_router(llm_connection_routes_module.build_llm_connection_router(ctx._llm_connection_routes_dependencies))
    app.include_router(analysis_spatial_routes_module.build_analysis_spatial_router(ctx._analysis_spatial_routes_dependencies))
    app.include_router(council_action_routes_module.build_council_action_router_for_service(services.agreement_workspace))
    app.include_router(document_routes_module.build_document_router_for_service(services.agreement_workspace))
    app.include_router(
        agreement_pay_table_routes_module.build_agreement_pay_table_router_for_service(services.agreement_workspace)
    )
    app.include_router(build_scenario_governance_router_for_service(services.governance_events))
    app.include_router(wiki_routes_module.build_wiki_router_for_service(services.wiki_layer))
    app.include_router(agent_routes_module.build_agent_router_for_service(services.agent_discovery))
    return app
