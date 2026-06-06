from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from benchmarking_data_factory.workbench.application_core import AgentDiscoveryService, build_workbench_services


def build_agent_router(ctx: Any, app: Any) -> APIRouter:
    return build_agent_router_for_service(build_workbench_services(ctx, app).agent_discovery)


def build_agent_router_for_service(discovery: AgentDiscoveryService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/agent/status")
    def api_agent_status() -> dict[str, Any]:
        return discovery.status()

    @router.get("/api/agent/catalog")
    def api_agent_catalog() -> dict[str, Any]:
        return discovery.catalog()

    @router.get("/api/agent/datasets")
    def api_agent_datasets() -> dict[str, Any]:
        return discovery.datasets_catalog()

    @router.get("/api/agent/actions")
    def api_agent_actions() -> dict[str, Any]:
        return discovery.actions()

    @router.get("/api/agent/io")
    def api_agent_io() -> dict[str, Any]:
        return discovery.io()

    return router
