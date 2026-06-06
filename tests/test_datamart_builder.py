from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_datamarts.py"
spec = importlib.util.spec_from_file_location("build_datamarts_module", SCRIPT)
build_datamarts_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = build_datamarts_module
spec.loader.exec_module(build_datamarts_module)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_minimal_root(tmp_path: Path) -> Path:
    (tmp_path / "canonical").mkdir()
    (tmp_path / "registers").mkdir()
    (tmp_path / "wiki").mkdir()
    (tmp_path / "data" / "reference" / "cohorts").mkdir(parents=True)
    (tmp_path / "data" / "bronze" / "phase1_source_build" / "candidate_agreements").mkdir(parents=True)
    (tmp_path / "data" / "reference" / "cohorts" / "cohort-nomenclature.yaml").write_text(
        "schema_version: '0.1'\ncohorts:\n  standard_band_core:\n    label: Standard band core\n",
        encoding="utf-8",
    )
    write_csv(
        tmp_path / "data" / "reference" / "victorian-council-master.csv",
        [
            {
                "council_key": "EXAMPLE",
                "short_name": "Example",
                "long_name": "Example Shire Council",
                "status": "active",
                "is_active": "True",
                "council_category": "Small shire",
                "council_type": "shire",
                "official_name": "EXAMPLE SHIRE",
                "spatial_name": "Example",
                "spatial_key": "EXAMPLE",
                "map_join_key": "EXAMPLE",
                "lga_code": "299",
                "abs_lga_code_2025": "29999",
                "abs_lga_name_2025": "Example",
                "abs_area_albers_sqkm": "10",
                "office_township": "Example",
                "office_lat": "-37.0",
                "office_lon": "145.0",
                "vif_metropolitan_region": "",
                "vif_regional_partnership": "Example Region",
                "lgprf_group": "Small Shire",
                "vgccc_region": "Country",
                "has_abs_asgs": "True",
            }
        ],
        [
            "council_key",
            "short_name",
            "long_name",
            "status",
            "is_active",
            "council_category",
            "council_type",
            "official_name",
            "spatial_name",
            "spatial_key",
            "map_join_key",
            "lga_code",
            "abs_lga_code_2025",
            "abs_lga_name_2025",
            "abs_area_albers_sqkm",
            "office_township",
            "office_lat",
            "office_lon",
            "vif_metropolitan_region",
            "vif_regional_partnership",
            "lgprf_group",
            "vgccc_region",
            "has_abs_asgs",
        ],
    )
    (tmp_path / "data" / "bronze" / "phase1_source_build" / "candidate_agreements" / "candidate_agreements.json").write_text(
        "[]",
        encoding="utf-8",
    )
    write_csv(
        tmp_path / "registers" / "source-document-register.csv",
        [],
        [
            "source_document_id",
            "source_name",
            "source_type",
            "source_origin",
            "fetched_at",
            "content_hash",
            "frozen_path",
            "file_size_bytes",
            "source_status",
            "serviceability_status",
            "discovery_reference",
            "notes",
        ],
    )
    return tmp_path


def write_test_council_master(root: Path, councils: list[tuple[str, str, str]]) -> None:
    master_path = root / "data" / "reference" / "victorian-council-master.csv"
    with master_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        template = next(reader)
    rows = []
    for index, (key, short_name, long_name) in enumerate(councils, start=1):
        row = {field: "" for field in fieldnames}
        row.update(template)
        row.update(
            {
                "council_key": key,
                "short_name": short_name,
                "long_name": long_name,
                "official_name": long_name.upper(),
                "spatial_name": short_name,
                "spatial_key": key,
                "map_join_key": key,
                "lga_code": str(290 + index),
                "abs_lga_code_2025": str(29990 + index),
                "abs_lga_name_2025": short_name,
            }
        )
        rows.append(row)
    write_csv(master_path, rows, fieldnames)


