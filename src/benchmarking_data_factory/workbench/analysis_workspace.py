from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable

from benchmarking_data_factory.workbench.analysis_rule_normalisation import (
    _ANALYSIS_DELTA_TAIL_RE,
    _ANALYSIS_INVERTED_DELTA_RE,
    _ANALYSIS_PCT_RE,
    _ANALYSIS_RATE_CAP_HEAD_RE,
    _ANALYSIS_RATE_CAP_TAIL_RE,
    _analysis_normalise_uplift_rule,
    _analysis_number,
    _analysis_pct_tokens,
    _analysis_rule_has_rate_cap,
    _normalised_governed_rule_for_response,
    _rate_cap_resolution_for_rule,
)
from benchmarking_data_factory.workbench.analysis_pay_candidate_quality import (
    _ALLOWANCE_FALSE_POSITIVE_RE,
    _APPENDIX_FALSE_POSITIVE_RE,
    _SPECIALIST_FALSE_POSITIVE_RE,
    _STANDARD_PAY_TABLE_RE,
    _candidate_pay_pages_from_canonical,
    _candidate_quality_recommendations,
    _normalise_page_list,
    _pay_candidate_page_signal as _pay_candidate_page_signal_impl,
    _short_text_excerpt,
    _table_source_pages,
    _used_pay_pages_from_canonical,
    build_pay_candidate_quality as _build_pay_candidate_quality_impl,
)
from benchmarking_data_factory.workbench.analysis_distribution_points import (
    _analysis_iso_date as _analysis_iso_date_impl,
    _distribution_band,
    _distribution_level,
    _distribution_level_sort_key,
    _distribution_quarters_for_row as _distribution_quarters_for_row_impl,
    _distribution_source_basis,
    _distribution_source_rows,
    _quarter_start_iso as _quarter_start_iso_impl,
    _shift_quarter_start_iso,
    _source_pages_from_rows,
    build_distribution_point_analysis as _build_distribution_point_analysis_impl,
)
from benchmarking_data_factory.workbench.analysis_end_of_band import (
    build_end_of_band_dollars_analysis as _build_end_of_band_dollars_analysis_impl,
)


@dataclass(frozen=True)
class AnalysisWorkspaceDependencies:
    load_registry: Callable[[], dict[str, str]]
    load_multi_council_decisions: Callable[[], dict[str, dict[str, Any]]]
    split_ae_ids_from_decisions: Callable[[dict[str, dict[str, Any]]], set[str]]
    list_pdfs: Callable[[], list[str]]
    get_canonical: Callable[[str], dict[str, Any]]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any]]
    resolve_canonical_lga_short_name: Callable[..., str | None]
    scenario_cell_overrides_for_period: Callable[[str, str], dict[str, Any] | None]
    save_canonical: Callable[[str, dict[str, Any]], None]
    now_iso: Callable[[], str]
    analysis_geography_fields: Callable[[Any], dict[str, Any]]
    standard_band_level_metadata: Callable[[dict[str, Any]], dict[str, Any]]
    parse_iso_date: Callable[[Any], str | None]
    root_path: Callable[[], Path]
    distribution_point_analysis_json: Callable[[], Path]
    extract_page_text: Callable[[str, int], str] | None = None


_ACTIVE_DEPS: ContextVar[AnalysisWorkspaceDependencies | None] = ContextVar(
    "analysis_workspace_dependencies",
    default=None,
)


class _AnalysisDependencyScope:
    def __init__(self, deps: AnalysisWorkspaceDependencies):
        self.deps = deps
        self.token: Any = None

    def __enter__(self) -> None:
        self.token = _ACTIVE_DEPS.set(self.deps)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.token is not None:
            _ACTIVE_DEPS.reset(self.token)


def analysis_workspace_dependencies(deps: AnalysisWorkspaceDependencies) -> _AnalysisDependencyScope:
    return _AnalysisDependencyScope(deps)


def _deps() -> AnalysisWorkspaceDependencies:
    deps = _ACTIVE_DEPS.get()
    if deps is None:
        raise RuntimeError("Analysis workspace dependencies are not configured")
    return deps


def load_registry() -> dict[str, str]:
    return _deps().load_registry()


def load_multi_council_decisions() -> dict[str, dict[str, Any]]:
    return _deps().load_multi_council_decisions()


