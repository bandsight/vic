from benchmarking_data_factory.governed_set import promote_pay_table


def test_promote_pay_table_applies_saved_scenario_overrides():
    canonical = {
        "sections": {
            "pay_tables": {
                "tables": [
                    {
                        "effective_from": "2025-12-01",
                        "rate_kind": "weekly",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 100.0},
                            {"band": "1", "level": "B", "weekly_rate": 110.0},
                            {"band": "1", "level": "C", "weekly_rate": 120.0},
                        ],
                    }
                ]
            },
            "uplifts": {"data": {"periods": []}},
        }
    }

    promote_pay_table(
        canonical,
        "2025-12-01",
        cell_overrides={
            "1:A": {"action": "use_computed", "weekly": 103.45},
            "1:B": {"action": "accept"},
            "1:C": {"action": "deleted"},
        },
    )

    period = canonical["sections"]["uplifts"]["data"]["periods"][0]
    table = period["pay_table"]
    rows = table["rows"]

    assert table["scenario_override_counts"] == {
        "accept": 1,
        "deleted": 1,
        "use_computed": 1,
    }
    assert [(row["band"], row["level"]) for row in rows] == [("1", "A"), ("1", "B")]
    assert rows[0]["weekly_rate"] == 103.45
    assert rows[0]["source_weekly_rate"] == 100.0
    assert rows[0]["weekly_rate_basis"] == "scenario_override_use_computed"
    assert rows[0]["scenario_override_action"] == "use_computed"
    assert rows[1]["weekly_rate"] == 110.0
    assert rows[1]["scenario_override_action"] == "accept"
