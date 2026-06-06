from __future__ import annotations

import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient

from benchmarking_data_factory.workbench.analysis_spatial_routes import (
    AnalysisSpatialRoutesDependencies,
    build_analysis_spatial_router,
)
from benchmarking_data_factory.workbench.pay_horizon_explorer import (
    PayHorizonCurveStore,
    build_chart_manifest,
    compare_midpoint_parity,
    curve_options,
    query_curve_sqlite_quarter,
    title_is_safe,
    v1_midpoint_analytics,
    v2_midpoint_analytics,
)


def curve_row(window_id="range_midpoint_only", label="Range midpoint rate distribution", metrics=None, points=None):
    metrics = metrics or ["range_midpoint_rate"]
    points = points or [
        {
            "comparison_metric": "range_midpoint_rate",
            "display_label": "Range midpoint rate",
            "weekly_rate": 1150.0,
            "resolved_level_label": None,
            "resolved_value_mode": None,
            "actual_step_count": None,
            "capacity_carry_forward": None,
            "calculation_status": "calculated_from_governed_points",
            "report_ready_status": "ready",
            "metric_caveat": None,
        }
    ]
    return {
        "curve_id": f"curve::all_governed::band_5::2026-07-01::{window_id}::payrange::ae111111::2026-07-01::band_5",
        "cohort_id": "all_governed",
        "cohort_name": "All governed comparable rows",
        "standard_band": "5",
        "effective_from": "2026-07-01",
        "effective_to": None,
        "service_horizon_window_id": window_id,
        "service_horizon_window_label": label,
        "included_metric_points": metrics,
        "included_service_horizon_years": [1, 2, 3] if window_id == "entry_to_y3" else [],
        "curve_sample_count": 3,
        "curve_council_count": 3,
        "weighting_method": "observation_weighted",
        "curve_min": 1000.0,
        "curve_p25": 1075.0,
        "curve_median": 1150.0,
        "curve_p75": 1250.0,
        "curve_max": 1350.0,
        "density_points_json": "[]",
        "comparator_envelope_json": json.dumps(
            {
                "curve_sample_count": 3,
                "curve_council_count": 3,
                "blocked_observation_count": 0,
                "included_metric_points": metrics,
            }
        ),
        "horizon_envelope_json": json.dumps(
            [
                {
                    "comparison_metric": metric,
                    "display_label": metric,
                    "sample_count": 3,
                    "council_count": 3,
                    "median": 1150.0,
                }
                for metric in metrics
            ]
        ),
        "selected_council_points_json": json.dumps(points),
        "selected_council_id": "ALPHA",
        "selected_council_name": "Alpha Shire Council",
        "selected_range_group_id": "payrange::ae111111::2026-07-01::band_5",
        "selected_classification_family": "band_5",
        "selected_council_included_in_curve_sample": True,
        "selected_council_min": 1150.0,
        "selected_council_max": 1150.0,
        "selected_council_position_summary": "selected_window_median_equals_curve_median",
        "chart_title": f"Band 5 {label} - All governed comparable rows",
        "caveat_status": "ready",
        "metric_caveats": ["Curve and selected dots are drawn from the same service_horizon_window metric universe."],
        "report_ready_status": "ready",
        "blocker_reason": None,
    }


