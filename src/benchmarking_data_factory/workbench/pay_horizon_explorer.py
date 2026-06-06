from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
import json
from pathlib import Path
import re
import sqlite3
from typing import Any


CURVE_VIEW_ID = "pay_service_horizon_curve_view"
CURVE_VIEW_JSON = Path("data") / "datamarts" / "pay_service_horizon_curve_view.json"
CURVE_VIEW_SQLITE = Path("data") / "datamarts" / "pay_service_horizon_curve_view.sqlite"
CURVE_VIEW_STATUS_JSON = Path("data") / "datamarts" / "pay_service_horizon_curve_view_status.json"
COUNCIL_PROFILE_JSON = Path("data") / "datamarts" / "council_profile_mart.json"
COUNCIL_MASTER_CSV = Path("data") / "reference" / "victorian-council-master.csv"
LEGACY_DISTRIBUTION_JSON = Path("data") / "analysis" / "distribution-point-analysis.json"
V2_CHART_VERSION = "pay_horizon_distribution_explorer.v2_prototype"
MIN_SELECTABLE_CURVE_COHORT_COUNCILS = 16

SINGLE_POINT_METRIC_TO_WINDOW = {
    "entry_rate": "entry_only",
    "range_midpoint_rate": "range_midpoint_only",
    "capacity_rate": "capacity_only",
    "service_year_3_rate": "y3_only",
}

SAFE_TITLE_TERMS = {
    "entry",
    "midpoint",
    "capacity",
    "service-horizon",
    "year",
    "range",
    "profile",
}


@dataclass(frozen=True)
class PayHorizonCurveStore:
    root: Path

    @property
    def curve_path(self) -> Path:
        return self.root / CURVE_VIEW_JSON

    @property
    def status_path(self) -> Path:
        return self.root / CURVE_VIEW_STATUS_JSON

    @property
    def sqlite_path(self) -> Path:
        return self.root / CURVE_VIEW_SQLITE

    def payload(self) -> dict[str, Any]:
        return read_json_cached(self.curve_path)

    def status(self) -> dict[str, Any] | None:
        if not self.status_path.exists():
            return None
        return read_json_cached(self.status_path)

    def response(
        self,
        *,
        standard_band: str | None = None,
        effective_from: str | None = None,
        quarter_start: str | None = None,
        cohort_id: str | None = None,
        selected_council_id: str | None = None,
        service_horizon_window_id: str | None = None,
        limit: int = 250,
    ) -> dict[str, Any]:
        if self.sqlite_path.exists():
            return self.sqlite_response(
                standard_band=standard_band,
                effective_from=effective_from,
                quarter_start=quarter_start,
                cohort_id=cohort_id,
                selected_council_id=selected_council_id,
                service_horizon_window_id=service_horizon_window_id,
                limit=limit,
            )
        payload = self.payload()
        rows = filter_curve_rows(
            payload.get("rows") or [],
            standard_band=standard_band,
            effective_from=effective_from,
            cohort_id=cohort_id,
            selected_council_id=selected_council_id,
            service_horizon_window_id=service_horizon_window_id,
        )
        capped_limit = min(max(limit, 1), 5000)
        return {
            "schema_version": payload.get("schema_version"),
            "mart_id": payload.get("mart_id") or CURVE_VIEW_ID,
            "source": str(self.curve_path),
            "status": self.status(),
            "row_count": payload.get("row_count") or len(payload.get("rows") or []),
            "filtered_count": len(rows),
            "limit": capped_limit,
            "rows": rows[:capped_limit],
        }

    def sqlite_response(
        self,
        *,
        standard_band: str | None = None,
        effective_from: str | None = None,
        quarter_start: str | None = None,
        cohort_id: str | None = None,
        selected_council_id: str | None = None,
        service_horizon_window_id: str | None = None,
        limit: int = 250,
    ) -> dict[str, Any]:
        capped_limit = min(max(limit, 1), 5000)
        if quarter_start:
            rows, filtered_count, row_count, schema_version = query_curve_sqlite_quarter(
                self.sqlite_path,
                standard_band=standard_band,
                quarter_start=quarter_start,
                cohort_id=cohort_id,
                selected_council_id=selected_council_id,
                service_horizon_window_id=service_horizon_window_id,
                limit=capped_limit,
            )
        else:
            rows, filtered_count, row_count, schema_version = query_curve_sqlite(
                self.sqlite_path,
                standard_band=standard_band,
                effective_from=effective_from,
                cohort_id=cohort_id,
                selected_council_id=selected_council_id,
                service_horizon_window_id=service_horizon_window_id,
                limit=capped_limit,
            )
        return {
            "schema_version": schema_version,
            "mart_id": CURVE_VIEW_ID,
            "source": str(self.sqlite_path),
            "status": self.status(),
            "row_count": row_count,
            "filtered_count": filtered_count,
            "limit": capped_limit,
            "rows": rows,
        }

    def options_response(self) -> dict[str, Any]:
        council_payload = read_json_cached(self.root / COUNCIL_PROFILE_JSON)
        council_reference = council_reference_options(self.root, council_payload.get("rows") or [])
        if self.sqlite_path.exists():
            options, row_count, schema_version = curve_options_from_sqlite(
                self.sqlite_path,
                council_payload.get("rows") or [],
            )
            options["council_reference"] = council_reference
            return {
                "schema_version": schema_version,
                "mart_id": CURVE_VIEW_ID,
                "source": str(self.sqlite_path),
                "status": self.status(),
                "row_count": row_count,
                "options": options,
            }
        payload = self.payload()
        return {
            "schema_version": payload.get("schema_version"),
            "mart_id": payload.get("mart_id") or CURVE_VIEW_ID,
            "source": str(self.curve_path),
            "status": self.status(),
            "row_count": payload.get("row_count") or len(payload.get("rows") or []),
            "options": {
                **curve_options(payload.get("rows") or [], council_payload.get("rows") or []),
                "council_reference": council_reference,
            },
        }