def write_curve_fixture(root: Path) -> None:
    write_test_council_master(
        root,
        [
            ("ALPHA", "Alpha", "Alpha Shire Council"),
            ("BETA", "Beta", "Beta City Council"),
            ("GAMMA", "Gamma", "Gamma Borough Council"),
        ],
    )
    fixtures = [
        (
            "ae111111",
            "Alpha Shire Council Enterprise Agreement",
            [
                ("A", 1000),
                ("B", 1100),
                ("C", 1300),
            ],
        ),
        (
            "ae222222",
            "Beta City Council Enterprise Agreement",
            [
                ("A", 900),
                ("B", 1000),
                ("C", 1100),
                ("D", 1200),
                ("E", 1400),
                ("F", 1600),
            ],
        ),
        (
            "ae333333",
            "Gamma Borough Council Enterprise Agreement",
            [
                ("A", 950),
                ("B", 1500),
            ],
        ),
    ]
    for agreement_id, source_name, levels in fixtures:
        rows = "\n".join(
            f"              - {{band: '5', level: '{level}', weekly_rate: {rate}}}"
            for level, rate in levels
        )
        (root / "canonical" / f"{agreement_id}.yaml").write_text(
            f"""
agreement_id: {agreement_id}
source_name: {source_name}
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            rows:
{rows}
""",
            encoding="utf-8",
        )


def test_initial_datamart_contracts_exist():
    assert (ROOT / "docs" / "datamarts" / "initial-datamart-suite.md").exists()
    for mart_id in build_datamarts_module.MART_IDS:
        path = ROOT / "docs" / "datamarts" / "contracts" / f"{mart_id}.md"
        assert path.exists(), mart_id
        assert "Safety Rules" in path.read_text(encoding="utf-8")


def test_governed_canonical_contracts_exist():
    assert (ROOT / "docs" / "governed_canonical" / "governed-canonical-layer.md").exists()
    for dataset_id in build_datamarts_module.GOVERNED_CANONICAL_IDS:
        path = ROOT / "docs" / "governed_canonical" / "contracts" / f"{dataset_id}.md"
        assert path.exists(), dataset_id
        assert "Safety Rules" in path.read_text(encoding="utf-8")


