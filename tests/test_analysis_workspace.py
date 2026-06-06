from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
import yaml

from benchmarking_data_factory.workbench import analysis_workspace


def test_uplift_rules_analysis_combines_governed_sets(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {
        "aetest01": "Example Council Agreement",
        "aetest02": "Second Council Agreement",
    })
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {
            "matched_lga_names": "Example" if ae_id == "aetest01" else "Second"
        },
    )

    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    status: in_progress\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          uplift_rule_governed_at: '2026-04-24T01:00:00Z'\n"
        "          uplift_rule:\n"
        "            pct_component: 3.0\n"
        "            dollar_component: 40\n"
        "            dollar_basis: weekly\n"
        "            floor_dollar: 40\n"
        "            pattern_archetype: pct_OR_floor\n"
        "            pattern_variant: 3% or $40 weekly\n"
        "        - effective_from: '2026-07-01'\n"
        "          uplift_rule_governed_at: '2026-04-24T01:05:00Z'\n"
        "          uplift_rule:\n"
        "            pct_component: 90.0\n"
        "            dollar_component: 50\n"
        "            dollar_basis: weekly\n"
        "            rate_cap_component: 3.0\n"
        "            floor_dollar: 50\n"
        "            floor_pct: 3.0\n"
        "            pattern_archetype: rate_cap_plus_margin\n"
        "            pattern_variant: 90% of the official rate cap, or 3.0% or $50 per week, whichever is greater\n"
        "        - effective_from: '2027-07-01'\n"
        "          uplift_rule: null\n",
        encoding="utf-8",
    )
    (tmp_path / "aetest02.yaml").write_text(
        "agreement_id: aetest02\n"
        "source_name: Second Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    status: not_started\n"
        "    data: null\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/uplift-rules")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["set_id"] == "set_1_uplift_rules"
    assert body["summary"]["agreements_scanned"] == 2
    assert body["summary"]["agreements_with_governed_periods"] == 1
    assert body["summary"]["agreements_with_uplift_rules"] == 1
    assert body["summary"]["governed_periods"] == 3
    assert body["summary"]["rules"] == 2
    assert body["summary"]["periods_without_rule"] == 1
    assert body["summary"]["rate_cap_rules"] == 1
    assert body["summary"]["floor_rules"] == 2
    assert body["summary"]["earliest_effective_from"] == "2025-07-01"
    assert body["summary"]["latest_effective_from"] == "2026-07-01"
    assert [row["effective_from"] for row in body["rows"]] == ["2025-07-01", "2026-07-01"]
    assert body["rows"][0]["canonical_lga_short_name"] == "Example"
    cap_row = body["rows"][1]
    assert cap_row["normalised_components"]["raw_pct_component"] == 90.0
    assert cap_row["normalised_components"]["internal_pct_component"] == 3.0
    assert cap_row["normalised_components"]["external_cap_share"] == 0.9
    assert cap_row["normalised_components"]["external_cap_pct"] == 2.75
    assert cap_row["normalised_components"]["external_formula_pct"] == 2.475
    assert cap_row["normalised_components"]["resolved_pct"] == 3.0
    assert cap_row["normalised_components"]["resolved_basis"] == "internal_pct_floor"
    assert {item["pattern"] for item in body["patterns"]} == {"pct_OR_floor", "rate_cap_plus_margin"}


