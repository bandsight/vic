from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body

from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module
from benchmarking_data_factory.workbench.application_core import GovernanceEventService
from benchmarking_data_factory.workbench.api_models import (
    ConstructTableRequest,
    PromoteRequest,
    RateCapConfirmRequest,
    ScenarioNoteRequest,
    ScenarioRequest,
    UnwindRequest,
)


ScenarioGovernanceDependenciesFactory = Callable[
    [],
    scenario_governance_module.ScenarioGovernanceDependencies,
]
GovernanceEventServiceFactory = Callable[[], GovernanceEventService]


def build_scenario_governance_router(
    dependencies: ScenarioGovernanceDependenciesFactory,
) -> APIRouter:
    return build_scenario_governance_router_for_service(
        lambda: GovernanceEventService(scenario_governance_dependencies=dependencies)
    )


def build_scenario_governance_router_for_service(
    governance: GovernanceEventService | GovernanceEventServiceFactory,
) -> APIRouter:
    router = APIRouter()

    def service() -> GovernanceEventService:
        return governance() if callable(governance) else governance

    @router.post("/api/councils/{ae_id}/uplift-rules/scenarios")
    async def api_uplift_rules_scenarios(
        ae_id: str,
        body: ScenarioRequest = Body(default_factory=ScenarioRequest),
    ) -> dict[str, Any]:
        return service().run_uplift_rule_scenarios(ae_id, body)

    @router.get("/api/councils/{ae_id}/uplift-rules/scenarios/overrides")
    async def api_get_uplift_rule_scenario_overrides(ae_id: str) -> dict[str, Any]:
        return service().scenario_overrides(ae_id)

    @router.post("/api/councils/{ae_id}/uplift-rules/scenarios/overrides")
    async def api_post_uplift_rule_scenario_overrides(
        ae_id: str,
        body: ScenarioRequest = Body(default_factory=ScenarioRequest),
    ) -> dict[str, Any]:
        return service().save_scenario_overrides(ae_id, body)

    @router.post("/api/councils/{ae_id}/uplift-rules/scenarios/note")
    async def api_post_uplift_rule_scenario_note(
        ae_id: str,
        body: ScenarioNoteRequest,
    ) -> dict[str, Any]:
        return service().save_scenario_note(ae_id, body)

    @router.delete("/api/councils/{ae_id}/uplift-rules/scenarios/overrides")
    async def api_delete_uplift_rule_scenario_overrides(ae_id: str) -> dict[str, Any]:
        return service().clear_scenario_overrides(ae_id)

    @router.post("/api/councils/{ae_id}/pay-tables/construct")
    async def api_construct_pay_table(ae_id: str, body: ConstructTableRequest) -> dict[str, Any]:
        return service().construct_pay_table(ae_id, body)

    @router.post("/api/councils/{ae_id}/governed-set/promote")
    async def api_governed_set_promote(ae_id: str, body: PromoteRequest) -> dict[str, Any]:
        return service().promote_governed_set(ae_id, body)

    @router.post("/api/councils/{ae_id}/governed-set/unwind")
    async def api_governed_set_unwind(ae_id: str, body: UnwindRequest) -> dict[str, Any]:
        return service().unwind_governed_set(ae_id, body)

    @router.get("/api/councils/{ae_id}/governed-set")
    async def api_governed_set_get(ae_id: str) -> dict[str, Any]:
        return service().governed_set(ae_id)

    @router.get("/api/rate-caps/status")
    async def api_get_rate_cap_status() -> dict[str, Any]:
        return service().rate_cap_status()

    @router.post("/api/rate-caps/confirm")
    async def api_post_rate_cap_confirm(body: RateCapConfirmRequest) -> dict[str, Any]:
        return service().confirm_rate_cap(body)

    return router