def sqlite_metadata(path: Path) -> dict[str, str]:
    connection = sqlite3.connect(path)
    try:
        return {key: value for key, value in connection.execute("SELECT key, value FROM metadata")}
    finally:
        connection.close()


def query_curve_sqlite(
    path: Path,
    *,
    standard_band: str | None = None,
    effective_from: str | None = None,
    cohort_id: str | None = None,
    selected_council_id: str | None = None,
    service_horizon_window_id: str | None = None,
    limit: int = 250,
) -> tuple[list[dict[str, Any]], int, int, str | None]:
    where: list[str] = []
    params: list[Any] = []
    if standard_band:
        where.append("standard_band = ?")
        params.append(str(standard_band))
    if effective_from:
        where.append("effective_from = ?")
        params.append(str(effective_from))
    if cohort_id:
        where.append("cohort_id = ?")
        params.append(str(cohort_id))
    if selected_council_id:
        where.append("LOWER(selected_council_id) = LOWER(?)")
        params.append(str(selected_council_id))
    if service_horizon_window_id:
        where.append("service_horizon_window_id = ?")
        params.append(str(service_horizon_window_id))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    order_sql = """
        ORDER BY
            CAST(standard_band AS INTEGER),
            effective_from,
            service_horizon_window_id,
            selected_council_name,
            selected_range_group_id
    """
    connection = sqlite3.connect(path)
    try:
        metadata = {key: value for key, value in connection.execute("SELECT key, value FROM metadata")}
        filtered_count = int(connection.execute(f"SELECT COUNT(*) FROM curve_rows {where_sql}", params).fetchone()[0])
        rows = [
            json.loads(row_json)
            for (row_json,) in connection.execute(
                f"SELECT row_json FROM curve_rows {where_sql} {order_sql} LIMIT ?",
                [*params, limit],
            )
        ]
        return rows, filtered_count, int(metadata.get("row_count") or 0), metadata.get("schema_version")
    finally:
        connection.close()


def query_curve_sqlite_quarter(
    path: Path,
    *,
    standard_band: str | None = None,
    quarter_start: str,
    cohort_id: str | None = None,
    selected_council_id: str | None = None,
    service_horizon_window_id: str | None = None,
    limit: int = 250,
) -> tuple[list[dict[str, Any]], int, int, str | None]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        metadata = {key: value for key, value in connection.execute("SELECT key, value FROM metadata")}
        cohort_ids = [cohort_id] if cohort_id else selectable_cohort_ids(connection)
        rows: list[dict[str, Any]] = []
        for current_cohort_id in cohort_ids:
            rows.extend(
                build_quarter_curve_rows(
                    connection,
                    standard_band=str(standard_band or ""),
                    quarter_start=quarter_start,
                    cohort_id=str(current_cohort_id or ""),
                    selected_council_id=selected_council_id,
                    service_horizon_window_id=service_horizon_window_id or "range_midpoint_only",
                )
            )
        rows = sorted(
            rows,
            key=lambda row: (
                _sort_band(str(row.get("standard_band") or "")),
                str(row.get("quarter_start") or row.get("effective_from") or ""),
                str(row.get("cohort_name") or ""),
                str(row.get("selected_council_name") or ""),
                str(row.get("selected_range_group_id") or ""),
            ),
        )
        return rows[:limit], len(rows), int(metadata.get("row_count") or 0), metadata.get("schema_version")
    finally:
        connection.close()


def selectable_cohort_ids(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            """
            SELECT cohort_id
            FROM curve_rows
            WHERE cohort_id IS NOT NULL
            GROUP BY cohort_id
            HAVING MAX(curve_council_count) >= ?
            ORDER BY MIN(cohort_name)
            """,
            (MIN_SELECTABLE_CURVE_COHORT_COUNCILS,),
        )
    ]