def test_pay_position_mart_does_not_use_unpromoted_extraction(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  pay_tables:
    status: done
    tables:
      - table_title: Raw extracted table
        rows:
          - {band: '1', level: 'A', weekly_rate: 1000}
  uplifts:
    status: not_started
    data:
      periods: []
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    status = json.loads((out / "pay_position_mart_status.json").read_text(encoding="utf-8"))
    governed_status = json.loads((root / "data" / "governed_canonical" / "pay_rows_status.json").read_text(encoding="utf-8"))
    assert governed_status["status"] == "blocked"
    assert status["status"] == "blocked"
    assert "sections.uplifts" in status["blocked_reasons"][0]
    assert not (root / "data" / "governed_canonical" / "pay_rows.csv").exists()
    assert not (out / "pay_position_mart.csv").exists()


def test_missing_governed_rate_is_blocker_not_absence_or_zero(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    status: done
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            table_title: Governed table with missing value
            source_page: 12
            source_clause: Schedule A
            effective_from: '2026-07-01'
            rate_kind: weekly
            rows:
              - {band: '1', level: 'A', classification_key: band_01_level_A}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    mart = json.loads((out / "pay_position_mart.json").read_text(encoding="utf-8"))
    governed = json.loads((root / "data" / "governed_canonical" / "pay_rows.json").read_text(encoding="utf-8"))
    mart_status = json.loads((out / "pay_position_mart_status.json").read_text(encoding="utf-8"))
    governed_row = governed["rows"][0]
    row = mart["rows"][0]
    assert governed_row["source_section_path"] == "sections.uplifts.data.periods[0].pay_table.rows[0]"
    assert governed_row["governed_canonical_status"] == "governed"
    assert "data/governed_canonical/pay_rows.csv" in mart_status["inputs"]
    assert row["governed_rate_value"] is None
    assert row["governed_canonical_status"] == "governed"
    assert row["value_status"] == "blocked_missing_governed_rate_value"
    assert row["governed_rate_value"] != 0


def test_accepted_uplift_suggestion_alone_does_not_populate_uplift_mart(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplift_rules:
    status: done
    data:
      accepted:
        document:
          ae_id: ae123456
          council: Example Shire Council
          timing_pattern: annual_fixed_date
          rules:
            - period_label: Year 1
              quantum: 3%
              quantum_type: fixed_pct
              effective_date: '2026-07-01'
              source_page: 9
  uplifts:
    status: not_started
    data:
      periods: []
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    status = json.loads((out / "uplift_timing_mart_status.json").read_text(encoding="utf-8"))
    governed_status = json.loads((root / "data" / "governed_canonical" / "uplift_rules_status.json").read_text(encoding="utf-8"))
    assert governed_status["status"] == "blocked"
    assert status["status"] == "blocked"
    assert "sections.uplifts" in status["blocked_reasons"][0]
    assert not (out / "uplift_timing_mart.csv").exists()


def test_entitlement_summary_mart_blocks_without_governed_entitlements(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  clauses:
    status: not_started
    data: null
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    status = json.loads((out / "entitlement_summary_mart_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "blocked"
    assert any("No reviewed/governed entitlement" in reason for reason in status["blocked_reasons"])


def test_entitlement_definition_overrides_apply_to_governed_items(tmp_path):
    root = make_minimal_root(tmp_path)
    exemplar_path = root / "wiki" / "artifacts" / "downstream-analysis-exemplars" / "ballarat-entitlement-benchmark-exemplar.json"
    exemplar_path.parent.mkdir(parents=True, exist_ok=True)
    exemplar_path.write_text(
        json.dumps(
            {
                "artifact_id": "ballarat-entitlement-benchmark-exemplar",
                "categories": [
                    {
                        "category_id": "leave",
                        "label": "Leave",
                        "entitlements": [
                            {
                                "entitlement_id": "leave-test",
                                "entitlement_label": "Test Leave",
                                "definition": "Rough exemplar wording.",
                                "scope": {"scope": "standard_employees"},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    override_path = root / "data" / "review" / "entitlement_definition_overrides.json"
    override_path.parent.mkdir(parents=True, exist_ok=True)
    override_path.write_text(
        json.dumps({"overrides": {"leave-test": {"definition": "Curated working definition."}}}),
        encoding="utf-8",
    )

    rows = build_datamarts_module.build_governed_entitlement_items(root)

    assert rows[0]["definition"] == "Curated working definition."


def test_all_declared_outputs_write_status_files_and_summary_details(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    status: done
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          uplift_rule_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            table_title: Governed table
            source_page: 12
            source_clause: Schedule A
            rows:
              - {band: '1', level: 'A', weekly_rate: 1000}
          uplift_rule:
            source_rule_id: '2026-07-01'
            source_quantum: '3%'
            source_quantum_type: fixed_pct
            resolved_pct: 3
            resolved_basis: source_quantum
        - effective_from: '2027-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            table_title: Governed table
            source_page: 14
            source_clause: Schedule A
            rows:
              - {band: '1', level: 'A', weekly_rate: 1030}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    governed_root = root / "data" / "governed_canonical"
    for dataset_id in build_datamarts_module.GOVERNED_CANONICAL_IDS:
        assert (governed_root / f"{dataset_id}_status.json").exists(), dataset_id
    for mart_id in build_datamarts_module.MART_IDS:
        assert (out / f"{mart_id}_status.json").exists(), mart_id

    governed_summary = (governed_root / "governed_canonical_build_summary.md").read_text(encoding="utf-8")
    datamart_summary = (out / "datamart_build_summary.md").read_text(encoding="utf-8")
    assert "Per-Dataset Build Details" in governed_summary
    assert "Per-Mart Build Details" in datamart_summary
    assert "Governance status coverage" in datamart_summary


def test_pay_structure_singleton_range_builds_metric_bundle(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            rows:
              - {band: '5', level: 'A', weekly_rate: 1000}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    point = json.loads((out / "pay_rate_point_mart.json").read_text(encoding="utf-8"))["rows"][0]
    summary = json.loads((out / "pay_range_summary_mart.json").read_text(encoding="utf-8"))["rows"][0]
    progression = json.loads((out / "pay_progression_service_year_mart.json").read_text(encoding="utf-8"))["rows"]
    distribution = json.loads((out / "pay_distribution_point_mart.json").read_text(encoding="utf-8"))["rows"]
    by_year = {row["service_horizon_year"]: row for row in progression}
    midpoint = next(row for row in distribution if row["comparison_metric"] == "range_midpoint_rate")
    year_6 = next(row for row in distribution if row["comparison_metric"] == "service_year_6_rate")

    assert point["range_role"] == "singleton"
    assert summary["entry_weekly_rate"] == 1000
    assert summary["capacity_weekly_rate"] == 1000
    assert summary["range_midpoint_weekly_rate"] == 1000
    assert summary["has_singleton_rate"] is True
    for year in range(1, 7):
        assert by_year[year]["weekly_rate_at_service_year"] == 1000
        assert by_year[year]["actual_step_count"] == 1
        assert by_year[year]["ordinal_position_resolved"] == 1
        assert by_year[year]["resolved_level_label"] == "A"
        assert by_year[year]["resolved_value_mode"] == "capacity_carry_forward"
        assert by_year[year]["capacity_carry_forward"] is True
    assert midpoint["entry_weekly_rate"] == 1000
    assert midpoint["capacity_weekly_rate"] == 1000
    assert midpoint["service_year_6_weekly_rate"] == 1000
    assert year_6["service_horizon_label"] == "Year 6 service-horizon rate, capacity carried forward from Level A"
    assert "Level 6" not in year_6["service_horizon_label"]


def test_pay_structure_multistep_midpoint_step_mean_and_y1_to_y6(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            rows:
              - {band: '5', level: 'A', weekly_rate: 1000}
              - {band: '5', level: 'B', weekly_rate: 1100}
              - {band: '5', level: 'C', weekly_rate: 1300}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    points = json.loads((out / "pay_rate_point_mart.json").read_text(encoding="utf-8"))["rows"]
    roles = {row["standard_level"]: row["range_role"] for row in points}
    summary = json.loads((out / "pay_range_summary_mart.json").read_text(encoding="utf-8"))["rows"][0]
    progression = json.loads((out / "pay_progression_service_year_mart.json").read_text(encoding="utf-8"))["rows"]
    by_year = {row["service_year_index"]: row for row in progression}

    assert roles == {"A": "entry", "B": "internal_step", "C": "capacity"}
    assert summary["range_midpoint_weekly_rate"] == 1150
    assert round(summary["step_mean_weekly_rate"], 4) == 1133.3333
    assert summary["range_midpoint_weekly_rate"] != summary["step_mean_weekly_rate"]
    assert by_year[1]["weekly_rate_at_service_year"] == 1000
    assert by_year[2]["weekly_rate_at_service_year"] == 1100
    assert by_year[3]["weekly_rate_at_service_year"] == 1300
    assert by_year[6]["weekly_rate_at_service_year"] == 1300
    assert by_year[3]["calculation_status"] == "calculated_from_level_ordinal_estimate"
    assert by_year[1]["service_horizon_year"] == 1
    assert by_year[1]["ordinal_position_resolved"] == 1
    assert by_year[1]["resolved_level_label"] == "A"
    assert by_year[1]["resolved_value_mode"] == "exact_level_point"
    assert by_year[6]["service_horizon_year"] == 6
    assert by_year[6]["actual_step_count"] == 3
    assert by_year[6]["ordinal_position_resolved"] == 3
    assert by_year[6]["resolved_level_label"] == "C"
    assert by_year[6]["resolved_value_mode"] == "capacity_carry_forward"
    assert by_year[6]["capacity_reached"] is True
    assert by_year[6]["capacity_carry_forward"] is True
    assert by_year[6]["ordinal_position_resolved"] != 6


def test_pay_structure_six_step_range_year_six_resolves_exact_level(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            rows:
              - {band: '5', level: 'A', weekly_rate: 1000}
              - {band: '5', level: 'B', weekly_rate: 1100}
              - {band: '5', level: 'C', weekly_rate: 1200}
              - {band: '5', level: 'D', weekly_rate: 1300}
              - {band: '5', level: 'E', weekly_rate: 1400}
              - {band: '5', level: 'F', weekly_rate: 1500}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    progression = json.loads((out / "pay_progression_service_year_mart.json").read_text(encoding="utf-8"))["rows"]
    distribution = json.loads((out / "pay_distribution_point_mart.json").read_text(encoding="utf-8"))["rows"]
    year_6 = next(row for row in progression if row["service_horizon_year"] == 6)
    distribution_year_6 = next(row for row in distribution if row["comparison_metric"] == "service_year_6_rate")

    assert year_6["weekly_rate_at_service_year"] == 1500
    assert year_6["actual_step_count"] == 6
    assert year_6["ordinal_position_resolved"] == 6
    assert year_6["resolved_level_label"] == "F"
    assert year_6["resolved_value_mode"] == "exact_level_point"
    assert year_6["capacity_reached"] is True
    assert year_6["capacity_carry_forward"] is False
    assert distribution_year_6["service_horizon_label"] == "Year 6 service-horizon rate, exact Level F point"


def test_pay_structure_ambiguous_grouping_creates_quality_issue(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            rows:
              - {band: '5', level: 'A', weekly_rate: 1000}
              - {band: '5', level: 'A', weekly_rate: 1100}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    points = json.loads((out / "pay_rate_point_mart.json").read_text(encoding="utf-8"))["rows"]
    issues = json.loads((out / "data_quality_issue_mart.json").read_text(encoding="utf-8"))["rows"]
    assert {row["calculation_status"] for row in points} == {"blocked_ambiguous_range_grouping"}
    assert any(row["issue_type"] == "ambiguous_range_grouping" for row in issues)


def test_non_deterministic_progression_blocks_year_values(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          progression_basis: competency_based
          progression_rule_status: reviewed
          pay_table:
            rows:
              - {band: '5', level: 'A', weekly_rate: 1000}
              - {band: '5', level: 'B', weekly_rate: 1100}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    progression = json.loads((out / "pay_progression_service_year_mart.json").read_text(encoding="utf-8"))["rows"]
    year_1 = next(row for row in progression if row["service_year_index"] == 1)
    issues = json.loads((out / "data_quality_issue_mart.json").read_text(encoding="utf-8"))["rows"]
    assert year_1["weekly_rate_at_service_year"] is None
    assert year_1["calculation_status"] == "blocked_non_deterministic_progression"
    assert any(row["issue_type"] == "blocked_non_deterministic_progression" for row in issues)


def test_metric_aware_distribution_declares_metric_and_bundle(tmp_path):
    root = make_minimal_root(tmp_path)
    (root / "canonical" / "ae123456.yaml").write_text(
        """
agreement_id: ae123456
source_name: Example Shire Council Enterprise Agreement
sections:
  uplifts:
    data:
      periods:
        - effective_from: '2026-07-01'
          pay_table_governed_at: '2026-05-07T00:00:00Z'
          pay_table:
            rows:
              - {band: '5', level: 'A', weekly_rate: 1000}
              - {band: '5', level: 'B', weekly_rate: 1100}
""",
        encoding="utf-8",
    )

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    rows = json.loads((out / "pay_distribution_point_mart.json").read_text(encoding="utf-8"))["rows"]
    metrics = {row["comparison_metric"] for row in rows}
    assert {"entry_rate", "capacity_rate", "range_midpoint_rate", "service_year_1_rate", "service_year_6_rate"} <= metrics
    assert all(row["comparison_metric"] for row in rows)
    midpoint = next(row for row in rows if row["comparison_metric"] == "range_midpoint_rate")
    assert midpoint["weekly_rate"] == 1050
    assert midpoint["entry_weekly_rate"] == 1000
    assert midpoint["capacity_weekly_rate"] == 1100
    assert midpoint["service_year_6_weekly_rate"] == 1100
    year_6 = next(row for row in rows if row["comparison_metric"] == "service_year_6_rate")
    assert year_6["service_horizon_year"] == 6
    assert year_6["resolved_value_mode"] == "capacity_carry_forward"
    assert year_6["resolved_level_label"] == "B"
    assert year_6["actual_step_count"] == 2
    assert year_6["capacity_carry_forward"] is True
    assert year_6["service_horizon_label"] == "Year 6 service-horizon rate, capacity carried forward from Level B"
    assert "Level 6" not in year_6["service_horizon_label"]


def test_service_horizon_curve_entry_only_uses_single_metric_universe(tmp_path):
    root = make_minimal_root(tmp_path)
    write_curve_fixture(root)

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    rows = json.loads((out / "pay_service_horizon_curve_view.json").read_text(encoding="utf-8"))["rows"]
    entry = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA" and row["service_horizon_window_id"] == "entry_only"
    )
    midpoint = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA" and row["service_horizon_window_id"] == "range_midpoint_only"
    )
    points = json.loads(entry["selected_council_points_json"])
    midpoint_points = json.loads(midpoint["selected_council_points_json"])

    assert entry["service_horizon_window_label"] == "Entry rate distribution"
    assert entry["included_metric_points"] == ["entry_rate"]
    assert entry["curve_sample_count"] == 3
    assert entry["curve_council_count"] == 3
    assert entry["weighting_method"] == "observation_weighted"
    assert points == [
        {
            "comparison_metric": "entry_rate",
            "service_horizon_year": None,
            "display_label": "Entry",
            "weekly_rate": 1000.0,
            "annual_rate": 52000.0,
            "resolved_level_label": None,
            "resolved_value_mode": None,
            "actual_step_count": None,
            "capacity_carry_forward": None,
            "capacity_reached": None,
            "calculation_status": "calculated_from_governed_points",
            "report_ready_status": "ready",
            "metric_caveat": None,
        }
    ]
    assert "Band 5" in entry["chart_title"]
    assert "Entry rate distribution" in entry["chart_title"]
    assert midpoint["service_horizon_window_label"] == "Range midpoint rate distribution"
    assert midpoint["included_metric_points"] == ["range_midpoint_rate"]
    assert midpoint_points[0]["comparison_metric"] == "range_midpoint_rate"
    assert midpoint_points[0]["weekly_rate"] == 1150.0
    assert "Range midpoint rate distribution" in midpoint["chart_title"]


def test_service_horizon_curve_entry_to_y3_and_capacity_duplication_control(tmp_path):
    root = make_minimal_root(tmp_path)
    write_curve_fixture(root)

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    distribution = json.loads((out / "pay_distribution_point_mart.json").read_text(encoding="utf-8"))["rows"]
    rows = json.loads((out / "pay_service_horizon_curve_view.json").read_text(encoding="utf-8"))["rows"]
    entry_to_y3 = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA" and row["service_horizon_window_id"] == "entry_to_y3"
    )
    entry_to_y6 = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA" and row["service_horizon_window_id"] == "entry_to_y6"
    )
    capacity_profile = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA" and row["service_horizon_window_id"] == "entry_to_capacity_profile"
    )

    y3_points = json.loads(entry_to_y3["selected_council_points_json"])
    y3_envelope = json.loads(entry_to_y3["horizon_envelope_json"])
    assert entry_to_y3["included_metric_points"] == [
        "entry_rate",
        "service_year_1_rate",
        "service_year_2_rate",
        "service_year_3_rate",
    ]
    assert [point["comparison_metric"] for point in y3_points] == entry_to_y3["included_metric_points"]
    assert [point["comparison_metric"] for point in y3_envelope] == entry_to_y3["included_metric_points"]
    assert [point["sample_count"] for point in y3_envelope] == [3, 3, 3, 3]
    assert entry_to_y3["selected_council_included_in_curve_sample"] is True
    assert entry_to_y3["curve_sample_count"] == 12
    assert entry_to_y3["curve_council_count"] == 3
    assert "Entry-to-Year-3 service-horizon distribution" in entry_to_y3["chart_title"]
    assert {row["cohort_id"] for row in distribution} >= {
        "all_governed",
        "benchmark_lane__standard_band_core",
        "council_type__shire",
    }

    benchmark_lane = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA"
        and row["service_horizon_window_id"] == "entry_to_y3"
        and row["cohort_id"] == "benchmark_lane__standard_band_core"
    )
    assert benchmark_lane["cohort_name"] == "Benchmark Lane: standard band core"
    assert benchmark_lane["curve_sample_count"] == 12
    assert benchmark_lane["curve_council_count"] == 3
    assert benchmark_lane["selected_council_included_in_curve_sample"] is True

    assert entry_to_y6["curve_sample_count"] == 21
    assert "capacity_rate" not in entry_to_y6["included_metric_points"]
    assert capacity_profile["curve_sample_count"] == 24
    assert "capacity_rate" in capacity_profile["included_metric_points"]
    assert "capacity_rate" in {point["comparison_metric"] for point in json.loads(capacity_profile["horizon_envelope_json"])}
    assert "entry_to_capacity_profile" in capacity_profile["comparator_envelope_json"]


def test_service_horizon_curve_y3_to_y6_carry_forward_has_safe_labels(tmp_path):
    root = make_minimal_root(tmp_path)
    write_curve_fixture(root)

    out = root / "out"
    build_datamarts_module.build_datamarts(root, out, generated_at="2026-05-07T00:00:00Z")

    rows = json.loads((out / "pay_service_horizon_curve_view.json").read_text(encoding="utf-8"))["rows"]
    y3_to_y6 = next(
        row
        for row in rows
        if row["selected_council_id"] == "ALPHA" and row["service_horizon_window_id"] == "y3_to_y6"
    )
    points = json.loads(y3_to_y6["selected_council_points_json"])
    y6 = next(point for point in points if point["comparison_metric"] == "service_year_6_rate")

    assert y3_to_y6["included_metric_points"] == [
        "service_year_3_rate",
        "service_year_4_rate",
        "service_year_5_rate",
        "service_year_6_rate",
    ]
    assert y3_to_y6["curve_sample_count"] == 12
    assert y6["service_horizon_year"] == 6
    assert y6["resolved_level_label"] == "C"
    assert y6["resolved_value_mode"] == "capacity_carry_forward"
    assert y6["actual_step_count"] == 3
    assert y6["capacity_carry_forward"] is True
    assert y6["display_label"] == "Y6 service-horizon, capacity carried forward from Level C"
    assert "Level 6" not in y6["display_label"]