def write_curve_payload(root, rows):
    target = root / "data" / "datamarts"
    target.mkdir(parents=True)
    (target / "council_profile_mart.json").write_text(
        json.dumps(
            {
                "schema_version": "test.v1",
                "mart_id": "council_profile_mart",
                "row_count": 2,
                "rows": [
                    {
                        "canonical_council_id": "ALPHA",
                        "canonical_council_name": "Alpha Shire Council",
                    },
                    {
                        "canonical_council_id": "OMEGA",
                        "canonical_council_name": "Omega Rural City Council",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (target / "pay_service_horizon_curve_view.json").write_text(
        json.dumps(
            {
                "schema_version": "test.v1",
                "mart_id": "pay_service_horizon_curve_view",
                "row_count": len(rows),
                "rows": rows,
            }
        ),
        encoding="utf-8",
    )
    (target / "pay_service_horizon_curve_view_status.json").write_text(
        json.dumps({"mart_id": "pay_service_horizon_curve_view", "status": "built", "row_count": len(rows)}),
        encoding="utf-8",
    )


def write_curve_sqlite(root, rows):
    target = root / "data" / "datamarts"
    target.mkdir(parents=True)
    path = target / "pay_service_horizon_curve_view.sqlite"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [("schema_version", "test.v1"), ("row_count", str(len(rows)))],
        )
        connection.execute(
            """
            CREATE TABLE curve_rows (
                row_index INTEGER PRIMARY KEY,
                standard_band TEXT,
                effective_from TEXT,
                effective_to TEXT,
                cohort_id TEXT,
                cohort_name TEXT,
                curve_council_count INTEGER,
                selected_council_id TEXT,
                selected_council_name TEXT,
                service_horizon_window_id TEXT,
                service_horizon_window_label TEXT,
                selected_range_group_id TEXT,
                row_json TEXT
            )
            """
        )
        for index, row in enumerate(rows):
            connection.execute(
                """
                INSERT INTO curve_rows (
                    row_index, standard_band, effective_from, effective_to, cohort_id, cohort_name,
                    curve_council_count, selected_council_id, selected_council_name,
                    service_horizon_window_id, service_horizon_window_label, selected_range_group_id, row_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    index,
                    row.get("standard_band"),
                    row.get("effective_from"),
                    row.get("effective_to"),
                    row.get("cohort_id"),
                    row.get("cohort_name"),
                    row.get("curve_council_count"),
                    row.get("selected_council_id"),
                    row.get("selected_council_name"),
                    row.get("service_horizon_window_id"),
                    row.get("service_horizon_window_label"),
                    row.get("selected_range_group_id"),
                    json.dumps(row),
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return path


def build_test_client(store):
    deps = AnalysisSpatialRoutesDependencies(
        build_uplift_rules_analysis=lambda **kwargs: {},
        build_pay_tables_analysis=lambda **kwargs: {},
        build_end_of_band_dollars_analysis=lambda **kwargs: {},
        build_review_learning_snapshot=lambda **kwargs: {},
        load_distribution_point_analysis_asset=lambda: None,
        materialize_distribution_point_analysis=lambda **kwargs: {},
        rebuild_analysis_data_set=lambda *args, **kwargs: {},
        build_council_geography_payload=lambda: {},
        pay_horizon_curve_store=store,
    )
    app = FastAPI()
    app.include_router(build_analysis_spatial_router(lambda: deps))
    return TestClient(app)


def test_pay_horizon_curve_endpoint_filters_read_only_view(tmp_path):
    rows = [
        curve_row(),
        curve_row("entry_only", "Entry rate distribution", ["entry_rate"]),
        curve_row(
            "entry_to_y3",
            "Entry-to-Year-3 service-horizon distribution",
            ["entry_rate", "service_year_1_rate", "service_year_2_rate", "service_year_3_rate"],
            points=[
                {"comparison_metric": "entry_rate", "display_label": "Entry", "weekly_rate": 1000.0},
                {"comparison_metric": "service_year_1_rate", "display_label": "Y1 service-horizon", "weekly_rate": 1000.0},
                {"comparison_metric": "service_year_2_rate", "display_label": "Y2 service-horizon", "weekly_rate": 1100.0},
                {"comparison_metric": "service_year_3_rate", "display_label": "Y3 service-horizon", "weekly_rate": 1300.0},
            ],
        ),
    ]
    write_curve_payload(tmp_path, rows)
    client = build_test_client(PayHorizonCurveStore(tmp_path))

    options = client.get("/api/analysis/pay-service-horizon-curve/options")
    assert options.status_code == 200
    assert "range_midpoint_only" in {
        item["service_horizon_window_id"] for item in options.json()["options"]["windows"]
    }
    assert options.json()["options"]["default_selection"]["service_horizon_window_id"] == "range_midpoint_only"
    councils = {item["selected_council_id"]: item for item in options.json()["options"]["councils"]}
    assert councils["ALPHA"]["has_pay_horizon_data"] is True
    assert councils["OMEGA"]["selected_council_name"] == "Omega Rural City Council"
    assert councils["OMEGA"]["has_pay_horizon_data"] is False
    reference = {item["council_key"]: item for item in options.json()["options"]["council_reference"]}
    assert reference["ALPHA"]["council_name"] == "Alpha Shire Council"
    assert reference["OMEGA"]["council_name"] == "Omega Rural City Council"

    response = client.get(
        "/api/analysis/pay-service-horizon-curve",
        params={
            "standard_band": "5",
            "effective_from": "2026-07-01",
            "cohort_id": "all_governed",
            "selected_council_id": "ALPHA",
            "service_horizon_window_id": "entry_to_y3",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["filtered_count"] == 1
    assert body["rows"][0]["included_metric_points"] == [
        "entry_rate",
        "service_year_1_rate",
        "service_year_2_rate",
        "service_year_3_rate",
    ]


def test_curve_options_only_exposes_cohorts_with_n_over_15():
    rows = []
    for index in range(16):
        rows.append(
            {
                "cohort_id": "large_curve_cohort",
                "cohort_name": "Large curve cohort",
                "selected_council_id": f"LARGE_{index}",
                "selected_council_name": f"Large Council {index}",
                "standard_band": "5",
                "effective_from": "2026-07-01",
                "service_horizon_window_id": "range_midpoint_only",
                "service_horizon_window_label": "Range midpoint rate distribution",
                "included_metric_points": ["range_midpoint_rate"],
                "included_service_horizon_years": [],
                "curve_council_count": 16,
            }
        )
    for index in range(15):
        rows.append(
            {
                "cohort_id": "small_curve_cohort",
                "cohort_name": "Small curve cohort",
                "selected_council_id": f"SMALL_{index}",
                "selected_council_name": f"Small Council {index}",
                "standard_band": "5",
                "effective_from": "2026-07-01",
                "service_horizon_window_id": "range_midpoint_only",
                "service_horizon_window_label": "Range midpoint rate distribution",
                "included_metric_points": ["range_midpoint_rate"],
                "included_service_horizon_years": [],
                "curve_council_count": 15,
            }
        )

    options = curve_options(rows, [])
    cohorts = {item["cohort_id"]: item for item in options["cohorts"]}

    assert "large_curve_cohort" in cohorts
    assert cohorts["large_curve_cohort"]["cohort_council_count"] == 16
    assert "small_curve_cohort" not in cohorts


def test_curve_options_default_prefers_latest_robust_midpoint_row():
    sparse_latest = {
        **curve_row(),
        "effective_from": "2028-07-01",
        "curve_council_count": 2,
        "curve_sample_count": 2,
        "selected_council_id": "SPARSE",
        "selected_council_name": "Sparse Council",
    }
    robust_older = {
        **curve_row(),
        "effective_from": "2026-07-01",
        "curve_council_count": 16,
        "curve_sample_count": 16,
        "selected_council_id": "ROBUST",
        "selected_council_name": "Robust Council",
    }

    options = curve_options([sparse_latest, robust_older], [])

    assert options["default_selection"]["selected_council_id"] == "ROBUST"
    assert options["default_selection"]["effective_from"] == "2026-07-01"


def test_quarter_curve_resolves_latest_active_governed_rates(tmp_path):
    def row_for(council_id, council_name, agreement_id, effective_from, effective_to, rate):
        row = curve_row()
        row.update(
            {
                "selected_council_id": council_id,
                "selected_council_name": council_name,
                "selected_range_group_id": f"payrange::{agreement_id}::{effective_from}::{effective_to}::band_5",
                "effective_from": effective_from,
                "effective_to": None,
                "curve_council_count": 1,
                "curve_sample_count": 1,
                "curve_min": rate,
                "curve_p25": rate,
                "curve_median": rate,
                "curve_p75": rate,
                "curve_max": rate,
                "selected_council_min": rate,
                "selected_council_max": rate,
                "selected_council_points_json": json.dumps(
                    [
                        {
                            "comparison_metric": "range_midpoint_rate",
                            "display_label": "Range midpoint rate",
                            "weekly_rate": rate,
                            "calculation_status": "calculated_from_governed_points",
                            "report_ready_status": "ready",
                        }
                    ]
                ),
            }
        )
        return row

    path = write_curve_sqlite(
        tmp_path,
        [
            row_for("ALPHA", "Alpha Shire Council", "ae-alpha", "2025-07-01", "2026-06-30", 1100.0),
            row_for("ALPHA", "Alpha Shire Council", "ae-alpha", "2026-07-01", "open_ended", 1200.0),
            row_for("BETA", "Beta City Council", "ae-beta", "2025-10-01", "open_ended", 1300.0),
        ],
    )

    rows, filtered_count, _, _ = query_curve_sqlite_quarter(
        path,
        standard_band="5",
        quarter_start="2026-07-01",
        cohort_id="all_governed",
        selected_council_id="ALPHA",
        service_horizon_window_id="range_midpoint_only",
        limit=10,
    )

    assert filtered_count == 1
    assert rows[0]["quarter_start"] == "2026-07-01"
    assert rows[0]["curve_council_count"] == 2
    assert rows[0]["curve_sample_count"] == 2
    assert rows[0]["curve_median"] == 1250.0
    assert rows[0]["selected_council_min"] == 1200.0


def test_v2_midpoint_parity_matches_legacy_midpoint_fixture():
    legacy_rows = [
        {"ae_id": "ae111111", "band": "5", "quarter_start": "2026-07-01", "midpoint_weekly_rate": 1150.0},
        {"ae_id": "ae222222", "band": "5", "quarter_start": "2026-07-01", "midpoint_weekly_rate": 1000.0},
        {"ae_id": "ae333333", "band": "5", "quarter_start": "2026-07-01", "midpoint_weekly_rate": 1350.0},
    ]
    v1 = v1_midpoint_analytics(
        legacy_rows,
        band="5",
        effective_from="2026-07-01",
        selected_agreement_id_value="ae111111",
    )
    v2 = v2_midpoint_analytics(curve_row())
    parity = compare_midpoint_parity(v1, v2)

    assert parity["ok"] is True
    assert all(item["match"] for item in parity["comparisons"].values())


def test_chart_manifest_and_title_safety_require_metric_universe():
    row = curve_row()
    manifest = build_chart_manifest(row, view_mode="single_point", comparison_metric="range_midpoint_rate")

    assert manifest["chart_version"] == "pay_horizon_distribution_explorer.v2_prototype"
    assert manifest["comparison_metric"] == "range_midpoint_rate"
    assert manifest["service_horizon_window_id"] == "range_midpoint_only"
    assert manifest["title_safe"] is True
    assert title_is_safe("Band 5 distribution") is False
    assert title_is_safe("Band 5 range midpoint distribution") is True


def test_capacity_carry_forward_point_does_not_create_fake_level_6():
    row = curve_row(
        "y3_to_y6",
        "Year-3-to-Year-6 service-horizon distribution",
        ["service_year_3_rate", "service_year_4_rate", "service_year_5_rate", "service_year_6_rate"],
        points=[
            {
                "comparison_metric": "service_year_6_rate",
                "service_horizon_year": 6,
                "display_label": "Y6 service-horizon, capacity carried forward from Level C",
                "weekly_rate": 1300.0,
                "resolved_level_label": "C",
                "resolved_value_mode": "capacity_carry_forward",
                "actual_step_count": 3,
                "capacity_carry_forward": True,
                "capacity_reached": True,
                "calculation_status": "calculated_from_level_ordinal_estimate",
                "report_ready_status": "caveated_estimate_not_report_ready",
                "metric_caveat": "Using the service-horizon estimate model.",
            }
        ],
    )
    point = json.loads(row["selected_council_points_json"])[0]

    assert point["resolved_value_mode"] == "capacity_carry_forward"
    assert point["resolved_level_label"] == "C"
    assert "Level 6" not in point["display_label"]
