"""Table projection - construct a synthetic pay table by applying an uplift rule to a prior period."""
from __future__ import annotations

from typing import Optional

from benchmarking_data_factory.scenario_testing.engine import _apply_rule, _find_rule_for_period, _parse_iso_date
from benchmarking_data_factory.scenario_testing.normalise import is_standard_band_level_row, row_to_weekly, standard_cell_key


def extract_rules_for_projection(uplift_rules_section: dict) -> tuple:
    """Extract accepted rules. Priority (first non-empty wins):
    1. data.accepted.document.rules
    2. data.accepted.rules
    3. data.suggestion.document.rules
    """
    data = uplift_rules_section.get("data") or {}
    accepted = data.get("accepted") or {}
    if isinstance(accepted, dict):
        doc = accepted.get("document") or {}
        if isinstance(doc, dict):
            r = doc.get("rules")
            if r:
                return tuple(r)
        r = accepted.get("rules")
        if r:
            return tuple(r)
    suggestion = data.get("suggestion") or {}
    if isinstance(suggestion, dict):
        doc = suggestion.get("document") or {}
        if isinstance(doc, dict):
            r = doc.get("rules")
            if r:
                return tuple(r)
    return ()


def construct_table(
    canonical: dict,
    effective_date: str,
    lga_short_name: str | None = None,
) -> dict | None:
    """Construct a projected pay table for effective_date.

    Returns a table dict ready to append to canonical["sections"]["pay_tables"]["tables"],
    or None if construction is not possible.
    """
    sections = canonical.get("sections", {}) or {}
    pt_section = sections.get("pay_tables", {}) or {}
    ur_section = sections.get("uplift_rules", {}) or {}

    tables = pt_section.get("tables") or []
    rules = extract_rules_for_projection(ur_section)
    if not rules:
        return None

    rule = _find_rule_for_period(rules, effective_date)
    if rule is None:
        return None

    qtype = rule.get("quantum_type", "unknown")
    if qtype in ("table_embedded", "unknown"):
        return None

    if qtype == "conditional":
        from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (
            RateCapResolutionError,
            classify_rate_cap_mode,
            date_to_financial_year,
            get_year_status_row,
            resolve_effective_rate,
        )

        quantum_str = rule.get("quantum") or ""
        external_ref = rule.get("quantum_external_ref") or ""
        cap_mode = classify_rate_cap_mode(quantum_str, external_ref)
        if cap_mode == "no_rate_cap_ref":
            return None
        try:
            fy = date_to_financial_year(effective_date)
        except RateCapResolutionError:
            return None
        year_row = get_year_status_row(fy)
        year_status = year_row.get("resolution_status") if year_row else "unknown"
        if year_status != "confirmed" or not lga_short_name:
            return None
        try:
            resolution = resolve_effective_rate(lga_short_name, fy, quantum_str, external_ref)
        except RateCapResolutionError:
            return None
        if resolution is None:
            return None
        rule = dict(rule)
        rule["quantum_type"] = "percentage"
        rule["quantum"] = f"{resolution['effective_rate']:.4f}%"
        rule["_rate_cap_resolution"] = resolution
        rule.pop("quantum_external_ref", None)

    eff_date_parsed = _parse_iso_date(effective_date)
    if eff_date_parsed is None:
        return None

    prior_table: Optional[dict] = None
    prior_date = None
    for t in tables:
        t_date = _parse_iso_date(t.get("effective_from"))
        if t_date is None or t_date >= eff_date_parsed:
            continue
        if prior_date is None or t_date > prior_date:
            prior_table = t
            prior_date = t_date
    if prior_table is None:
        return None

    prior_by_cell: dict[tuple[str, str], float] = {}
    prior_rows_by_key: dict[tuple[str, str], dict] = {}
    for row in prior_table.get("rows") or []:
        if not is_standard_band_level_row(row):
            continue
        key = standard_cell_key(row)
        if key is None:
            continue
        weekly = row_to_weekly(row)
        if weekly is None:
            continue
        if key in prior_by_cell:
            continue
        prior_by_cell[key] = weekly
        prior_rows_by_key[key] = row
    if not prior_by_cell:
        return None

    computed_by_cell = _apply_rule(rule, prior_by_cell)
    if not computed_by_cell:
        return None

    rows = []
    for key in sorted(computed_by_cell.keys()):
        prior_row = prior_rows_by_key.get(key, {})
        rows.append({
            "band": prior_row.get("band"),
            "level": prior_row.get("level"),
            "title": prior_row.get("title"),
            "weekly_rate": round(computed_by_cell[key], 2),
            "annual_rate": None,
            "hourly_rate": None,
            "fortnightly_rate": None,
            "notes": None,
        })

    return {
        "table_title": f"Projected rates ({effective_date})",
        "source_page": None,
        "source_clause": None,
        "effective_from": effective_date,
        "rate_kind": "weekly",
        "rows": rows,
        "provenance": "constructed",
        "to_date": None,
    }
