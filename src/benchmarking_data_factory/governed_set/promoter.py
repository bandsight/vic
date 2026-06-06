"""Promote scenario-validated assets from upstream canonical into the Governed Set."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from .classifier import classify_rule
from benchmarking_data_factory.scenario_testing.normalise import (
    is_standard_band_level_row,
    row_to_weekly,
    standard_band_level_metadata,
    standard_cell_key,
)


_NON_WEEKLY_RATE_FIELDS = {"annual_rate", "fortnightly_rate", "hourly_rate"}
_WEEKLY_RATE_KINDS = {"weekly", "weekly_rate"}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _ensure_governed_shape(canonical: dict[str, Any]) -> dict[str, Any]:
    sections = canonical.setdefault("sections", {})
    uplifts = sections.setdefault("uplifts", {})
    data = uplifts.get("data")
    if not isinstance(data, dict):
        data = {"periods": []}
        uplifts["data"] = data
    data.setdefault("periods", [])
    return data


def _get_or_create_period(governed: dict[str, Any], effective_from: str) -> dict[str, Any]:
    for period in governed["periods"]:
        if period.get("effective_from") == effective_from:
            return period
    period = {
        "effective_from": effective_from,
        "pay_table": None,
        "pay_table_governed_at": None,
        "uplift_rule": None,
        "uplift_rule_governed_at": None,
    }
    governed["periods"].append(period)
    governed["periods"].sort(key=lambda p: p.get("effective_from") or "")
    return period


def extract_uplift_rules(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the active upstream uplift rule list from canonical, if present."""
    ur = (canonical.get("sections", {}).get("uplift_rules", {}) or {}).get("data") or {}
    for path in (("accepted", "document", "rules"), ("accepted", "rules"), ("suggestion", "document", "rules"), ("rules",)):
        cursor: Any = ur
        for key in path:
            if not isinstance(cursor, dict):
                cursor = None
                break
            cursor = cursor.get(key)
        if isinstance(cursor, list) and cursor:
            return [r for r in cursor if isinstance(r, dict)]
    return []


def _normalise_scope_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()


def _rule_scope_text(rule: dict[str, Any]) -> str:
    return _normalise_scope_text(" ".join(
        str(rule.get(key) or "")
        for key in ("period_label", "timing_clause", "quantum_resolution")
    ))


def _filter_rules_by_lga(rules: list[dict[str, Any]], lga_short_name: str | None) -> list[dict[str, Any]]:
    if not lga_short_name:
        return rules
    needle = _normalise_scope_text(lga_short_name)
    if not needle:
        return rules
    matched = [rule for rule in rules if needle in _rule_scope_text(rule)]
    return matched if matched else rules


def select_uplift_rule_for_period(
    rules: list[dict[str, Any]],
    effective_from: str,
    *,
    lga_short_name: str | None = None,
) -> dict[str, Any] | None:
    """Pick the rule for a period, respecting council-specific multi-employer rows."""
    scoped_rules = _filter_rules_by_lga(rules, lga_short_name)
    return next((r for r in scoped_rules if r.get("effective_date") == effective_from), None)


def _normalised_rate_kind(table: dict[str, Any]) -> str:
    return str(table.get("rate_kind") or "").strip().lower()


def _weekly_rate_from_row(row: dict[str, Any], table_rate_kind: str) -> Any:
    weekly_rate = row.get("weekly_rate")
    if weekly_rate is not None:
        return weekly_rate
    if table_rate_kind in _WEEKLY_RATE_KINDS and row.get("rate") is not None:
        return row.get("rate")
    derived = row_to_weekly(row)
    return round(derived, 2) if derived is not None else None


def _weekly_rate_basis(row: dict[str, Any], table_rate_kind: str) -> str | None:
    if row.get("weekly_rate") is not None:
        return "weekly_rate"
    if table_rate_kind in _WEEKLY_RATE_KINDS and row.get("rate") is not None:
        return "rate"
    if row.get("annual_rate") is not None and row_to_weekly(row) is not None:
        return "annual_rate/52"
    if row.get("fortnightly_rate") is not None and row_to_weekly(row) is not None:
        return "fortnightly_rate/2"
    return None


def _has_weekly_values(table: dict[str, Any]) -> bool:
    table_rate_kind = _normalised_rate_kind(table)
    return any(
        isinstance(row, dict)
        and is_standard_band_level_row(row)
        and _weekly_rate_from_row(row, table_rate_kind) is not None
        for row in (table.get("rows") or [])
    )


def _has_explicit_weekly_values(table: dict[str, Any]) -> bool:
    table_rate_kind = _normalised_rate_kind(table)
    return any(
        isinstance(row, dict)
        and is_standard_band_level_row(row)
        and (row.get("weekly_rate") is not None or (table_rate_kind in _WEEKLY_RATE_KINDS and row.get("rate") is not None))
        for row in (table.get("rows") or [])
    )