def build_quarter_curve_rows(
    connection: sqlite3.Connection,
    *,
    standard_band: str,
    quarter_start: str,
    cohort_id: str,
    selected_council_id: str | None,
    service_horizon_window_id: str,
) -> list[dict[str, Any]]:
    if not standard_band or not quarter_start or not cohort_id:
        return []
    source_rows = [
        json.loads(row["row_json"])
        for row in connection.execute(
            """
            SELECT row_json
            FROM curve_rows
            WHERE standard_band = ?
              AND cohort_id = ?
              AND service_horizon_window_id = ?
              AND effective_from <= ?
            ORDER BY effective_from, selected_council_name, selected_range_group_id
            """,
            (standard_band, cohort_id, service_horizon_window_id, quarter_start),
        )
    ]
    active_comparator_rows = latest_active_curve_rows(source_rows, quarter_start, comparator_only=True)
    if not active_comparator_rows:
        return []
    comparator_values = active_curve_values(active_comparator_rows)
    if not comparator_values:
        return []
    selected_source_rows = source_rows
    if selected_council_id:
        selected_key = str(selected_council_id).casefold()
        selected_source_rows = [
            row
            for row in source_rows
            if str(row.get("selected_council_id") or "").casefold() == selected_key
        ]
    selected_rows = latest_active_curve_rows(selected_source_rows, quarter_start, comparator_only=False)
    if selected_council_id and not selected_rows:
        return []
    if not selected_rows:
        selected_rows = active_comparator_rows[:1]

    stat_values = stats(comparator_values)
    cohort_name = str((active_comparator_rows[0].get("cohort_name") if active_comparator_rows else "") or cohort_id)
    included_metrics = parse_json_field(active_comparator_rows[0].get("included_metric_points"), [])
    if not isinstance(included_metrics, list):
        included_metrics = []
    horizon_years = parse_json_field(active_comparator_rows[0].get("included_service_horizon_years"), [])
    if not isinstance(horizon_years, list):
        horizon_years = []
    window_label = active_comparator_rows[0].get("service_horizon_window_label") or service_horizon_window_id
    density_points = density_points_for_values(comparator_values)
    envelope = {
        "quarter_start": quarter_start,
        "curve_sample_count": len(comparator_values),
        "curve_council_count": len({str(row.get("selected_council_id") or "") for row in active_comparator_rows}),
        "blocked_observation_count": 0,
        "included_metric_points": included_metrics,
        "weighting_method": "observation_weighted",
        "min": stat_values["min"],
        "p25": stat_values["p25"],
        "median": stat_values["median"],
        "p75": stat_values["p75"],
        "max": stat_values["max"],
    }

    output_rows: list[dict[str, Any]] = []
    for selected_row in selected_rows:
        selected_points_for_row = selected_points(selected_row)
        selected_values = [float(point["weekly_rate"]) for point in selected_points_for_row if isinstance(point.get("weekly_rate"), (int, float))]
        row = {
            **selected_row,
            "curve_id": (
                f"quarter_curve::{cohort_id}::band_{standard_band}::{quarter_start}::"
                f"{service_horizon_window_id}::{selected_row.get('selected_range_group_id') or 'selected'}"
            ),
            "cohort_id": cohort_id,
            "cohort_name": cohort_name,
            "standard_band": standard_band,
            "effective_from": quarter_start,
            "quarter_start": quarter_start,
            "effective_to": None,
            "service_horizon_window_id": service_horizon_window_id,
            "service_horizon_window_label": window_label,
            "included_metric_points": included_metrics,
            "included_service_horizon_years": horizon_years,
            "curve_sample_count": len(comparator_values),
            "curve_council_count": envelope["curve_council_count"],
            "weighting_method": "observation_weighted",
            "curve_min": stat_values["min"],
            "curve_p25": stat_values["p25"],
            "curve_median": stat_values["median"],
            "curve_p75": stat_values["p75"],
            "curve_max": stat_values["max"],
            "density_points_json": json.dumps(density_points),
            "comparator_envelope_json": json.dumps(envelope),
            "horizon_envelope_json": json.dumps(horizon_envelope(active_comparator_rows)),
            "selected_council_points_json": json.dumps(selected_points_for_row),
            "selected_council_min": min(selected_values) if selected_values else None,
            "selected_council_max": max(selected_values) if selected_values else None,
            "selected_council_position_summary": selected_position_summary(selected_values, stat_values),
            "chart_title": chart_title_for_window(standard_band, window_label, cohort_name),
            "metric_caveats": merge_caveats(
                selected_row.get("metric_caveats"),
                ["Quarter curve resolves each observation to the latest governed rate period active at the selected dim-date quarter."],
            ),
            "report_ready_status": "ready",
            "caveat_status": "ready",
            "blocker_reason": None,
        }
        output_rows.append(row)
    return output_rows


def latest_active_curve_rows(rows: list[dict[str, Any]], quarter_start: str, *, comparator_only: bool) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if comparator_only and not row.get("selected_council_included_in_curve_sample"):
            continue
        if not curve_row_active_at(row, quarter_start):
            continue
        key = active_curve_row_key(row)
        effective_from = curve_row_effective_from(row)
        previous = latest.get(key)
        if previous is None or effective_from > curve_row_effective_from(previous):
            latest[key] = row
    return sorted(
        latest.values(),
        key=lambda row: (
            str(row.get("selected_council_name") or ""),
            str(row.get("selected_range_group_id") or ""),
        ),
    )


def curve_row_active_at(row: dict[str, Any], quarter_start: str) -> bool:
    effective_from = curve_row_effective_from(row)
    if not effective_from or effective_from > quarter_start:
        return False
    effective_to = curve_row_effective_to(row)
    return not effective_to or effective_to >= quarter_start


def curve_row_effective_from(row: dict[str, Any]) -> str:
    parsed = parse_range_group_id(row.get("selected_range_group_id"))
    return parsed.get("effective_from") or str(row.get("effective_from") or "")


