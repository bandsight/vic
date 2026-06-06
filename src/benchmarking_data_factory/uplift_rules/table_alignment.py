"""Rule/table binding checks for uplift extraction QA.

These checks keep coherent table mismatches upstream. If a published table
movement conflicts with the accepted uplift rule in a clean pattern, the issue
is usually extraction binding: wrong table family, wrong date anchor, or missing
rule context. Scenario QA should not silently accept that as a downstream table
choice.
"""
from __future__ import annotations

from typing import Any


def build_rule_table_alignment_issues(
    canonical: dict[str, Any],
    *,
    lga_short_name: str | None = None,
) -> list[dict[str, Any]]:
    from benchmarking_data_factory.scenario_testing.engine import run_scenarios

    issues: list[dict[str, Any]] = []
    try:
        scenarios = run_scenarios(canonical, overrides=None, lga_short_name=lga_short_name)
    except Exception:
        return issues

    for scenario in scenarios:
        decision = scenario.decision_recommendation or {}
        if decision.get("action") != "needs_rule_extraction_review":
            continue
        period = scenario.period_effective_from
        rule_quantum = scenario.rule_quantum or decision.get("rule_quantum")
        implied = decision.get("implied_weekly_increase")
        mechanised = decision.get("mechanised_weekly_increase")
        message = (
            f"{period}: published table movement conflicts with the accepted uplift rule. "
            "Review uplift-rule extraction context and table/date binding before scenario QA."
        )
        if mechanised is not None and implied is not None:
            message += f" Rule implies ${mechanised}/week; table pattern implies ${implied}/week."
        issues.append({
            "level": "error",
            "code": "uplift_rule_table_binding_conflict",
            "period_effective_from": period,
            "message": message,
            "basis": decision.get("basis"),
            "rule_id": scenario.rule_id,
            "rule_quantum": rule_quantum,
            "table_names": list(scenario.table_names),
            "affected_cells": decision.get("affected_cells"),
            "covered_cells": decision.get("covered_cells"),
            "variance_ratio": decision.get("variance_ratio"),
            "mechanised_weekly_increase": mechanised,
            "implied_weekly_increase": implied,
            "consistent_offset": decision.get("consistent_offset"),
        })
    return issues


def record_rule_table_alignment_issues(
    canonical: dict[str, Any],
    *,
    lga_short_name: str | None = None,
) -> list[dict[str, Any]]:
    issues = build_rule_table_alignment_issues(canonical, lga_short_name=lga_short_name)
    sections = canonical.setdefault("sections", {})
    uplift_section = sections.setdefault("uplift_rules", {})
    data = uplift_section.get("data") if isinstance(uplift_section.get("data"), dict) else {}
    data["table_alignment_issues"] = issues
    uplift_section["data"] = data
    return issues


__all__ = ["build_rule_table_alignment_issues", "record_rule_table_alignment_issues"]
