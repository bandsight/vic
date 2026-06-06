from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter

from benchmarking_data_factory.workbench.api_models import LlmConnectionUpdateRequest


@dataclass(frozen=True)
class LlmConnectionRoutesDependencies:
    llm_provider_status: Callable[[], dict[str, Any]]
    llm_connections_status: Callable[[], dict[str, Any]]
    update_llm_connection: Callable[[LlmConnectionUpdateRequest], dict[str, Any]]


LlmConnectionRoutesDependenciesFactory = Callable[[], LlmConnectionRoutesDependencies]


def build_llm_connection_router(
    dependencies: LlmConnectionRoutesDependenciesFactory,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/llm/status")
    def api_llm_status() -> dict[str, Any]:
        return dependencies().llm_provider_status()

    @router.get("/api/connections")
    def api_connections() -> dict[str, Any]:
        return dependencies().llm_connections_status()

    @router.post("/api/connections/llm")
    def api_update_llm_connection(request: LlmConnectionUpdateRequest) -> dict[str, Any]:
        return dependencies().update_llm_connection(request)

    return router
