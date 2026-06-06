from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timedelta
from typing import Any


def _apply_needs_review(
    results: tuple,
    saved_at: str | None,
) -> list:
    """Flip table_resolved to needs_review when a dependency was confirmed after saved_at."""
    if not saved_at:
        return list(results)
    out = []
    for result in results:
        if result.status != "table_resolved" or not result.external_deps:
            out.append(result)
            continue
        flip = False
        newest_confirmed = None
        for dep in result.external_deps:
            if dep.dep_status == "confirmed" and dep.confirmed_at and dep.confirmed_at > saved_at:
                flip = True
                if newest_confirmed is None or dep.confirmed_at > newest_confirmed:
                    newest_confirmed = dep.confirmed_at
        if flip:
            out.append(replace(
                result,
                status="needs_review",
                sub_status="rate_cap_confirmed_since_save",
                reason=f"[dep confirmed {newest_confirmed} after save at {saved_at}] " + result.reason,
            ))
        else:
            out.append(result)
    return out


def _scenario_compact_result(result: Any) -> dict[str, Any]:
    payload = {
        "period_effective_from": getattr(result, "period_effective_from", ""),
        "period_label": getattr(result, "period_label", ""),
        "status": getattr(result, "status", ""),
        "sub_status": getattr(result, "sub_status", ""),
        "reason": getattr(result, "reason", ""),
        "rule_id": getattr(result, "rule_id", None),
        "rule_quantum": getattr(result, "rule_quantum", None),
    }
    recommendation = getattr(result, "decision_recommendation", None)
    if recommendation:
        payload["decision_recommendation"] = recommendation
    return payload


def _is_future_iso_date(value: str | None) -> bool:
    if not value:
        return False
    try:
        return date.fromisoformat(value) > date.today()
    except ValueError:
        return False


def _future_trigger_date(period_effective_from: str | None) -> str:
    review_date = date.today() + timedelta(days=30)
    if period_effective_from:
        try:
            effective_date = date.fromisoformat(period_effective_from)
        except ValueError:
            effective_date = None
        if effective_date and effective_date > review_date:
            return effective_date.isoformat()
    return review_date.isoformat()


def _scenario_future_trigger(result: Any) -> dict[str, Any] | None:
    status = getattr(result, "status", "")
    sub_status = getattr(result, "sub_status", "")
    period_effective_from = getattr(result, "period_effective_from", "")
    external_deps = tuple(getattr(result, "external_deps", ()) or ())
    has_pending_external_dep = any(getattr(dep, "dep_status", "") == "pending" for dep in external_deps)

    if status == "table_resolved" and (sub_status == "rate_cap_pending" or has_pending_external_dep):
        return {
            **_scenario_compact_result(result),
            "trigger_type": "pending_external_dependency",
            "trigger_date": _future_trigger_date(period_effective_from),
            "external_deps": [asdict(dep) for dep in external_deps],
        }

    if status == "awaiting_input" and _is_future_iso_date(period_effective_from):
        return {
            **_scenario_compact_result(result),
            "trigger_type": "future_external_input",
            "trigger_date": _future_trigger_date(period_effective_from),
            "external_deps": [asdict(dep) for dep in external_deps],
        }

    return None


def _scenario_section_resolution(results: list[Any], run_at: str) -> tuple[str, dict[str, Any]]:
    summary: dict[str, int] = {}
    future_triggers: list[dict[str, Any]] = []
    blocking_results: list[dict[str, Any]] = []
    hard_review_statuses = {"needs_attention", "awaiting_input", "needs_review"}
    complete_statuses = {"baseline", "consistent", "table_resolved"}

    def source_table_only(result: Any) -> bool:
        if getattr(result, "status", "") != "needs_attention":
            return False
        reason = str(getattr(result, "reason", "") or "").lower()
        return (
            "table exists for this period but no uplift rule covers it" in reason
            or "rule did not cover any cells" in reason
        )

    for result in results:
        status = getattr(result, "status", "")
        summary[status] = summary.get(status, 0) + 1
        future_trigger = _scenario_future_trigger(result)
        if future_trigger:
            future_triggers.append(future_trigger)
            continue
        if status in complete_statuses:
            continue
        if source_table_only(result):
            continue
        blocking_results.append(_scenario_compact_result(result))

    if not results:
        section_status = "not_started"
    elif any(item.get("status") in hard_review_statuses for item in blocking_results):
        section_status = "flagged"
    elif blocking_results:
        section_status = "in_progress"
    else:
        section_status = "done"

    data = {
        "last_run_at": run_at,
        "status_summary": summary,
        "future_triggers": future_triggers,
        "blocking_results": blocking_results,
    }
    return section_status, data
