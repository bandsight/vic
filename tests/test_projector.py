"""Tests for the table projection module."""
from unittest.mock import patch

from benchmarking_data_factory.scenario_testing.projector import construct_table


def _row(band, level, weekly):
    return {
        "band": band,
        "level": level,
        "weekly_rate": weekly,
        "annual_rate": None,
        "hourly_rate": None,
        "fortnightly_rate": None,
        "title": None,
        "notes": None,
    }


def _table(eff_from, rows):
    return {"table_title": "Test", "effective_from": eff_from, "rows": rows, "rate_kind": "weekly"}


def _rule(eff_date, qtype, quantum, **kwargs):
    return {"effective_date": eff_date, "quantum_type": qtype, "quantum": quantum, "period_label": "Year X", **kwargs}


def _make_canonical(tables, rules):
    return {
        "agreement_id": "ae_test",
        "sections": {
            "pay_tables": {"status": "done", "tables": tables},
            "uplift_rules": {
                "status": "done",
                "data": {"accepted": {"document": {"rules": rules}}},
            },
        },
    }


def test_construct_percentage_rule():
    canonical = _make_canonical(
        tables=[_table("2024-10-01", [_row(1, "A", 1000.00), _row(1, "B", 1100.00)])],
        rules=[_rule("2025-10-01", "percentage", "4%")],
    )
    result = construct_table(canonical, "2025-10-01")
    assert result is not None
    assert result["effective_from"] == "2025-10-01"
    assert result["provenance"] == "constructed"
    assert len(result["rows"]) == 2
    assert result["rows"][0]["weekly_rate"] == 1040.00
    assert result["rows"][1]["weekly_rate"] == 1144.00


def test_construct_ignores_non_standard_specialist_rows():
    canonical = _make_canonical(
        tables=[_table("2024-10-01", [
            _row(1, "A", 1000.00),
            {"band": None, "level": None, "title": "Maternal and Child Health Nurse Year 1", "weekly_rate": 2000.00},
        ])],
        rules=[_rule("2025-10-01", "percentage", "4%")],
    )
    result = construct_table(canonical, "2025-10-01")
    assert result is not None
    assert result["rows"] == [{
        "band": 1,
        "level": "A",
        "title": None,
        "weekly_rate": 1040.00,
        "annual_rate": None,
        "hourly_rate": None,
        "fortnightly_rate": None,
        "notes": None,
    }]


def test_construct_keeps_first_standard_duplicate_cell():
    canonical = _make_canonical(
        tables=[_table("2024-10-01", [
            _row(1, "A", 1000.00),
            _row(1, "A", 2000.00),
        ])],
        rules=[_rule("2025-10-01", "percentage", "4%")],
    )
    result = construct_table(canonical, "2025-10-01")
    assert result is not None
    assert result["rows"][0]["weekly_rate"] == 1040.00


def test_construct_pct_or_floor_rule():
    canonical = _make_canonical(
        tables=[_table("2024-10-01", [_row(1, "A", 1000.00), _row(2, "A", 1800.00)])],
        rules=[_rule("2025-10-01", "pct_OR_floor", "3% or $50 per week (whichever is greater)", quantum_floor="$50")],
    )
    result = construct_table(canonical, "2025-10-01")
    assert result is not None
    assert result["rows"][0]["weekly_rate"] == 1050.00
    assert result["rows"][1]["weekly_rate"] == 1854.00


def test_construct_conditional_confirmed_cap():
    canonical = _make_canonical(
        tables=[_table("2025-07-01", [_row(1, "A", 1000.00), _row(1, "B", 1100.00)])],
        rules=[_rule("2026-07-01", "conditional", "3% or the rate cap, whichever is the greater")],
    )
    with patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.classify_rate_cap_mode", return_value="rate_cap_max_of_floor_and_cap"), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.date_to_financial_year", return_value="2026-27"), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.get_year_status_row", return_value={"resolution_status": "confirmed", "confirmed_date": "2026-04-10"}), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.resolve_effective_rate", return_value={"effective_rate": 3.0, "source": "floor"}):
        result = construct_table(canonical, "2026-07-01", lga_short_name="port_phillip")
    assert result is not None
    assert result["rows"][0]["weekly_rate"] == 1030.00
    assert result["rows"][1]["weekly_rate"] == 1133.00


def test_construct_conditional_cap_keeps_dollar_floor():
    canonical = _make_canonical(
        tables=[_table("2025-07-01", [_row(1, "A", 1000.00), _row(1, "B", 3000.00)])],
        rules=[
            _rule(
                "2026-07-01",
                "conditional",
                "2% or $50 per week or 80% of the gazetted Local Government rate cap, whichever is greater",
            )
        ],
    )
    with patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.classify_rate_cap_mode", return_value="pct_of_rate_cap"), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.date_to_financial_year", return_value="2026-27"), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.get_year_status_row", return_value={"resolution_status": "confirmed", "confirmed_date": "2026-04-10"}), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.resolve_effective_rate", return_value={"effective_rate": 2.0, "dollar_floor_per_week": 50.0}):
        result = construct_table(canonical, "2026-07-01", lga_short_name="loddon")

    assert result is not None
    assert result["rows"][0]["weekly_rate"] == 1050.00
    assert result["rows"][1]["weekly_rate"] == 3060.00


def test_construct_conditional_pending_cap():
    canonical = _make_canonical(
        tables=[_table("2025-07-01", [_row(1, "A", 1000.00)])],
        rules=[_rule("2026-07-01", "conditional", "3% or the rate cap, whichever is the greater")],
    )
    with patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.classify_rate_cap_mode", return_value="rate_cap_max_of_floor_and_cap"), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.date_to_financial_year", return_value="2026-27"), \
         patch("benchmarking_data_factory.uplift_rules.rate_cap.resolver.get_year_status_row", return_value={"resolution_status": "pending_announcement"}):
        result = construct_table(canonical, "2026-07-01", lga_short_name="port_phillip")
    assert result is None


def test_construct_no_prior_table():
    canonical = _make_canonical(
        tables=[],
        rules=[_rule("2026-07-01", "percentage", "4%")],
    )
    assert construct_table(canonical, "2026-07-01") is None


def test_construct_no_matching_rule():
    canonical = _make_canonical(
        tables=[_table("2024-10-01", [_row(1, "A", 1000.00)])],
        rules=[_rule("2025-10-01", "percentage", "4%")],
    )
    assert construct_table(canonical, "2099-01-01") is None


def test_construct_table_embedded_rule():
    canonical = _make_canonical(
        tables=[_table("2024-10-01", [_row(1, "A", 1000.00)])],
        rules=[_rule("2025-10-01", "table_embedded", "rates in Appendix 1")],
    )
    assert construct_table(canonical, "2025-10-01") is None