def curve_row_effective_to(row: dict[str, Any]) -> str | None:
    parsed = parse_range_group_id(row.get("selected_range_group_id"))
    effective_to = parsed.get("effective_to") or row.get("effective_to")
    if effective_to in {None, "", "open_ended", "unknown", "None"}:
        return None
    return str(effective_to)


def parse_range_group_id(value: Any) -> dict[str, str]:
    parts = str(value or "").split("::")
    if len(parts) >= 5 and parts[0] == "payrange":
        return {
            "agreement_id": parts[1],
            "effective_from": parts[2],
            "effective_to": parts[3],
            "band": parts[4],
        }
    return {}


def active_curve_row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    parsed = parse_range_group_id(row.get("selected_range_group_id"))
    return (
        str(row.get("selected_council_id") or ""),
        parsed.get("agreement_id") or str(row.get("selected_range_group_id") or ""),
        str(row.get("selected_classification_family") or parsed.get("band") or row.get("standard_band") or ""),
    )


def active_curve_values(rows: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for row in rows:
        for point in selected_points(row):
            value = point.get("weekly_rate")
            if isinstance(value, (int, float)):
                values.append(float(value))
    return values


def density_points_for_values(values: list[float]) -> list[dict[str, float]]:
    clean = sorted(values)
    if not clean:
        return []
    return [{"x": value, "y": (index + 1) / len(clean)} for index, value in enumerate(clean)]


def horizon_envelope(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_metric: dict[str, list[float]] = {}
    for row in rows:
        for point in selected_points(row):
            metric = str(point.get("comparison_metric") or "")
            value = point.get("weekly_rate")
            if metric and isinstance(value, (int, float)):
                by_metric.setdefault(metric, []).append(float(value))
    return [
        {
            "comparison_metric": metric,
            "sample_count": metric_stats["count"],
            "median": metric_stats["median"],
            "min": metric_stats["min"],
            "max": metric_stats["max"],
        }
        for metric, values in sorted(by_metric.items())
        for metric_stats in [stats(values)]
    ]


def selected_position_summary(selected_values: list[float], stat_values: dict[str, Any]) -> str:
    if not selected_values or stat_values.get("median") is None:
        return "selected_value_not_available"
    selected_value = selected_values[0]
    median_value = float(stat_values["median"])
    if selected_value > median_value:
        return "selected_value_above_curve_median"
    if selected_value < median_value:
        return "selected_value_below_curve_median"
    return "selected_value_equals_curve_median"


def chart_title_for_window(band: str, window_label: Any, cohort_name: str) -> str:
    label = str(window_label or "range midpoint rate distribution")
    label = label.replace("Range midpoint rate distribution", "governed range midpoint distribution")
    return f"Band {band} {label} - {cohort_name}"


def merge_caveats(existing: Any, extra: list[str]) -> list[str]:
    caveats = parse_json_field(existing, existing)
    if isinstance(caveats, str):
        caveats = [caveats]
    if not isinstance(caveats, list):
        caveats = []
    merged: list[str] = []
    for item in [*caveats, *extra]:
        if item and item not in merged:
            merged.append(str(item))
    return merged


def quarter_periods_from_effective_periods(effective_periods: list[str]) -> list[str]:
    quarter_starts = sorted(
        {
            quarter_start
            for value in effective_periods
            for quarter_start in [quarter_start_for_iso_date(value)]
            if quarter_start
        }
    )
    if not quarter_starts:
        return []
    start_year = int(quarter_starts[0][:4])
    start_quarter = quarter_number_from_iso(quarter_starts[0])
    end_year = int(quarter_starts[-1][:4])
    end_quarter = quarter_number_from_iso(quarter_starts[-1])
    periods: list[str] = []
    year, quarter = start_year, start_quarter
    while (year, quarter) <= (end_year, end_quarter):
        periods.append(quarter_start_from_year_quarter(year, quarter))
        quarter += 1
        if quarter > 4:
            quarter = 1
            year += 1
    return periods


def quarter_start_for_iso_date(value: str) -> str | None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value or "")):
        return None
    return quarter_start_from_year_quarter(int(value[:4]), quarter_number_from_iso(value))


