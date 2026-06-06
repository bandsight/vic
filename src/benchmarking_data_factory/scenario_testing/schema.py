"""Scenario testing schema — read-only dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

ScenarioStatus = Literal[
    "consistent",
    "needs_attention",
    "awaiting_input",
    "baseline",
    "blocked",
    "table_resolved",
    "needs_review",
]

ScenarioSubStatus = Literal[
    "conflict",
    "table_only",
    "pending",
    "partial_rule",
    "ambiguous_rule",
    "no_weekly_equivalent",
    "rate_cap_pending",
    "rate_cap_confirmed_since_save",
    # empty string allowed for statuses that don't have a sub
]


@dataclass(frozen=True)
class CellDelta:
    band: str
    level: str
    prior_weekly: Optional[float]
    computed_weekly: Optional[float]
    actual_weekly: Optional[float]
    abs_delta: Optional[float]
    pct_delta: Optional[float]
    within_tolerance: bool
    override_action: Optional[str] = None
    recommended_action: Optional[str] = None
    recommendation_reason: Optional[str] = None
    recommendation_basis: Optional[str] = None


@dataclass(frozen=True)
class ExternalDep:
    dep_key: str
    dep_kind: str
    financial_year: str
    dep_status: str
    confirmed_at: Optional[str] = None
    raw_rate_cap: Optional[float] = None
    effective_rate: Optional[float] = None
    resolution_note: Optional[str] = None


@dataclass(frozen=True)
class ScenarioResult:
    ae_id: str
    period_effective_from: str
    period_label: str
    status: ScenarioStatus
    sub_status: str
    reason: str
    rule_id: Optional[str]
    rule_quantum: Optional[str]
    prior_period_effective_from: Optional[str]
    table_names: tuple[str, ...]
    cell_deltas: tuple[CellDelta, ...]
    external_deps: tuple[ExternalDep, ...] = field(default_factory=tuple)
    decision_recommendation: Optional[dict[str, Any]] = None
