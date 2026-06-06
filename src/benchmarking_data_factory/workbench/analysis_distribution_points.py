from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
import re
from typing import Any, Callable

from benchmarking_data_factory.workbench.analysis_rule_normalisation import _analysis_number


def _analysis_sort_piece(value: Any) -> str:
    if value is None:
        return ""
    return str(value).lower()


def _analysis_iso_date(value: Any, *, parse_iso_date: Callable[[Any], str | None]) -> str | None:
    return parse_iso_date(value)


def _quarter_start_iso(value: Any, *, parse_iso_date: Callable[[Any], str | None]) -> str | None:
    iso = _analysis_iso_date(value, parse_iso_date=parse_iso_date)
    if iso is None:
        return None
    parsed = date.fromisoformat(iso)
    month = ((parsed.month - 1) // 3) * 3 + 1
    return f"{parsed.year:04d}-{month:02d}-01"


def _shift_quarter_start_iso(quarter_start: str, offset_quarters: int) -> str:
    parsed = date.fromisoformat(quarter_start)
    month_index = (parsed.year * 12) + (parsed.month - 1) + (offset_quarters * 3)
    year = month_index // 12
    month = (month_index % 12) + 1
    return f"{year:04d}-{month:02d}-01"


def _distribution_quarters_for_row(
    row: dict[str, Any],
    *,
    parse_iso_date: Callable[[Any], str | None],
) -> list[str]:
    start = _quarter_start_iso(row.get("effective_from"), parse_iso_date=parse_iso_date)
    if start is None:
        return []
    end = _quarter_start_iso(row.get("to_date"), parse_iso_date=parse_iso_date)
    if end is None or int(end[:4]) >= 2100:
        end = start
    quarters: list[str] = []
    cursor = start
    while cursor <= end:
        quarters.append(cursor)
        cursor = _shift_quarter_start_iso(cursor, 1)
    return quarters


def _distribution_band(row: dict[str, Any]) -> str:
    return str(row.get("standard_band") or row.get("band") or "").strip()


def _distribution_level(row: dict[str, Any]) -> str:
    return str(row.get("standard_level") or row.get("level") or "").strip()


def _distribution_level_sort_key(level: Any, fallback: Any = None) -> tuple[int, str]:
    fallback_number = _analysis_number(fallback)
    if fallback_number is not None:
        return int(fallback_number), str(level or "")
    text = str(level or "").strip()
    if text.isdigit():
        return int(text), text
    match = re.search(r"[A-Za-z]", text)
    if match:
        return ord(match.group(0).upper()) - 64, text
    return 999999, text


def _source_pages_from_rows(rows: list[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for row in rows:
        raw_pages = row.get("source_pages")
        values = raw_pages if isinstance(raw_pages, list) else [raw_pages]
        if row.get("source_page") is not None:
            values.append(row.get("source_page"))
        for value in values:
            try:
                page = int(value)
            except (TypeError, ValueError):
                continue
            if page not in pages:
                pages.append(page)
    return pages


def _distribution_source_basis(rows: list[dict[str, Any]]) -> str:
    titles = " ".join(str(row.get("table_title") or "") for row in rows).lower()
    bases = {str(row.get("weekly_rate_basis") or "weekly_rate") for row in rows}
    if "projected" in titles:
        return "scenario_projection"
    non_standard = sorted(base for base in bases if base != "weekly_rate")
    if non_standard:
        return non_standard[0]
    return "governed_table"


def _distribution_source_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_rows: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (
        _distribution_level_sort_key(_distribution_level(item), item.get("classification_sort")),
        int(item.get("row_index") or 0),
    )):
        source_rows.append({
            "source_row_id": f"{row.get('period_index')}:{row.get('row_index')}",
            "period_index": row.get("period_index"),
            "row_index": row.get("row_index"),
            "level": _distribution_level(row) or None,
            "classification_label": row.get("classification_label"),
            "weekly_rate": row.get("weekly_rate"),
            "weekly_rate_basis": row.get("weekly_rate_basis"),
            "table_title": row.get("table_title"),
        })
    return source_rows


def build_distribution_point_analysis(
    include_split_parents: bool = False,
    pay_tables_analysis: dict[str, Any] | None = None,
    *,
    build_pay_tables_analysis: Callable[..., dict[str, Any]],
    parse_iso_date: Callable[[Any], str | None],
    now_iso: Callable[[], str],
) -> dict[str, Any]:
    pay_analysis = pay_tables_analysis or build_pay_tables_analysis(include_split_parents=include_split_parents)
    pay_rows = [row for row in pay_analysis.get("rows", []) if isinstance(row, dict)]
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for row in pay_rows:
        band = _distribution_band(row)
        weekly_rate = _analysis_number(row.get("weekly_rate"))
        if not band or weekly_rate is None:
            continue
        for quarter_start in _distribution_quarters_for_row(row, parse_iso_date=parse_iso_date):
            key = (str(row.get("ae_id") or ""), quarter_start, band)
            buckets.setdefault(key, []).append({**row, "weekly_rate": weekly_rate})

    raw_points: list[dict[str, Any]] = []
    expected_levels: dict[tuple[str, str], set[str]] = {}

    for (ae_id, quarter_start, band), bucket_rows in buckets.items():
        if not bucket_rows:
            continue
        latest_by_level: dict[str, dict[str, Any]] = {}
        level_counts: Counter[str] = Counter()
        for row in bucket_rows:
            level = _distribution_level(row) or f"row_{row.get('row_index')}"
            level_counts[level] += 1
            existing = latest_by_level.get(level)
            if existing is None or str(row.get("effective_from") or "") >= str(existing.get("effective_from") or ""):
                latest_by_level[level] = row
        level_rows = list(latest_by_level.values())
        if not level_rows:
            continue
        level_rows.sort(key=lambda row: (
            _distribution_level_sort_key(_distribution_level(row), row.get("classification_sort")),
            _analysis_number(row.get("weekly_rate")) or 0.0,
        ))
        min_row = level_rows[0]
        max_row = level_rows[-1]
        min_rate = _analysis_number(min_row.get("weekly_rate"))
        max_rate = _analysis_number(max_row.get("weekly_rate"))
        if min_rate is None or max_rate is None:
            continue
        midpoint_rate = (min_rate + max_rate) / 2
        levels = [_distribution_level(row) for row in level_rows if _distribution_level(row)]
        service_year_rates: dict[str, float | None] = {}
        for service_year in range(1, 7):
            index = min(service_year - 1, len(level_rows) - 1)
            service_year_rates[f"service_year_{service_year}_weekly_rate"] = _analysis_number(
                level_rows[index].get("weekly_rate")
            ) if level_rows else None
        expected_levels.setdefault((quarter_start, band), set()).update(levels)
        latest_row = max(level_rows, key=lambda row: str(row.get("effective_from") or ""))
        source_basis = _distribution_source_basis(level_rows)
        is_projected = source_basis == "scenario_projection"
        raw_points.append({
            "analysis_id": f"dpa::{ae_id}::{quarter_start}::band_{band}",
            "ae_id": ae_id,
            "agreement_id": ae_id,
            "agreement_name": latest_row.get("agreement_name"),
            "canonical_lga_short_name": latest_row.get("canonical_lga_short_name"),
            "quarter_start": quarter_start,
            "year": int(quarter_start[:4]),
            "quarter": ((int(quarter_start[5:7]) - 1) // 3) + 1,
            "band": band,
            "min_level": _distribution_level(min_row) or None,
            "min_weekly_rate": min_rate,
            "max_level": _distribution_level(max_row) or None,
            "max_weekly_rate": max_rate,
            "midpoint_weekly_rate": midpoint_rate,
            "max_level_point_weekly_rate": max_rate,
            "comparison_metric": "range_midpoint_rate",
            "comparison_metric_label": "Range midpoint rate",
            "service_year_index": None,
            "entry_weekly_rate": min_rate,
            "range_midpoint_weekly_rate": midpoint_rate,
            "capacity_weekly_rate": max_rate,
            **service_year_rates,
            "metric_bundle_status": "legacy_endpoint_metric_labelled",
            "metric_bundle_caveats": [
                "Legacy endpoint defaults chart weekly_rate to explicit range_midpoint_rate.",
                "Y1-Y6 values are service-horizon comparison estimates; later horizons carry capacity forward after the actual ladder is exhausted.",
            ],
            "weekly_rate": midpoint_rate,
            "standard_band": band,
            "standard_level": (
                f"{_distribution_level(min_row)}-{_distribution_level(max_row)}"
                if _distribution_level(min_row) and _distribution_level(max_row)
                else None
            ),
            "classification_label": (
                f"Band {band} Levels {_distribution_level(min_row)}-{_distribution_level(max_row)} range midpoint"
                if _distribution_level(min_row) and _distribution_level(max_row)
                else f"Band {band} range midpoint"
            ),
            "chart_band": band,
            "chart_min_level": _distribution_level(min_row) or None,
            "chart_max_level": _distribution_level(max_row) or None,
            "chart_min_weekly_rate": min_rate,
            "chart_max_weekly_rate": max_rate,
            "chart_basis": "distribution_point_analysis",
            "effective_from": latest_row.get("effective_from"),
            "to_date": latest_row.get("to_date"),
            "covered_by_table": True,
            "source_basis": source_basis,
            "is_known_value": not is_projected,
            "is_projected_value": is_projected,
            "source_table_title": latest_row.get("table_title"),
            "source_clause": latest_row.get("source_clause"),
            "source_pages": _source_pages_from_rows(level_rows),
            "source_row_ids": [item["source_row_id"] for item in _distribution_source_rows(level_rows)],
            "source_rows": _distribution_source_rows(level_rows),
            "governed_at": latest_row.get("governed_at"),
            "source_version": hashlib.sha1(json.dumps({
                "ae_id": ae_id,
                "quarter_start": quarter_start,
                "band": band,
                "rows": _distribution_source_rows(level_rows),
            }, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12],
            "level_count": len(levels),
            "expected_level_count": None,
            "missing_levels": [],
            "has_partial_band": False,
            "has_duplicate_levels": any(count > 1 for count in level_counts.values()),
            "calculation_status": "ok",
            "calculation_notes": "",
            "report_ready_status": "legacy_labelled_range_midpoint",
            "spatial_key": latest_row.get("spatial_key"),
            "map_join_key": latest_row.get("map_join_key"),
            "council_category": latest_row.get("council_category"),
            "council_type": latest_row.get("council_type"),
            "lgprf_group": latest_row.get("lgprf_group"),
            "vgccc_seifa_dis_score": latest_row.get("vgccc_seifa_dis_score"),
        })

    for point in raw_points:
        expected = sorted(
            expected_levels.get((point["quarter_start"], point["band"]), set()),
            key=_distribution_level_sort_key,
        )
        actual = {
            str(row.get("level"))
            for row in point.get("source_rows", [])
            if row.get("level") is not None
        }
        missing = [level for level in expected if level not in actual]
        point["expected_level_count"] = len(expected) if expected else point["level_count"]
        point["missing_levels"] = missing
        point["has_partial_band"] = bool(missing)
        if point["has_duplicate_levels"]:
            point["calculation_status"] = "duplicate_levels"
            point["calculation_notes"] = "Duplicate levels were present; latest effective row per level was used."
        elif missing:
            point["calculation_status"] = "partial"
            point["calculation_notes"] = f"Missing expected levels: {', '.join(missing)}."

    raw_points.sort(key=lambda item: (
        str(item.get("quarter_start") or "9999-99-99"),
        _analysis_sort_piece(item.get("canonical_lga_short_name") or item.get("agreement_name")),
        int(item.get("band") or 999999) if str(item.get("band") or "").isdigit() else 999999,
        str(item.get("band") or ""),
    ))

    quarter_starts = [str(row["quarter_start"]) for row in raw_points]
    source_basis_counts = Counter(str(row.get("source_basis") or "unknown") for row in raw_points)
    status_counts = Counter(str(row.get("calculation_status") or "unknown") for row in raw_points)
    patterns = [
        {"pattern": key, "count": count}
        for key, count in sorted(source_basis_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    payload = {
        "set_id": "set_3_distribution_point_analysis",
        "schema_version": "distribution_point_analysis.v1",
        "label": "Distribution Point Analysis",
        "description": "Legacy chart-ready governed pay points by agreement, quarter and band. Each point now labels the default weekly_rate as comparison_metric=range_midpoint_rate and carries entry, capacity, and Y1-Y6 service-horizon comparison estimates.",
        "generated_at": now_iso(),
        "source_set_id": pay_analysis.get("set_id"),
        "summary": {
            "agreements_scanned": (pay_analysis.get("summary") or {}).get("agreements_scanned"),
            "source_pay_table_rows": (pay_analysis.get("summary") or {}).get("rows", len(pay_rows)),
            "distribution_points": len(raw_points),
            "agreements_with_points": len({row["ae_id"] for row in raw_points}),
            "quarters": len(set(quarter_starts)),
            "bands": len({row["band"] for row in raw_points}),
            "earliest_quarter_start": min(quarter_starts) if quarter_starts else None,
            "latest_quarter_start": max(quarter_starts) if quarter_starts else None,
            "projected_points": sum(1 for row in raw_points if row.get("is_projected_value")),
            "known_points": sum(1 for row in raw_points if row.get("is_known_value")),
            "partial_band_points": sum(1 for row in raw_points if row.get("has_partial_band")),
            "duplicate_level_points": sum(1 for row in raw_points if row.get("has_duplicate_levels")),
            "source_basis_counts": dict(source_basis_counts),
            "calculation_status_counts": dict(status_counts),
        },
        "patterns": patterns,
        "rows": raw_points,
    }
    payload["asset_version"] = hashlib.sha1(json.dumps({
        "schema_version": payload["schema_version"],
        "summary": payload["summary"],
        "row_versions": [row.get("source_version") for row in raw_points],
    }, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return payload