def quarter_number_from_iso(value: str) -> int:
    month = int(str(value)[5:7])
    return ((month - 1) // 3) + 1


def quarter_start_from_year_quarter(year: int, quarter: int) -> str:
    month = ((quarter - 1) * 3) + 1
    return date(year, month, 1).isoformat()


def curve_options_from_sqlite(path: Path, council_rows: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], int, str | None]:
    connection = sqlite3.connect(path)
    try:
        metadata = {key: value for key, value in connection.execute("SELECT key, value FROM metadata")}
        bands = sorted(
            {str(row[0]) for row in connection.execute("SELECT DISTINCT standard_band FROM curve_rows WHERE standard_band IS NOT NULL")},
            key=_sort_band,
        )
        effective_periods = sorted(
            {str(row[0]) for row in connection.execute("SELECT DISTINCT effective_from FROM curve_rows WHERE effective_from IS NOT NULL")}
        )
        quarter_periods = quarter_periods_from_effective_periods(effective_periods)
        cohorts = sorted(
            [
                {
                    "cohort_id": cohort_id,
                    "cohort_name": cohort_name,
                    "cohort_council_count": max_curve_council_count,
                }
                for cohort_id, cohort_name, max_curve_council_count in connection.execute(
                    """
                    SELECT cohort_id, MIN(cohort_name), MAX(curve_council_count) AS max_curve_council_count
                    FROM curve_rows
                    WHERE cohort_id IS NOT NULL
                    GROUP BY cohort_id
                    HAVING max_curve_council_count >= ?
                    """,
                    (MIN_SELECTABLE_CURVE_COHORT_COUNCILS,),
                )
            ],
            key=lambda item: str(item.get("cohort_name") or item.get("cohort_id") or ""),
        )
        council_rows_from_curve = [
            {
                "selected_council_id": council_id,
                "selected_council_name": council_name,
                "has_pay_horizon_data": True,
            }
            for council_id, council_name in connection.execute(
                """
                SELECT selected_council_id, MIN(selected_council_name)
                FROM curve_rows
                WHERE selected_council_id IS NOT NULL
                GROUP BY selected_council_id
                """
            )
        ]
        window_rows = [
            json.loads(row_json)
            for (row_json,) in connection.execute(
                """
                SELECT row_json
                FROM curve_rows
                WHERE row_index IN (
                    SELECT MIN(row_index)
                    FROM curve_rows
                    WHERE service_horizon_window_id IS NOT NULL
                    GROUP BY service_horizon_window_id
                )
                """
            )
        ]
        default_row_json = connection.execute(
            """
            SELECT row_json
            FROM curve_rows
            WHERE service_horizon_window_id = 'range_midpoint_only'
              AND standard_band = '5'
              AND cohort_id = 'all_governed'
              AND curve_council_count >= ?
            ORDER BY effective_from DESC, selected_council_name, selected_range_group_id
            LIMIT 1
            """,
            (MIN_SELECTABLE_CURVE_COHORT_COUNCILS,),
        ).fetchone()
        if default_row_json is None:
            default_row_json = connection.execute(
                """
                SELECT row_json
                FROM curve_rows
                WHERE service_horizon_window_id = 'range_midpoint_only'
                  AND standard_band = '5'
                ORDER BY effective_from DESC, selected_council_name DESC, selected_range_group_id DESC
                LIMIT 1
                """
            ).fetchone()
        row_count = int(metadata.get("row_count") or 0)
    finally:
        connection.close()

    councils_by_id = {
        str(row.get("selected_council_id") or ""): row
        for row in council_rows_from_curve
        if row.get("selected_council_id")
    }
    for row in council_rows or []:
        council_id = str(row.get("canonical_council_id") or row.get("council_key") or "")
        if not council_id:
            continue
        councils_by_id.setdefault(
            council_id,
            {
                "selected_council_id": council_id,
                "selected_council_name": row.get("canonical_council_name") or row.get("council_name") or council_id,
                "has_pay_horizon_data": False,
            },
        )
    councils = sorted(
        councils_by_id.values(),
        key=lambda item: str(item.get("selected_council_name") or item.get("selected_council_id") or ""),
    )
    windows = []
    for row in window_rows:
        metrics = parse_json_field(row.get("included_metric_points"), [])
        years = parse_json_field(row.get("included_service_horizon_years"), [])
        windows.append(
            {
                "service_horizon_window_id": row.get("service_horizon_window_id"),
                "service_horizon_window_label": row.get("service_horizon_window_label"),
                "included_metric_points": metrics,
                "included_service_horizon_years": years,
                "view_mode": "single_point" if len(metrics) == 1 else "service_window",
                "comparison_metric": metrics[0] if len(metrics) == 1 else None,
            }
        )
    windows.sort(key=lambda item: window_sort_key(str(item.get("service_horizon_window_id") or "")))
    default_row = json.loads(default_row_json[0]) if default_row_json else None
    return (
        {
            "bands": bands,
            "effective_periods": effective_periods,
            "quarter_periods": quarter_periods,
            "cohorts": cohorts,
            "councils": councils,
            "windows": windows,
            "single_point_metrics": [
                {
                    "comparison_metric": window["comparison_metric"],
                    "service_horizon_window_id": window["service_horizon_window_id"],
                    "label": window["service_horizon_window_label"],
                }
                for window in windows
                if window.get("view_mode") == "single_point"
            ],
            "default_selection": {
                "selected_council_id": default_row.get("selected_council_id") if default_row else None,
                "standard_band": default_row.get("standard_band") if default_row else None,
                "cohort_id": default_row.get("cohort_id") if default_row else None,
                "effective_from": default_row.get("effective_from") if default_row else None,
                "quarter_start": default_row.get("quarter_start") or default_row.get("effective_from") if default_row else None,
                "service_horizon_window_id": default_row.get("service_horizon_window_id") if default_row else None,
                "comparison_metric": "range_midpoint_rate",
            },
        },
        row_count,
        metadata.get("schema_version"),
    )