def test_pay_tables_analysis_flattens_governed_rows(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "DISTRIBUTION_POINT_ANALYSIS_JSON", tmp_path / "distribution-point-analysis.json")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )

    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    status: in_progress\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            table_title: Base salaries\n"
        "            source_page: 44\n"
        "            source_clause: Appendix A\n"
        "            effective_from: '2025-07-01'\n"
        "            to_date: '2026-06-30'\n"
        "            rate_kind: weekly\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', title: Officer, weekly_rate: 1000, annual_rate: 52000}\n"
        "              - {band: '1', level: 'B', title: Senior Officer, weekly_rate: 1100, annual_rate: 57200}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/pay-tables")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["set_id"] == "set_2_pay_tables"
    assert body["summary"]["agreements_scanned"] == 1
    assert body["summary"]["agreements_with_governed_pay_tables"] == 1
    assert body["summary"]["tables"] == 1
    assert body["summary"]["rows"] == 2
    assert body["summary"]["weekly_rate_rows"] == 2
    assert body["summary"]["non_weekly_rows_skipped"] == 0
    assert [row["level"] for row in body["rows"]] == ["A", "B"]
    first = body["rows"][0]
    assert first["canonical_lga_short_name"] == "Example"
    assert first["table_title"] == "Base salaries"
    assert first["source_page"] == 44
    assert first["weekly_rate"] == 1000.0
    assert first["weekly_rate_basis"] == "weekly_rate"
    assert first["standard_band"] == "1"
    assert first["standard_level"] == "A"
    assert first["classification_key"] == "band_01_level_A"
    assert first["classification_label"] == "Band 1 Level A"
    assert first["classification_sort"] == 101
    assert "annual_rate" not in first
    assert body["summary"]["weekly_rate_basis_counts"] == {"weekly_rate": 2}
    assert body["patterns"] == [{"pattern": "weekly_rate", "count": 2}]


def test_pay_tables_analysis_reports_unused_candidate_pages(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "DISTRIBUTION_POINT_ANALYSIS_JSON", tmp_path / "distribution-point-analysis.json")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )
    page_text = {
        11: "Schedule of Allowances Meal allowance $10.00 Travel allowance $20.00 Tool allowance $30.00",
        12: "Quantum and Timing Wage increases 1 July 2026 3.0% rate cap pay increase",
        13: "Hourly Rate Casual classification $35.00 $36.00 $37.00",
    }
    monkeypatch.setattr(main, "extract_page_text", lambda ae_id, page_num: page_text.get(page_num, ""))

    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "overview:\n"
        "  likely_pay_table_pages: [10, 11, 12, 13]\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: done\n"
        "    tables:\n"
        "      - table_title: Standard rates\n"
        "        source_page: 10\n"
        "        effective_from: '2025-07-01'\n"
        "        rate_kind: weekly\n"
        "        rows:\n"
        "          - {band: '1', level: 'A', weekly_rate: 1000}\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            table_title: Standard rates\n"
        "            source_page: 10\n"
        "            effective_from: '2025-07-01'\n"
        "            rate_kind: weekly\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', weekly_rate: 1000}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/pay-tables")

    assert response.status_code == 200, response.text
    quality = response.json()["candidate_quality"]
    assert quality["summary"]["candidate_pages"] == 4
    assert quality["summary"]["used_candidate_pages"] == 1
    assert quality["summary"]["unused_candidate_pages"] == 3
    reasons = {item["page"]: item["reason"] for item in quality["false_positive_pages"]}
    assert reasons[11] == "allowance_or_penalty_schedule"
    assert reasons[12] == "uplift_clause_overlap"
    assert reasons[13] == "hourly_only"
    assert {item["rule"] for item in quality["recommendations"]} >= {
        "downrank_allowance_dollar_density",
        "separate_uplift_clause_candidates",
        "drop_hourly_only_pages",
    }


