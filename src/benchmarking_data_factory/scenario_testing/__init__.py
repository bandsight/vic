"""Scenario testing subsystem — read-only comparison of uplift rules vs pay tables."""
from benchmarking_data_factory.scenario_testing.engine import run_scenarios  # noqa: F401
from benchmarking_data_factory.scenario_testing.schema import (  # noqa: F401
    CellDelta,
    ScenarioResult,
)

__all__ = ["run_scenarios", "ScenarioResult", "CellDelta"]