def split_ae_ids_from_decisions(decisions: dict[str, dict[str, Any]]) -> set[str]:
    return _deps().split_ae_ids_from_decisions(decisions)


def list_pdfs() -> list[str]:
    return _deps().list_pdfs()


def get_canonical(ae_id: str) -> dict[str, Any]:
    return _deps().get_canonical(ae_id)


def fetch_metadata_for_ae_id(ae_id: str, decisions: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    return _deps().fetch_metadata_for_ae_id(ae_id, decisions)


def resolve_canonical_lga_short_name(
    ae_id: str,
    fetch_metadata: dict[str, Any] | None,
    decisions: dict[str, dict[str, Any]] | None,
) -> str | None:
    return _deps().resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)


def _scenario_cell_overrides_for_period(ae_id: str, effective_from: str) -> dict[str, Any] | None:
    return _deps().scenario_cell_overrides_for_period(ae_id, effective_from)


def save_canonical(ae_id: str, canonical: dict[str, Any]) -> None:
    _deps().save_canonical(ae_id, canonical)


def now_iso() -> str:
    return _deps().now_iso()


def analysis_geography_fields(lga: Any) -> dict[str, Any]:
    return _deps().analysis_geography_fields(lga)


def standard_band_level_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return _deps().standard_band_level_metadata(row)


def parse_iso_date(value: Any) -> str | None:
    return _deps().parse_iso_date(value)


def root_path() -> Path:
    return _deps().root_path()


def distribution_point_analysis_json() -> Path:
    return _deps().distribution_point_analysis_json()


def analysis_extract_page_text(ae_id: str, page_num: int) -> str:
    extractor = _deps().extract_page_text
    if extractor is None:
        return ""
    try:
        return extractor(ae_id, page_num)
    except Exception:
        return ""


def analysis_visible_ae_ids(include_split_parents: bool = False) -> list[str]:
    registry = load_registry()
    decisions = load_multi_council_decisions()
    split_ae_ids = split_ae_ids_from_decisions(decisions)
    ae_ids = sorted(set(registry.keys()) | set(list_pdfs()) | split_ae_ids)
    hidden_parents = {
        decision_ae_id
        for decision_ae_id, decision in decisions.items()
        if decision.get("is_multi")
        and not include_split_parents
        and (decision.get("split_files") or any(split_id.startswith(f"{decision_ae_id}__") for split_id in split_ae_ids))
    }
    return [ae_id for ae_id in ae_ids if ae_id not in hidden_parents]


def normalised_governed_payload_for_response(
    governed: dict[str, Any] | None,
    *,
    lga_short_name: str | None = None,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(governed or {"periods": []}))
    periods = payload.get("periods")
    if not isinstance(periods, list):
        payload["periods"] = []
        return payload
    for period in periods:
        if not isinstance(period, dict):
            continue
        rule = period.get("uplift_rule")
        if isinstance(rule, dict) and rule:
            period["uplift_rule"] = _normalised_governed_rule_for_response(
                rule,
                lga_short_name=lga_short_name,
                effective_from=period.get("effective_from") or rule.get("effective_date"),
            )
    return payload


def _governed_data_for_rebuild(canonical: dict[str, Any]) -> dict[str, Any]:
    sections = canonical.setdefault("sections", {})
    uplifts = sections.setdefault("uplifts", {})
    data = uplifts.get("data")
    if not isinstance(data, dict):
        data = {"periods": []}
        uplifts["data"] = data
    periods = data.get("periods")
    if not isinstance(periods, list):
        data["periods"] = []
    return data


def _clear_governed_entity_slots(canonical: dict[str, Any], data_set: str) -> dict[str, int]:
    data = _governed_data_for_rebuild(canonical)
    periods = [p for p in (data.get("periods") or []) if isinstance(p, dict)]
    cleared = 0
    for period in periods:
        if data_set == "pay_tables":
            if period.get("pay_table") is not None or period.get("pay_table_governed_at") is not None:
                cleared += 1
            period["pay_table"] = None
            period["pay_table_governed_at"] = None
        elif data_set == "uplift_rules":
            if period.get("uplift_rule") is not None or period.get("uplift_rule_governed_at") is not None:
                cleared += 1
            period["uplift_rule"] = None
            period["uplift_rule_governed_at"] = None
    retained = [
        period
        for period in periods
        if period.get("pay_table") is not None or period.get("uplift_rule") is not None
    ]
    data["periods"] = retained
    return {"cleared": cleared, "empty_periods_removed": len(periods) - len(retained)}