def test_distribution_point_analysis_materialises_quarter_band_points(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "DISTRIBUTION_POINT_ANALYSIS_JSON", tmp_path / "distribution-point-analysis.json")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )

    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    status: in_progress\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            table_title: Base salaries\n"
        "            source_pages: [44, 45]\n"
        "            source_clause: Appendix A\n"
        "            effective_from: '2025-07-01'\n"
        "            to_date: '2025-12-31'\n"
        "            rate_kind: weekly\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', title: Officer, weekly_rate: 1000}\n"
        "              - {band: '1', level: 'B', title: Senior Officer, weekly_rate: 1100}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/distribution-point-analysis?force_refresh=true")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["set_id"] == "set_3_distribution_point_analysis"
    assert body["schema_version"] == "distribution_point_analysis.v1"
    assert body["summary"]["source_pay_table_rows"] == 2
    assert body["summary"]["distribution_points"] == 2
    assert body["summary"]["earliest_quarter_start"] == "2025-07-01"
    assert body["summary"]["latest_quarter_start"] == "2025-10-01"
    assert body["asset"]["path"] == str(tmp_path / "distribution-point-analysis.json")
    assert (tmp_path / "distribution-point-analysis.json").exists()
    assert body["report_asset"]["validation"]["valid"] is True
    assert (tmp_path / "distribution-point-analysis.asset.json").exists()
    first = body["rows"][0]
    assert first["analysis_id"] == "dpa::aetest01::2025-07-01::band_1"
    assert first["canonical_lga_short_name"] == "Example"
    assert first["band"] == "1"
    assert first["min_level"] == "A"
    assert first["min_weekly_rate"] == 1000.0
    assert first["max_level"] == "B"
    assert first["max_weekly_rate"] == 1100.0
    assert first["midpoint_weekly_rate"] == 1050.0
    assert first["max_level_point_weekly_rate"] == 1100.0
    assert first["source_pages"] == [44, 45]
    assert first["source_row_ids"] == ["0:0", "0:1"]
    assert first["level_count"] == 2
    assert first["expected_level_count"] == 2
    assert first["calculation_status"] == "ok"


def test_pay_table_candidates_return_labeled_pay_and_uplift_pages(monkeypatch):
    import main

    def fake_find_candidate_pages(ae_id, pattern):
        assert ae_id == "aetest01"
        if pattern is main.PAY_KEYWORDS:
            return [40, 41, 42]
        if pattern is main.UPLIFT_KEYWORDS:
            return [12, 40]
        return []

    monkeypatch.setattr(main, "find_candidate_pages", fake_find_candidate_pages)

    response = TestClient(main.app).post("/api/councils/aetest01/pay-tables/find-candidates")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pay_table_pages"] == [40, 41, 42]
    assert body["uplift_rule_pages"] == [12, 40]
    assert body["candidate_pages"] == [40, 41, 42, 12]


def test_pay_table_candidates_use_false_positive_quality_ranker(monkeypatch):
    import main
    from benchmarking_data_factory.workbench import document_page_workflow

    page_texts = [
        "APPENDIX 2 - ALLOWANCES $1,234.00 $1,345.00 $1,456.00 meal allowance overtime call out",
        "CLASSIFICATION AND WAGE RATES Band 1 Level A weekly rate $1,100.00 Band 2 Level A weekly rate $1,240.00",
        "Hourly rate ordinary hours table classification",
        "Quantum and Timing Wage increases 1 July 2026 3.0% rate cap wage increase",
    ]
    monkeypatch.setattr(
        document_page_workflow,
        "extract_all_page_texts",
        lambda ae_id, deps: page_texts,
    )

    response = TestClient(main.app).post("/api/councils/aetest01/pay-tables/find-candidates")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pay_table_pages"] == [2, 1]
    assert body["uplift_rule_pages"][0] == 4
    assert body["candidate_pages"][:3] == [2, 1, 4]


def test_pay_tables_analysis_skips_non_weekly_governed_rows(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )

    (tmp_path / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    status: in_progress\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            table_title: Annual salaries\n"
        "            effective_from: '2025-07-01'\n"
        "            rate_kind: annual\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', title: Officer, annual_rate: 52000}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/pay-tables")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["tables"] == 1
    assert body["summary"]["rows"] == 0
    assert body["summary"]["weekly_rate_rows"] == 0
    assert body["summary"]["non_weekly_rows_skipped"] == 1
    assert body["rows"] == []