def council_reference_options(root: Path, council_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    master_path = root / COUNCIL_MASTER_CSV
    rows: list[dict[str, Any]]
    if master_path.exists():
        with master_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        rows = list(council_rows or [])
    references = []
    for row in rows:
        reference = council_reference_row(row)
        if reference.get("council_key"):
            references.append(reference)
    return sorted(
        references,
        key=lambda row: str(row.get("council_name") or row.get("council_key") or ""),
    )


def council_reference_row(row: dict[str, Any]) -> dict[str, Any]:
    council_key = (
        row.get("council_key")
        or row.get("canonical_council_id")
        or row.get("spatial_key")
        or row.get("map_join_key")
        or ""
    )
    council_name = (
        row.get("long_name")
        or row.get("canonical_council_name")
        or row.get("council_name")
        or row.get("short_name")
        or council_key
    )
    return {
        "council_key": council_key,
        "council_name": council_name,
        "short_name": row.get("short_name") or row.get("spatial_name") or council_name,
        "spatial_key": row.get("spatial_key") or row.get("map_join_key") or council_key,
        "map_join_key": row.get("map_join_key") or row.get("spatial_key") or council_key,
        "council_category": row.get("council_category") or "",
        "council_type": row.get("council_type") or "",
        "lgprf_group": row.get("lgprf_group") or "",
        "vif_metropolitan_region": row.get("vif_metropolitan_region") or "",
        "vif_regional_partnership": row.get("vif_regional_partnership") or "",
        "vgccc_region": row.get("vgccc_region") or "",
        "office_lat": row.get("office_lat") or "",
        "office_lon": row.get("office_lon") or "",
        "vgccc_seifa_dis_score": row.get("vgccc_seifa_dis_score") or "",
        "lgprf_relative_socioeconomic_disadvantage": row.get("lgprf_relative_socioeconomic_disadvantage") or "",
    }


def read_json_cached(path: Path) -> dict[str, Any]:
    if not path.exists():
        return read_json(path)
    stat = path.stat()
    return _read_json_cached(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=12)
def _read_json_cached(path: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size
    return read_json(Path(path))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "missing",
            "mart_id": CURVE_VIEW_ID,
            "row_count": 0,
            "rows": [],
            "error": "file_not_found",
            "path": str(path),
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "schema_version": "invalid_json",
            "mart_id": CURVE_VIEW_ID,
            "row_count": 0,
            "rows": [],
            "error": f"invalid_json: {exc}",
            "path": str(path),
        }


def parse_json_field(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def _sort_band(value: str) -> tuple[int, str]:
    try:
        return (0, f"{int(value):03d}")
    except (TypeError, ValueError):
        return (1, str(value))


def _unique_dicts(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if value and value not in by_key:
            by_key[value] = row
    return list(by_key.values())


def curve_options(rows: list[dict[str, Any]], council_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    bands = sorted({str(row.get("standard_band") or "") for row in rows if row.get("standard_band")}, key=_sort_band)
    effective_periods = sorted({str(row.get("effective_from") or "") for row in rows if row.get("effective_from")})
    quarter_periods = quarter_periods_from_effective_periods(effective_periods)
    cohort_max_curve_n: dict[str, int] = {}
    for row in rows:
        cohort_id = str(row.get("cohort_id") or "")
        if cohort_id:
            cohort_max_curve_n[cohort_id] = max(
                cohort_max_curve_n.get(cohort_id, 0),
                int(row.get("curve_council_count") or 0),
            )
    cohorts = sorted(
        [
            {
                "cohort_id": row.get("cohort_id"),
                "cohort_name": row.get("cohort_name"),
                "cohort_council_count": cohort_max_curve_n.get(str(row.get("cohort_id") or ""), 0),
            }
            for row in _unique_dicts(rows, "cohort_id")
            if cohort_max_curve_n.get(str(row.get("cohort_id") or ""), 0) >= MIN_SELECTABLE_CURVE_COHORT_COUNCILS
        ],
        key=lambda item: str(item.get("cohort_name") or item.get("cohort_id") or ""),
    )
    councils_by_id = {
        str(row.get("selected_council_id") or ""): {
            "selected_council_id": row.get("selected_council_id"),
            "selected_council_name": row.get("selected_council_name"),
            "has_pay_horizon_data": True,
        }
        for row in _unique_dicts(rows, "selected_council_id")
        if row.get("selected_council_id")
    }
    for row in council_rows or []:
        council_id = str(row.get("canonical_council_id") or row.get("council_key") or "")
        if not council_id:
            continue
        councils_by_id.setdefault(
            council_id,
            {
                "selected_council_id": council_id,
                "selected_council_name": row.get("canonical_council_name") or row.get("council_name") or council_id,
                "has_pay_horizon_data": False,
            },
        )
    councils = sorted(
        councils_by_id.values(),
        key=lambda item: str(item.get("selected_council_name") or item.get("selected_council_id") or ""),
    )
    windows = []
    for row in _unique_dicts(rows, "service_horizon_window_id"):
        metrics = parse_json_field(row.get("included_metric_points"), [])
        years = parse_json_field(row.get("included_service_horizon_years"), [])
        windows.append(
            {
                "service_horizon_window_id": row.get("service_horizon_window_id"),
                "service_horizon_window_label": row.get("service_horizon_window_label"),
                "included_metric_points": metrics,
                "included_service_horizon_years": years,
                "view_mode": "single_point" if len(metrics) == 1 else "service_window",
                "comparison_metric": metrics[0] if len(metrics) == 1 else None,
            }
        )
    windows.sort(key=lambda item: window_sort_key(str(item.get("service_horizon_window_id") or "")))
    default_row = default_selection_row(rows)
    return {
        "bands": bands,
        "effective_periods": effective_periods,
        "quarter_periods": quarter_periods,
        "cohorts": cohorts,
        "councils": councils,
        "windows": windows,
        "single_point_metrics": [
            {
                "comparison_metric": window["comparison_metric"],
                "service_horizon_window_id": window["service_horizon_window_id"],
                "label": window["service_horizon_window_label"],
            }
            for window in windows
            if window.get("view_mode") == "single_point"
        ],
        "default_selection": {
            "selected_council_id": default_row.get("selected_council_id") if default_row else None,
            "standard_band": default_row.get("standard_band") if default_row else None,
            "cohort_id": default_row.get("cohort_id") if default_row else None,
            "effective_from": default_row.get("effective_from") if default_row else None,
            "quarter_start": default_row.get("quarter_start") or default_row.get("effective_from") if default_row else None,
            "service_horizon_window_id": default_row.get("service_horizon_window_id") if default_row else None,
            "comparison_metric": "range_midpoint_rate",
        },
    }


def window_sort_key(window_id: str) -> tuple[int, str]:
    order = {
        "entry_only": 10,
        "range_midpoint_only": 20,
        "y3_only": 30,
        "capacity_only": 40,
        "entry_to_y3": 50,
        "y3_to_y6": 60,
        "entry_to_y6": 70,
        "entry_to_capacity_profile": 80,
    }
    return (order.get(window_id, 999), window_id)


def default_selection_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    midpoint_rows = [row for row in rows if row.get("service_horizon_window_id") == "range_midpoint_only"]
    robust_candidates = [
        row
        for row in midpoint_rows
        if str(row.get("standard_band") or "") == "5"
        and row.get("cohort_id") == "all_governed"
        and int(row.get("curve_council_count") or 0) >= MIN_SELECTABLE_CURVE_COHORT_COUNCILS
    ]
    candidates = robust_candidates or [row for row in midpoint_rows if str(row.get("standard_band") or "") == "5"] or midpoint_rows or rows
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            str(row.get("effective_from") or ""),
            str(row.get("selected_council_name") or ""),
            str(row.get("selected_range_group_id") or ""),
        ),
        reverse=True,
    )[0]


def filter_curve_rows(
    rows: list[dict[str, Any]],
    *,
    standard_band: str | None = None,
    effective_from: str | None = None,
    cohort_id: str | None = None,
    selected_council_id: str | None = None,
    service_horizon_window_id: str | None = None,
) -> list[dict[str, Any]]:
    filtered = rows
    if standard_band:
        filtered = [row for row in filtered if str(row.get("standard_band") or "") == str(standard_band)]
    if effective_from:
        filtered = [row for row in filtered if str(row.get("effective_from") or "") == str(effective_from)]
    if cohort_id:
        filtered = [row for row in filtered if str(row.get("cohort_id") or "") == str(cohort_id)]
    if selected_council_id:
        selected_key = str(selected_council_id).casefold()
        filtered = [
            row
            for row in filtered
            if str(row.get("selected_council_id") or "").casefold() == selected_key
            or str(selected_agreement_id(row) or "").casefold() == selected_key
        ]
    if service_horizon_window_id:
        filtered = [
            row
            for row in filtered
            if str(row.get("service_horizon_window_id") or "") == str(service_horizon_window_id)
        ]
    return sorted(
        filtered,
        key=lambda row: (
            _sort_band(str(row.get("standard_band") or "")),
            str(row.get("effective_from") or ""),
            window_sort_key(str(row.get("service_horizon_window_id") or "")),
            str(row.get("selected_council_name") or ""),
            str(row.get("selected_range_group_id") or ""),
        ),
    )


def selected_agreement_id(row: dict[str, Any]) -> str | None:
    range_group = str(row.get("selected_range_group_id") or "")
    match = re.search(r"payrange::([^:]+)::", range_group)
    return match.group(1) if match else None


def selected_points(row: dict[str, Any]) -> list[dict[str, Any]]:
    points = parse_json_field(row.get("selected_council_points_json"), [])
    return points if isinstance(points, list) else []


def comparator_envelope(row: dict[str, Any]) -> dict[str, Any]:
    envelope = parse_json_field(row.get("comparator_envelope_json"), {})
    return envelope if isinstance(envelope, dict) else {}


def title_is_safe(title: str) -> bool:
    lowered = (title or "").casefold()
    if re.fullmatch(r"\s*band\s+\w+\s+distribution\s*", lowered):
        return False
    return "distribution" in lowered and any(term in lowered for term in SAFE_TITLE_TERMS)


def build_chart_manifest(
    row: dict[str, Any],
    *,
    view_mode: str,
    comparison_metric: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    envelope = comparator_envelope(row)
    included_metric_points = parse_json_field(row.get("included_metric_points"), [])
    points = selected_points(row)
    service_horizon_window_id = row.get("service_horizon_window_id")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "chart_version": V2_CHART_VERSION,
        "view_mode": view_mode,
        "comparison_metric": comparison_metric if view_mode == "single_point" else None,
        "service_horizon_window_id": service_horizon_window_id,
        "service_horizon_window_label": row.get("service_horizon_window_label"),
        "included_metric_points": included_metric_points,
        "selected_council": {
            "id": row.get("selected_council_id"),
            "name": row.get("selected_council_name"),
            "agreement_id": selected_agreement_id(row),
        },
        "band": row.get("standard_band"),
        "cohort": {
            "id": row.get("cohort_id"),
            "name": row.get("cohort_name"),
        },
        "effective_period": {
            "effective_from": row.get("effective_from"),
            "effective_to": row.get("effective_to"),
        },
        "weighting_method": row.get("weighting_method"),
        "source_view": CURVE_VIEW_ID,
        "source_view_version": "datamart_current",
        "council_count": row.get("curve_council_count") or envelope.get("curve_council_count"),
        "observation_count": row.get("curve_sample_count") or envelope.get("curve_sample_count"),
        "selected_point_count": len(points),
        "caveats": row.get("metric_caveats") or [],
        "generated_at": generated_at,
        "report_ready_status": row.get("report_ready_status"),
        "title": row.get("chart_title"),
        "title_safe": title_is_safe(str(row.get("chart_title") or "")),
    }


def percentile(values: list[float], p: float) -> float | None:
    clean = sorted(value for value in values if isinstance(value, (int, float)))
    if not clean:
        return None
    if len(clean) == 1:
        return float(clean[0])
    index = (len(clean) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(clean) - 1)
    if lower == upper:
        return float(clean[lower])
    return float(clean[lower] + ((clean[upper] - clean[lower]) * (index - lower)))


def stats(values: list[float]) -> dict[str, Any]:
    clean = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not clean:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}
    return {
        "count": len(clean),
        "min": clean[0],
        "p25": percentile(clean, 0.25),
        "median": percentile(clean, 0.5),
        "p75": percentile(clean, 0.75),
        "max": clean[-1],
    }


def v1_midpoint_analytics(
    legacy_rows: list[dict[str, Any]],
    *,
    band: str,
    effective_from: str,
    selected_agreement_id_value: str | None = None,
) -> dict[str, Any]:
    rows = [
        row
        for row in legacy_rows
        if str(row.get("band") or row.get("chart_band") or "") == str(band)
        and str(row.get("quarter_start") or row.get("effective_from") or "") == str(effective_from)
    ]
    values = [
        float(row["midpoint_weekly_rate"])
        for row in rows
        if isinstance(row.get("midpoint_weekly_rate"), (int, float))
    ]
    selected_row = None
    if selected_agreement_id_value:
        selected_row = next(
            (row for row in rows if str(row.get("ae_id") or row.get("agreement_id") or "") == selected_agreement_id_value),
            None,
        )
    return {
        "source": "legacy_distribution_point_analysis",
        "band": band,
        "effective_from": effective_from,
        "selected_agreement_id": selected_agreement_id_value,
        "selected_value": selected_row.get("midpoint_weekly_rate") if selected_row else None,
        "comparator_observation_count": len(values),
        "comparator_council_count": len({str(row.get("ae_id") or row.get("agreement_id") or "") for row in rows}),
        "stats": stats(values),
    }


def v2_midpoint_analytics(row: dict[str, Any]) -> dict[str, Any]:
    points = selected_points(row)
    selected_value = points[0].get("weekly_rate") if points else None
    return {
        "source": CURVE_VIEW_ID,
        "band": row.get("standard_band"),
        "effective_from": row.get("effective_from"),
        "selected_agreement_id": selected_agreement_id(row),
        "selected_value": selected_value,
        "comparator_observation_count": row.get("curve_sample_count"),
        "comparator_council_count": row.get("curve_council_count"),
        "stats": {
            "count": row.get("curve_sample_count"),
            "min": row.get("curve_min"),
            "p25": row.get("curve_p25"),
            "median": row.get("curve_median"),
            "p75": row.get("curve_p75"),
            "max": row.get("curve_max"),
        },
    }


def compare_midpoint_parity(v1: dict[str, Any], v2: dict[str, Any], *, tolerance: float = 0.0001) -> dict[str, Any]:
    comparisons: dict[str, dict[str, Any]] = {}
    keys = [
        ("selected_value", v1.get("selected_value"), v2.get("selected_value")),
        ("comparator_observation_count", v1.get("comparator_observation_count"), v2.get("comparator_observation_count")),
        ("comparator_council_count", v1.get("comparator_council_count"), v2.get("comparator_council_count")),
    ]
    for stat_key in ["min", "p25", "median", "p75", "max"]:
        keys.append((stat_key, (v1.get("stats") or {}).get(stat_key), (v2.get("stats") or {}).get(stat_key)))
    for key, left, right in keys:
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            delta = abs(float(left) - float(right))
            match = delta <= tolerance
        else:
            delta = None
            match = left == right
        comparisons[key] = {
            "v1": left,
            "v2": right,
            "delta": delta,
            "match": match,
        }
    ok = all(item["match"] for item in comparisons.values())
    return {
        "ok": ok,
        "tolerance": tolerance,
        "comparisons": comparisons,
        "likely_difference_reasons": []
        if ok
        else [
            "different upstream source or governance filter",
            "different cohort definition",
            "different date basis",
            "different blocked-row handling",
            "different value field or percentile method",
        ],
    }