def _upstream_pay_table_dates(canonical: dict[str, Any]) -> list[str]:
    dates = {
        str(table.get("effective_from"))
        for table in (((canonical.get("sections") or {}).get("pay_tables") or {}).get("tables") or [])
        if isinstance(table, dict) and table.get("effective_from")
    }
    return sorted(dates)


def _upstream_uplift_rule_dates(canonical: dict[str, Any], rules: list[dict[str, Any]]) -> list[str]:
    dates = {
        str(rule.get("effective_date"))
        for rule in rules
        if isinstance(rule, dict) and rule.get("effective_date")
    }
    return sorted(dates)


def rebuild_analysis_data_set(data_set: str, *, include_split_parents: bool = False) -> dict[str, Any]:
    if data_set not in {"pay_tables", "uplift_rules", "end_of_band_dollars"}:
        raise ValueError("data_set must be pay_tables, uplift_rules, or end_of_band_dollars")

    if data_set == "end_of_band_dollars":
        visible_ae_ids = analysis_visible_ae_ids(include_split_parents=include_split_parents)
        analysis = build_end_of_band_dollars_analysis(include_split_parents=include_split_parents)
        return {
            "data_set": data_set,
            "rebuilt_at": now_iso(),
            "agreements_scanned": len(visible_ae_ids),
            "derived_rows": len(analysis.get("rows") or []),
            "agreements_with_end_of_band_cash": (analysis.get("summary") or {}).get("agreements_with_end_of_band_cash", 0),
            "mutates_canonical": False,
        }

    from benchmarking_data_factory.governed_set import (  # noqa: PLC0415
        extract_uplift_rules,
        promote_pay_table,
        promote_uplift_rule,
        select_uplift_rule_for_period,
    )

    decisions = load_multi_council_decisions()
    visible_ae_ids = analysis_visible_ae_ids(include_split_parents=include_split_parents)
    summary: dict[str, Any] = {
        "data_set": data_set,
        "rebuilt_at": now_iso(),
        "agreements_scanned": len(visible_ae_ids),
        "agreements_changed": 0,
        "slots_cleared": 0,
        "empty_periods_removed": 0,
        "candidates": 0,
        "promoted": 0,
        "skipped": 0,
        "errors": [],
    }

    for ae_id in visible_ae_ids:
        canonical = get_canonical(ae_id)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id, decisions)
        lga_short_name = resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
        clear_result = _clear_governed_entity_slots(canonical, data_set)
        summary["slots_cleared"] += clear_result["cleared"]
        summary["empty_periods_removed"] += clear_result["empty_periods_removed"]

        changed = bool(clear_result["cleared"] or clear_result["empty_periods_removed"])
        promoted = 0
        rules = extract_uplift_rules(canonical) if data_set == "uplift_rules" else []
        candidate_dates = (
            _upstream_pay_table_dates(canonical)
            if data_set == "pay_tables"
            else _upstream_uplift_rule_dates(canonical, rules)
        )
        summary["candidates"] += len(candidate_dates)

        for effective_from in candidate_dates:
            try:
                if data_set == "pay_tables":
                    promote_pay_table(
                        canonical,
                        effective_from,
                        cell_overrides=_scenario_cell_overrides_for_period(ae_id, effective_from),
                    )
                else:
                    match = select_uplift_rule_for_period(
                        rules,
                        effective_from,
                        lga_short_name=lga_short_name,
                    )
                    resolution = (
                        _rate_cap_resolution_for_rule(
                            match,
                            lga_short_name=lga_short_name,
                            effective_from=effective_from,
                        )
                        if isinstance(match, dict)
                        else None
                    )
                    promote_uplift_rule(
                        canonical,
                        effective_from,
                        rate_cap_value=(resolution or {}).get("raw_rate_cap"),
                        rate_cap_resolution=resolution,
                        lga_short_name=lga_short_name,
                    )
                promoted += 1
            except ValueError as exc:
                summary["skipped"] += 1
                if len(summary["errors"]) < 25:
                    summary["errors"].append({
                        "ae_id": ae_id,
                        "effective_from": effective_from,
                        "message": str(exc),
                    })

        if changed or promoted:
            save_canonical(ae_id, canonical)
            summary["agreements_changed"] += 1
        summary["promoted"] += promoted

    return summary


