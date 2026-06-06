from __future__ import annotations

from benchmarking_data_factory.workbench.report_values import (
    DISPLAY_EMPTY,
    agreement_report_values,
    display_currency,
    display_currency_delta,
    display_date,
    display_date_range,
    display_file_size,
    display_fraction_percent,
    display_pages,
    display_percent,
    display_percent_delta,
    pay_table_report_values,
    validate_pay_metric_claim,
    validate_service_horizon_chart_title,
)


def test_display_dates_and_ranges_use_standard_empty_states():
    assert display_date("2026-04-27T10:15:00+10:00") == "2026-04-27"
    assert display_date(None) == DISPLAY_EMPTY
    assert display_date_range("2024-07-01", "2027-06-30") == "2024-07-01 to 2027-06-30"
    assert display_date_range("2024-07-01", None) == "2024-07-01 to open ended"
    assert display_date_range(None, "2027-06-30") == "Until 2027-06-30"
    assert display_date_range(None, None) == "Dates not stated"


def test_display_pages_currency_percent_and_file_size():
    assert display_pages([44, 51]) == "pp. 44, 51"
    assert display_pages(7) == "p. 7"
    assert display_currency("1234.5") == "A$1,234.50"
    assert display_currency_delta("-42") == "-A$42.00"
    assert display_percent("3.50%") == "3.5%"
    assert display_fraction_percent(0.035) == "3.5%"
    assert display_percent_delta(-0.025, fraction=True) == "-2.5%"
    assert display_file_size(499 * 1024) == "499 KB"
    assert display_file_size(2.5 * 1024 * 1024) == "2.5 MB"


def test_pay_table_report_values_standardise_section_fields():
    values = pay_table_report_values(
        {
            "table_title": "Schedule A",
            "source_clause": "",
            "source_pages": [28, 29],
            "effective_from": "2024-07-01",
            "to_date": "2025-06-30",
            "rate_kind": "weekly_rate",
        }
    )

    assert values["table_title"] == "Schedule A"
    assert values["source_clause"] == DISPLAY_EMPTY
    assert values["source_pages"] == "pp. 28, 29"
    assert values["effective_period"] == "2024-07-01 to 2025-06-30"
    assert values["rate_kind"] == "weekly rate"


def test_agreement_report_values_prefer_canonical_fwc_and_pdf_health():
    values = agreement_report_values(
        canonical={
            "fwc": {"operative_date": "2024-07-01", "expiry_date": "2027-06-30"},
            "overview": {
                "page_count": 162,
                "likely_pay_table_pages": [44],
                "likely_uplift_pages": [],
            },
        },
        fetch_metadata={"Operative Date": "2020-01-01", "Expiry Date": "2021-01-01"},
        pdf_source={"file_size_bytes": 1024 * 1024, "size_status": "suspect_under_500kb"},
        landed_at="2026-04-05T00:00:00+00:00",
        pay_table_summary=[{"table_title": "A"}, {"table_title": "B"}],
    )

    assert values["agreement_period"] == "2024-07-01 to 2027-06-30"
    assert values["page_count"] == "162"
    assert values["likely_pay_table_pages"] == "p. 44"
    assert values["likely_uplift_pages"] == DISPLAY_EMPTY
    assert values["fetched_pdf_size"] == "1.0 MB"
    assert values["fetched_pdf_health"] == "suspect under 500kb"
    assert values["frozen_pdf_size"] == values["fetched_pdf_size"]
    assert values["landed_at"] == "2026-04-05"
    assert values["pay_table_count"] == "2"


def test_pay_metric_claim_safety_requires_explicit_metric():
    vague = validate_pay_metric_claim("Band 5 sits above market.")
    explicit = validate_pay_metric_claim("Band 5 year-3 rate sits above the cohort median.")
    supplied = validate_pay_metric_claim("Band 5 sits above the cohort median.", comparison_metric="capacity_rate")

    assert vague["valid"] is False
    assert vague["reason"] == "pay_metric_missing"
    assert explicit["valid"] is True
    assert supplied["valid"] is True


def test_pay_metric_claim_safety_blocks_fake_service_horizon_ordinals():
    unsafe_level = validate_pay_metric_claim(
        "Council A has a Level 6 rate.",
        comparison_metric="service_year_6_rate",
        actual_step_count=3,
    )
    safe_horizon = validate_pay_metric_claim(
        "At the year-6 service horizon, the Band 5 value resolves to Level C capacity carried forward.",
        comparison_metric="service_year_6_rate",
        actual_step_count=3,
    )
    ungoverned_progression = validate_pay_metric_claim(
        "After six years of service the employee will receive the capacity rate.",
        comparison_metric="service_year_6_rate",
        actual_step_count=3,
        progression_rule_status="estimated_not_governed",
    )
    governed_progression = validate_pay_metric_claim(
        "After six years of service the employee will receive the capacity rate.",
        comparison_metric="service_year_6_rate",
        actual_step_count=6,
        progression_rule_status="governed",
    )

    assert unsafe_level["valid"] is False
    assert unsafe_level["reason"] == "unsafe_service_horizon_ordinal_language"
    assert safe_horizon["valid"] is True
    assert ungoverned_progression["valid"] is False
    assert ungoverned_progression["reason"] == "ungoverned_progression_claim"
    assert governed_progression["valid"] is True


def test_service_horizon_chart_title_requires_window_context():
    safe = validate_service_horizon_chart_title(
        "Band 5 Entry-to-Year-3 service-horizon distribution - All governed comparable rows",
        standard_band="5",
        cohort_name="All governed comparable rows",
        service_horizon_window_label="Entry-to-Year-3 service-horizon distribution",
    )
    generic = validate_service_horizon_chart_title(
        "Band 5 distribution",
        standard_band="5",
        cohort_name="All governed comparable rows",
        service_horizon_window_label="Entry-to-Year-3 service-horizon distribution",
    )

    assert safe["valid"] is True
    assert generic["valid"] is False
    assert generic["reason"] == "chart_title_missing_service_horizon_context"
    assert "service_horizon_window_label" in generic["missing"]