def test_end_of_band_dollars_analysis_projects_cash_amounts_by_band(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path / "canonical")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(main, "analysis_geography_fields", lambda lga: {})
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )
    monkeypatch.setattr(
        main,
        "resolve_canonical_lga_short_name",
        lambda ae_id, fetch_metadata=None, decisions=None: "Example",
    )

    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    cache_dir = tmp_path / "cache" / "aetest01"
    cache_dir.mkdir(parents=True)
    (cache_dir / "full_text.txt").write_text(
        "===== PAGE 0044 =====\n"
        "65. End of band payment All staff who reach the end of band/level in this Agreement "
        "and who are not progressing to a higher band shall qualify for a non-incremental payment "
        "of $1,000 (pro rata for part time staff) per annum following each additional year of service.\n",
        encoding="utf-8",
    )
    (canonical_dir / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            effective_from: '2025-07-01'\n"
        "            to_date: '2026-06-30'\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', weekly_rate: 1000}\n"
        "              - {band: '1', level: 'B', weekly_rate: 1100}\n"
        "              - {band: '2', level: 'A', weekly_rate: 1200}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/end-of-band-dollars")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["set_id"] == "set_4_end_of_band_dollars"
    assert body["summary"]["agreements_with_end_of_band_cash"] == 1
    assert body["summary"]["rows"] == 2
    assert {row["band"] for row in body["rows"]} == {"1", "2"}
    assert {row["end_of_band_cash_amount"] for row in body["rows"]} == {1000.0}
    assert body["rows"][0]["clause_number"] == "65"
    assert body["rows"][0]["source_page"] == 44