def build_uplift_rules_analysis(include_split_parents: bool = False) -> dict[str, Any]:
    registry = load_registry()
    decisions = load_multi_council_decisions()
    visible_ae_ids = analysis_visible_ae_ids(include_split_parents=include_split_parents)
    rows: list[dict[str, Any]] = []
    governed_period_count = 0
    periods_without_rule = 0
    agreements_with_periods: set[str] = set()

    for ae_id in visible_ae_ids:
        canonical = get_canonical(ae_id)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id, decisions)
        lga = resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
        periods = (
            ((canonical.get("sections") or {}).get("uplifts") or {})
            .get("data") or {}
        ).get("periods") or []
        if periods:
            agreements_with_periods.add(ae_id)
        for index, period in enumerate(periods):
            if not isinstance(period, dict):
                continue
            governed_period_count += 1
            rule = period.get("uplift_rule")
            if not isinstance(rule, dict) or not rule:
                periods_without_rule += 1
                continue
            effective_from = period.get("effective_from") or rule.get("effective_date")
            if effective_from is not None:
                effective_from = str(effective_from)
            rule = _normalised_governed_rule_for_response(
                rule,
                lga_short_name=lga,
                effective_from=effective_from,
            )
            normalised_components = rule.get("normalised_components") or _analysis_normalise_uplift_rule(rule)
            geography_fields = analysis_geography_fields(lga)
            rows.append({
                "ae_id": ae_id,
                "agreement_name": canonical.get("source_name") or registry.get(ae_id) or ae_id,
                "canonical_lga_short_name": lga,
                "effective_from": effective_from,
                "period_index": index,
                "pct_component": _analysis_number(rule.get("pct_component")),
                "dollar_component": _analysis_number(rule.get("dollar_component")),
                "dollar_basis": rule.get("dollar_basis"),
                "rate_cap_component": _analysis_number(rule.get("rate_cap_component")),
                "pct_of_rate_cap": _analysis_number(rule.get("pct_of_rate_cap")),
                "floor_dollar": _analysis_number(rule.get("floor_dollar")),
                "floor_pct": _analysis_number(rule.get("floor_pct")),
                "pattern_archetype": rule.get("pattern_archetype") or "unknown",
                "pattern_variant": rule.get("pattern_variant") or rule.get("quantum") or "",
                "source_rule_id": rule.get("source_rule_id"),
                "source_quantum_type": rule.get("source_quantum_type"),
                "governed_at": period.get("uplift_rule_governed_at"),
                "has_rate_cap": _analysis_rule_has_rate_cap(rule),
                "normalised_components": normalised_components,
                "internal_pct_component": normalised_components["internal_pct_component"],
                "pct_floor_component": normalised_components["pct_floor_component"],
                "dollar_floor_component": normalised_components["dollar_floor_component"],
                "external_cap_pct": normalised_components["external_cap_pct"],
                "external_cap_share": normalised_components["external_cap_share"],
                "external_cap_delta_pct": normalised_components["external_cap_delta_pct"],
                "external_formula_pct": normalised_components["external_formula_pct"],
                "resolved_pct": normalised_components["resolved_pct"],
                "resolved_basis": normalised_components["resolved_basis"],
                **geography_fields,
            })

    rows.sort(key=lambda item: (
        str(item.get("effective_from") or "9999-99-99"),
        str(item.get("canonical_lga_short_name") or item.get("agreement_name") or "").lower(),
        str(item.get("ae_id") or ""),
    ))

    pattern_counts: dict[str, int] = {}
    for row in rows:
        pattern = str(row.get("pattern_archetype") or "unknown")
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    dates = [
        str(row.get("effective_from"))
        for row in rows
        if isinstance(row.get("effective_from"), str) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(row.get("effective_from")))
    ]
    agreements_with_rules = {str(row["ae_id"]) for row in rows}
    return {
        "set_id": "set_1_uplift_rules",
        "label": "Uplift Rules",
        "description": "First-class governed uplift rule entity set promoted from validated agreement periods.",
        "summary": {
            "agreements_scanned": len(visible_ae_ids),
            "agreements_with_governed_periods": len(agreements_with_periods),
            "agreements_with_uplift_rules": len(agreements_with_rules),
            "governed_periods": governed_period_count,
            "rules": len(rows),
            "periods_without_rule": periods_without_rule,
            "rate_cap_rules": sum(1 for row in rows if row.get("has_rate_cap")),
            "floor_rules": sum(1 for row in rows if row.get("dollar_floor_component") is not None or row.get("pct_floor_component") is not None),
            "earliest_effective_from": min(dates) if dates else None,
            "latest_effective_from": max(dates) if dates else None,
        },
        "patterns": patterns,
        "rows": rows,
    }


