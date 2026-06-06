from benchmarking_data_factory.scenario_testing.engine import run_scenarios


def _table(effective_from, rows, table_title="Rates"):
    return {
        "effective_from": effective_from,
        "table_title": table_title,
        "rows": rows,
    }


def _row(band, level, weekly):
    return {"band": band, "level": level, "weekly_rate": weekly}


def _rule(effective_date, quantum):
    return {
        "effective_date": effective_date,
        "period_label": f"Period {effective_date}",
        "quantum_type": "conditional",
        "quantum": quantum,
    }


def _canonical(quantum: str, lga_short_name: str = "Yarra Ranges") -> dict:
    return {
        "agreement_id": "ae-test-lga",
        "canonical_lga_short_name": lga_short_name,
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    _table("2022-07-01", [_row("1", "A", 1000.0)], "Baseline"),
                    _table("2023-07-01", [_row("1", "A", 1020.0)], "Uplift"),
                ],
            },
            "uplift_rules": {
                "status": "done",
                "data": {
                    "rules": [
                        _rule("2023-07-01", quantum),
                    ]
                },
            },
        },
    }


def _non_baseline_result(results):
    return [result for result in results if result.period_effective_from == "2023-07-01"][0]


def test_yarra_ranges_rate_cap_resolves_with_lga():
    canonical = _canonical(
        "90% of the official rate cap as advised by the Minister for Local Government",
        lga_short_name="Yarra Ranges",
    )
    result = _non_baseline_result(run_scenarios(canonical, lga_short_name="Yarra Ranges"))
    assert result.sub_status not in {"ambiguous_rule", "missing_lga_context"}


def test_queenscliffe_delta_rule_resolves_with_lga():
    canonical = _canonical("0.5% less than the rate cap", lga_short_name="Queenscliffe")
    result = _non_baseline_result(run_scenarios(canonical, lga_short_name="Queenscliffe"))
    assert result.sub_status != "ambiguous_rule"


def test_missing_lga_emits_explicit_diagnostic():
    canonical = _canonical(
        "90% of the official rate cap as advised by the Minister for Local Government",
        lga_short_name="Yarra Ranges",
    )
    result = _non_baseline_result(run_scenarios(canonical))
    assert result.sub_status == "missing_lga_context"