def test_end_of_band_dollars_analysis_excludes_one_off_bonus(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path / "canonical")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(main, "analysis_geography_fields", lambda lga: {})
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda ae_id, decisions=None: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda *args, **kwargs: "Example")

    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    cache_dir = tmp_path / "cache" / "aetest01"
    cache_dir.mkdir(parents=True)
    (cache_dir / "full_text.txt").write_text(
        "===== PAGE 0007 =====\n"
        "One-off $250 End of Band payment for employees who have been at the end of band "
        "for no less than 12 months as at 26 June 2025.\n",
        encoding="utf-8",
    )
    (canonical_dir / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2025-07-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', weekly_rate: 1000}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/end-of-band-dollars")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["rows"] == 0
    assert body["agreement_statuses"]["aetest01"]["source_text_status"] == "no_in_scope_cash_candidate"


def test_end_of_band_dollars_analysis_uses_explicit_e_level_without_standardising_it(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path / "canonical")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(main, "analysis_geography_fields", lambda lga: {})
    monkeypatch.setattr(main, "fetch_metadata_for_ae_id", lambda ae_id, decisions=None: {})
    monkeypatch.setattr(main, "resolve_canonical_lga_short_name", lambda *args, **kwargs: "Example")

    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir()
    cache_dir = tmp_path / "cache" / "aetest01"
    cache_dir.mkdir(parents=True)
    (cache_dir / "full_text.txt").write_text(
        "===== PAGE 0050 =====\n"
        "5.4 End of Band Payments Any employee who has been at the end of their Band/Classification "
        "for over twelve months shall be entitled to progress to the 'E' level. These payments are "
        "calculated on the basis of $500 or a salary level equivalent to the mid-point between the "
        "upper level of their current band and the lower level of the next band, whichever amount is greater.\n"
        "===== PAGE 0170 =====\n"
        "Weekly Wage Rates\n"
        "Effective Full Pay Period Commencing on or after 1 October 2024\n"
        "Band\nA\nB\nC\nD\nE (End of Band)\n"
        "Weekly\nYearly\nWeekly\nYearly\nWeekly\nYearly\nWeekly\nYearly\nWeekly\nYearly\n"
        "1\n$1,192.78\n$62,025\n$1,203.54\n$62,584\n$1,214.18\n$63,137\n$1,224.83\n$63,691\n$1,235.96\n$64,270\n"
        "2\n$1,240.21\n$64,491\n$1,253.29\n$65,171\n$1,267.52\n$65,911\nn/a\nn/a\n$1,278.65\n$66,490\n"
        "8\n$2,400.19\n$124,810\n$2,491.13\n$129,539\n$2,587.67\n$134,559\n$2,689.60\n$139,859\n$2,710.32\n$140,936\n",
        encoding="utf-8",
    )
    (canonical_dir / "aetest01.yaml").write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2024-10-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            effective_from: '2024-10-01'\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', weekly_rate: 1192.78}\n"
        "              - {band: '1', level: 'B', weekly_rate: 1203.54}\n"
        "              - {band: '1', level: 'C', weekly_rate: 1214.18}\n"
        "              - {band: '1', level: 'D', weekly_rate: 1224.83}\n"
        "              - {band: '2', level: 'A', weekly_rate: 1240.21}\n"
        "              - {band: '8', level: 'D', weekly_rate: 2689.60}\n"
        "        - effective_from: '2025-10-01'\n"
        "          pay_table_governed_at: '2026-04-24T01:00:00Z'\n"
        "          pay_table:\n"
        "            effective_from: '2025-10-01'\n"
        "            rows:\n"
        "              - {band: '1', level: 'D', weekly_rate: 1261.57}\n"
        "              - {band: '2', level: 'A', weekly_rate: 1277.42}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).get("/api/analysis/end-of-band-dollars")

    assert response.status_code == 200, response.text
    rows = {(row["effective_from"], row["band"]): row for row in response.json()["rows"]}
    assert rows[("2024-10-01", "1")]["end_of_band_cash_amount"] == 578.76
    assert rows[("2024-10-01", "1")]["end_of_band_weekly_rate"] == 1235.96
    assert rows[("2024-10-01", "8")]["end_of_band_cash_amount"] == 1077.44
    assert rows[("2024-10-01", "8")]["amount_basis"] == "greater_of_fixed_floor_or_eob_rate_table_delta"
    assert rows[("2024-10-01", "8")]["calculation_status"] == "computed_from_eob_rate_table"
    assert rows[("2025-10-01", "1")]["end_of_band_cash_amount"] == 500.0
    assert rows[("2025-10-01", "1")]["calculation_status"] == "computed_from_governed_weekly_band_gap"
    assert rows[("2025-10-01", "1")]["end_of_band_rate_source_effective_from"] is None


def test_pay_tables_rebuild_promotes_upstream_weekly_tables(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "DISTRIBUTION_POINT_ANALYSIS_JSON", tmp_path / "distribution-point-analysis.json")
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )

    canonical_path = tmp_path / "aetest01.yaml"
    canonical_path.write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  pay_tables:\n"
        "    status: done\n"
        "    tables:\n"
        "      - table_title: Base salaries\n"
        "        effective_from: '2025-07-01'\n"
        "        rate_kind: weekly\n"
        "        rows:\n"
        "          - {band: '1', level: 'A', title: Officer, weekly_rate: 1000, annual_rate: 52000}\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2024-07-01'\n"
        "          pay_table_governed_at: old\n"
        "          pay_table:\n"
        "            effective_from: '2024-07-01'\n"
        "            rows:\n"
        "              - {band: '1', level: 'A', weekly_rate: 900}\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).post("/api/analysis/pay_tables/rebuild")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rebuild"]["slots_cleared"] == 1
    assert body["rebuild"]["empty_periods_removed"] == 1
    assert body["rebuild"]["promoted"] == 1
    assert body["analysis"]["summary"]["rows"] == 1
    assert body["analysis"]["rows"][0]["effective_from"] == "2025-07-01"

    saved = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    periods = saved["sections"]["uplifts"]["data"]["periods"]
    assert [period["effective_from"] for period in periods] == ["2025-07-01"]
    governed_row = periods[0]["pay_table"]["rows"][0]
    assert governed_row["weekly_rate"] == 1000
    assert "annual_rate" not in governed_row