def _analysis_sort_piece(value: Any) -> str:
    if value is None:
        return ""
    return str(value).lower()


def _pay_candidate_page_signal(ae_id: str, page: int) -> dict[str, Any]:
    return _pay_candidate_page_signal_impl(ae_id, page, extract_page_text=analysis_extract_page_text)


def _build_pay_candidate_quality(
    visible_ae_ids: list[str],
    registry: dict[str, str],
    decisions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return _build_pay_candidate_quality_impl(
        visible_ae_ids,
        registry,
        decisions,
        get_canonical=get_canonical,
        fetch_metadata_for_ae_id=fetch_metadata_for_ae_id,
        resolve_canonical_lga_short_name=resolve_canonical_lga_short_name,
        extract_page_text=analysis_extract_page_text,
    )


def build_pay_tables_analysis(include_split_parents: bool = False) -> dict[str, Any]:
    registry = load_registry()
    decisions = load_multi_council_decisions()
    visible_ae_ids = analysis_visible_ae_ids(include_split_parents=include_split_parents)
    rows: list[dict[str, Any]] = []
    governed_period_count = 0
    periods_without_pay_table = 0
    governed_table_count = 0
    non_weekly_rows_skipped = 0
    agreements_with_tables: set[str] = set()

    for ae_id in visible_ae_ids:
        canonical = get_canonical(ae_id)
        fetch_metadata = fetch_metadata_for_ae_id(ae_id, decisions)
        lga = resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
        periods = (
            ((canonical.get("sections") or {}).get("uplifts") or {})
            .get("data") or {}
        ).get("periods") or []
        agreement_name = canonical.get("source_name") or registry.get(ae_id) or ae_id
        for period_index, period in enumerate(periods):
            if not isinstance(period, dict):
                continue
            governed_period_count += 1
            table = period.get("pay_table")
            if not isinstance(table, dict) or not table:
                periods_without_pay_table += 1
                continue
            governed_table_count += 1
            agreements_with_tables.add(ae_id)
            effective_from = period.get("effective_from") or table.get("effective_from")
            if effective_from is not None:
                effective_from = str(effective_from)
            table_rows = table.get("rows") or []
            geography_fields = analysis_geography_fields(lga)
            for row_index, row in enumerate(table_rows):
                if not isinstance(row, dict):
                    continue
                weekly_rate = _analysis_number(row.get("weekly_rate"))
                if weekly_rate is None:
                    non_weekly_rows_skipped += 1
                    continue
                banding_fields = standard_band_level_metadata(row)
                standard_band = row.get("standard_band") or banding_fields.get("standard_band")
                standard_level = row.get("standard_level") or banding_fields.get("standard_level")
                classification_key = row.get("classification_key") or banding_fields.get("classification_key")
                classification_label = row.get("classification_label") or banding_fields.get("classification_label")
                classification_sort = row.get("classification_sort") or banding_fields.get("classification_sort")
                weekly_rate_basis = row.get("weekly_rate_basis") or "weekly_rate"
                rows.append({
                    "ae_id": ae_id,
                    "agreement_name": agreement_name,
                    "canonical_lga_short_name": lga,
                    "effective_from": effective_from,
                    "to_date": table.get("to_date"),
                    "period_index": period_index,
                    "row_index": row_index,
                    "table_title": table.get("table_title"),
                    "source_page": table.get("source_page"),
                    "source_pages": table.get("source_pages"),
                    "source_clause": table.get("source_clause"),
                    "effective_from_note": table.get("effective_from_note"),
                    "rate_kind": "weekly",
                    "governed_at": period.get("pay_table_governed_at"),
                    "band": row.get("band"),
                    "level": row.get("level"),
                    "standard_band": standard_band,
                    "standard_level": standard_level,
                    "classification_key": classification_key,
                    "classification_label": classification_label,
                    "classification_sort": classification_sort,
                    "title": row.get("title"),
                    "weekly_rate": weekly_rate,
                    "weekly_rate_basis": weekly_rate_basis,
                    "notes": row.get("notes"),
                    **geography_fields,
                })

    rows.sort(key=lambda item: (
        str(item.get("effective_from") or "9999-99-99"),
        _analysis_sort_piece(item.get("canonical_lga_short_name") or item.get("agreement_name")),
        int(item.get("classification_sort") or 999999),
        _analysis_sort_piece(item.get("standard_band") or item.get("band")),
        _analysis_sort_piece(item.get("standard_level") or item.get("level")),
        int(item.get("row_index") or 0),
    ))

    weekly_basis_counts: dict[str, int] = {}
    for row in rows:
        kind = str(row.get("weekly_rate_basis") or "weekly_rate")
        weekly_basis_counts[kind] = weekly_basis_counts.get(kind, 0) + 1
    patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in sorted(weekly_basis_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    dates = [
        str(row.get("effective_from"))
        for row in rows
        if isinstance(row.get("effective_from"), str) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(row.get("effective_from")))
    ]
    candidate_quality = _build_pay_candidate_quality(visible_ae_ids, registry, decisions)
    return {
        "set_id": "set_2_pay_tables",
        "label": "Pay Tables",
        "description": "Flattened governed weekly pay-table row entity set promoted from accepted evidence.",
        "summary": {
            "agreements_scanned": len(visible_ae_ids),
            "agreements_with_governed_pay_tables": len(agreements_with_tables),
            "governed_periods": governed_period_count,
            "tables": governed_table_count,
            "rows": len(rows),
            "periods_without_pay_table": periods_without_pay_table,
            "weekly_rate_rows": len(rows),
            "non_weekly_rows_skipped": non_weekly_rows_skipped,
            "weekly_rate_basis_counts": weekly_basis_counts,
            "earliest_effective_from": min(dates) if dates else None,
            "latest_effective_from": max(dates) if dates else None,
        },
        "patterns": patterns,
        "candidate_quality": candidate_quality,
        "rows": rows,
    }


def build_end_of_band_dollars_analysis(include_split_parents: bool = False) -> dict[str, Any]:
    return _build_end_of_band_dollars_analysis_impl(
        visible_ae_ids=analysis_visible_ae_ids(include_split_parents=include_split_parents),
        load_registry=load_registry,
        load_multi_council_decisions=load_multi_council_decisions,
        get_canonical=get_canonical,
        fetch_metadata_for_ae_id=fetch_metadata_for_ae_id,
        resolve_canonical_lga_short_name=resolve_canonical_lga_short_name,
        analysis_geography_fields=analysis_geography_fields,
        root_path=root_path,
    )


def _analysis_iso_date(value: Any) -> str | None:
    return _analysis_iso_date_impl(value, parse_iso_date=parse_iso_date)


def _quarter_start_iso(value: Any) -> str | None:
    return _quarter_start_iso_impl(value, parse_iso_date=parse_iso_date)


def _distribution_quarters_for_row(row: dict[str, Any]) -> list[str]:
    return _distribution_quarters_for_row_impl(row, parse_iso_date=parse_iso_date)


def build_distribution_point_analysis(
    include_split_parents: bool = False,
    pay_tables_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_distribution_point_analysis_impl(
        include_split_parents=include_split_parents,
        pay_tables_analysis=pay_tables_analysis,
        build_pay_tables_analysis=build_pay_tables_analysis,
        parse_iso_date=parse_iso_date,
        now_iso=now_iso,
    )


def materialize_distribution_point_analysis(
    include_split_parents: bool = False,
    pay_tables_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_distribution_point_analysis(
        include_split_parents=include_split_parents,
        pay_tables_analysis=pay_tables_analysis,
    )
    distribution_point_analysis_json().parent.mkdir(parents=True, exist_ok=True)
    try:
        asset_path = str(distribution_point_analysis_json().relative_to(root_path()))
    except ValueError:
        asset_path = str(distribution_point_analysis_json())
    payload["asset"] = {
        "path": asset_path,
        "materialized_at": now_iso(),
    }
    distribution_point_analysis_json().write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def load_distribution_point_analysis_asset() -> dict[str, Any] | None:
    if not distribution_point_analysis_json().exists():
        return None
    try:
        return json.loads(distribution_point_analysis_json().read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