def _cell_override(cell_overrides: dict[str, Any] | None, cell: tuple[str, str]) -> dict[str, Any] | None:
    if not cell_overrides:
        return None
    override = cell_overrides.get(f"{cell[0]}:{cell[1]}")
    return override if isinstance(override, dict) else None


def _weekly_only_snapshot(
    table: dict[str, Any],
    cell_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    table_rate_kind = _normalised_rate_kind(table)
    snapshot = {key: value for key, value in table.items() if key != "rows"}
    snapshot["rate_kind"] = "weekly"
    rows: list[dict[str, Any]] = []
    seen_standard_cells: set[tuple[str, str]] = set()
    duplicate_standard_rows_count = 0
    override_counts = {"accept": 0, "deleted": 0, "use_computed": 0}
    source_rows = [row for row in table.get("rows") or [] if isinstance(row, dict)]
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        if not is_standard_band_level_row(row):
            continue
        cell = standard_cell_key(row)
        if cell is None:
            continue
        if cell in seen_standard_cells:
            duplicate_standard_rows_count += 1
            continue
        seen_standard_cells.add(cell)
        override = _cell_override(cell_overrides, cell)
        override_action = str((override or {}).get("action") or "").strip()
        if override_action == "deleted":
            override_counts["deleted"] += 1
            continue
        weekly_rate = _weekly_rate_from_row(row, table_rate_kind)
        if weekly_rate is None:
            continue
        basis = _weekly_rate_basis(row, table_rate_kind)
        source_weekly_rate = weekly_rate
        if override_action == "use_computed" and override and override.get("weekly") is not None:
            weekly_rate = round(float(override["weekly"]), 2)
            basis = "scenario_override_use_computed"
            override_counts["use_computed"] += 1
        elif override_action == "accept":
            override_counts["accept"] += 1
        governed_row = dict(row)
        governed_row["weekly_rate"] = weekly_rate
        governed_row.update(standard_band_level_metadata(row))
        if basis and basis not in {"weekly_rate", "rate"}:
            governed_row["weekly_rate_basis"] = basis
        if override_action in {"accept", "use_computed"}:
            governed_row["scenario_override_action"] = override_action
        if override_action == "use_computed" and source_weekly_rate != weekly_rate:
            governed_row["source_weekly_rate"] = source_weekly_rate
        governed_row.pop("rate", None)
        for field in _NON_WEEKLY_RATE_FIELDS:
            governed_row.pop(field, None)
        rows.append(governed_row)
    snapshot["rows"] = rows
    snapshot["row_scope"] = "standard_band_level"
    snapshot["source_rows_count"] = len(source_rows)
    snapshot["standard_rows_count"] = len(rows)
    snapshot["duplicate_standard_rows_count"] = duplicate_standard_rows_count
    snapshot["excluded_rows_count"] = len(source_rows) - len(rows)
    snapshot["scenario_override_counts"] = {
        key: value for key, value in override_counts.items() if value
    }
    return snapshot


def promote_pay_table(
    canonical: dict[str, Any],
    effective_from: str,
    *,
    cell_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Copy weekly pay-table values for the given effective_from into governed set.

    Raises ValueError if no matching table with weekly values exists upstream.
    Returns the governed period dict after promotion.
    """
    tables = (canonical.get("sections", {}).get("pay_tables", {}) or {}).get("tables") or []
    matches = [t for t in tables if isinstance(t, dict) and t.get("effective_from") == effective_from]
    match = next((t for t in matches if _has_explicit_weekly_values(t)), None)
    if match is None:
        match = next((t for t in matches if _has_weekly_values(t)), None)
    if match is None:
        raise ValueError(f"No upstream pay table with weekly, annual, or fortnightly rates for effective_from={effective_from}")
    governed = _ensure_governed_shape(canonical)
    period = _get_or_create_period(governed, effective_from)
    snapshot = _weekly_only_snapshot(match, cell_overrides=cell_overrides)
    period["pay_table"] = snapshot
    period["pay_table_governed_at"] = _iso_now()
    return period


def promote_uplift_rule(
    canonical: dict[str, Any],
    effective_from: str,
    rate_cap_value: float | None = None,
    rate_cap_resolution: dict[str, Any] | None = None,
    lga_short_name: str | None = None,
) -> dict[str, Any]:
    """Classify and promote the upstream uplift rule for the given effective_from.

    Raises ValueError if no matching rule exists upstream.
    Returns the governed period dict after promotion.
    """
    rules = extract_uplift_rules(canonical)
    match = select_uplift_rule_for_period(rules, effective_from, lga_short_name=lga_short_name)
    if match is None:
        raise ValueError(f"No upstream uplift rule for effective_date={effective_from}")

    payload = classify_rule(match, rate_cap_value=rate_cap_value, rate_cap_resolution=rate_cap_resolution)
    governed = _ensure_governed_shape(canonical)
    period = _get_or_create_period(governed, effective_from)
    period["uplift_rule"] = payload
    period["uplift_rule_governed_at"] = _iso_now()
    return period