def test_uplift_rules_rebuild_promotes_accepted_rules(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main, "CANONICAL_DIR", tmp_path)
    monkeypatch.setattr(main, "load_registry", lambda: {"aetest01": "Example Council Agreement"})
    monkeypatch.setattr(main, "list_pdfs", lambda: [])
    monkeypatch.setattr(main, "load_multi_council_decisions", lambda: {})
    monkeypatch.setattr(main, "split_ae_ids_from_decisions", lambda decisions: set())
    monkeypatch.setattr(
        main,
        "fetch_metadata_for_ae_id",
        lambda ae_id, decisions=None: {"matched_lga_names": "Example"},
    )

    canonical_path = tmp_path / "aetest01.yaml"
    canonical_path.write_text(
        "agreement_id: aetest01\n"
        "source_name: Example Council Agreement\n"
        "sections:\n"
        "  uplift_rules:\n"
        "    status: done\n"
        "    data:\n"
        "      accepted:\n"
        "        rules:\n"
        "          - effective_date: '2025-07-01'\n"
        "            period_label: Year 1\n"
        "            quantum_type: percentage\n"
        "            quantum: 3%\n"
        "  uplifts:\n"
        "    data:\n"
        "      periods:\n"
        "        - effective_from: '2024-07-01'\n"
        "          uplift_rule_governed_at: old\n"
        "          uplift_rule:\n"
        "            pct_component: 2.5\n",
        encoding="utf-8",
    )

    response = TestClient(main.app).post("/api/analysis/uplift_rules/rebuild")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rebuild"]["slots_cleared"] == 1
    assert body["rebuild"]["empty_periods_removed"] == 1
    assert body["rebuild"]["promoted"] == 1
    assert body["analysis"]["summary"]["rules"] == 1
    assert body["analysis"]["rows"][0]["effective_from"] == "2025-07-01"
    assert body["analysis"]["rows"][0]["pattern_archetype"] == "flat_pct"

    saved = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    periods = saved["sections"]["uplifts"]["data"]["periods"]
    assert [period["effective_from"] for period in periods] == ["2025-07-01"]
    assert periods[0]["uplift_rule"]["source_quantum"] == "3%"


def test_analysis_dependency_context_is_isolated_between_threads():
    entered_a = Event()
    entered_b = Event()
    exited_a = Event()

    def deps_with_marker(marker):
        return analysis_workspace.AnalysisWorkspaceDependencies(
            load_registry=lambda: {"marker": marker},
            load_multi_council_decisions=lambda: {},
            split_ae_ids_from_decisions=lambda decisions: set(),
            list_pdfs=lambda: [],
            get_canonical=lambda ae_id: {},
            fetch_metadata_for_ae_id=lambda ae_id, decisions=None: {},
            resolve_canonical_lga_short_name=lambda *args, **kwargs: None,
            scenario_cell_overrides_for_period=lambda ae_id, effective_from: None,
            save_canonical=lambda ae_id, canonical: None,
            now_iso=lambda: "2026-05-02T00:00:00+00:00",
            analysis_geography_fields=lambda lga: {},
            standard_band_level_metadata=lambda row: {},
            parse_iso_date=lambda value: None,
            root_path=lambda: None,
            distribution_point_analysis_json=lambda: None,
            extract_page_text=lambda ae_id, page_num: "",
        )

    def worker_a():
        with analysis_workspace.analysis_workspace_dependencies(deps_with_marker("a")):
            entered_a.set()
            assert entered_b.wait(timeout=5)
        exited_a.set()

    def worker_b():
        assert entered_a.wait(timeout=5)
        with analysis_workspace.analysis_workspace_dependencies(deps_with_marker("b")):
            entered_b.set()
            assert exited_a.wait(timeout=5)
            return analysis_workspace.load_registry()["marker"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(worker_a)
        future_b = executor.submit(worker_b)

    future_a.result(timeout=5)
    assert future_b.result(timeout=5) == "b"
