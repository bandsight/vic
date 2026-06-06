import pytest

from benchmarking_data_factory.governed_set import promote_pay_table, promote_uplift_rule


def _canonical_with_table_and_rule():
    return {
        "agreement_id": "aeTEST01",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2026-07-01",
                        "table_title": "Base",
                        "rate_kind": "weekly",
                        "rows": [
                            {"band": "1", "level": "1", "weekly_rate": 900.0, "annual_rate": 46800.0},
                            {"band": "1", "level": "2", "weekly_rate": 950.0, "fortnightly_rate": 1900.0},
                        ],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {"effective_date": "2026-07-01", "quantum": "3%", "quantum_type": "percentage"},
                            ],
                        },
                    },
                },
            },
            "uplifts": {"status": "not_started", "data": None},
        },
    }


def _multi_employer_canonical():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"] = [
        {
            "period_label": "Year 1 - Ararat Rural City Council",
            "effective_date": "2024-07-01",
            "quantum": "4% or $55.00 per week, whichever is greater",
            "quantum_type": "pct_OR_floor",
            "quantum_resolution": "applies to Ararat Rural City Council employees",
        },
        {
            "period_label": "Year 2 - Ararat Rural City Council",
            "effective_date": "2025-07-01",
            "quantum": "3.5% or $50.00 per week, whichever is greater",
            "quantum_type": "pct_OR_floor",
            "quantum_resolution": "applies to Ararat Rural City Council employees",
        },
        {
            "period_label": "Year 2 - Central Goldfields Shire Council",
            "effective_date": "2025-07-01",
            "quantum": "3% or $50.00 per week, whichever is greater",
            "quantum_type": "pct_OR_floor",
            "quantum_resolution": "applies to Central Goldfields Shire Council employees per footnote",
        },
    ]
    return canonical


def _governed_pay_row(band, level, weekly_rate, **extra):
    level = str(level)
    band = str(band)
    level_sort = {"A": 1, "B": 2, "C": 3, "D": 4, "1": 1, "2": 2, "3": 3, "4": 4}.get(level, 99)
    row = {
        "band": band,
        "level": level,
        "weekly_rate": weekly_rate,
        "standard_band": band,
        "standard_level": level,
        "classification_key": f"band_{int(band):02d}_level_{level}",
        "classification_label": f"Band {band} Level {level}",
        "classification_sort": int(band) * 100 + level_sort,
    }
    row.update(extra)
    return row


def test_promote_pay_table_creates_period():
    canonical = _canonical_with_table_and_rule()
    period = promote_pay_table(canonical, "2026-07-01")
    assert period["effective_from"] == "2026-07-01"
    assert period["pay_table"] is not None
    assert period["pay_table_governed_at"] is not None
    assert len(period["pay_table"]["rows"]) == 2
    assert period["pay_table"]["rate_kind"] == "weekly"
    assert period["pay_table"]["rows"][0]["weekly_rate"] == 900.0
    assert "annual_rate" not in period["pay_table"]["rows"][0]
    assert "fortnightly_rate" not in period["pay_table"]["rows"][1]
    assert period["pay_table"]["row_scope"] == "standard_band_level"
    assert period["pay_table"]["excluded_rows_count"] == 0


def test_promote_pay_table_missing_raises():
    canonical = _canonical_with_table_and_rule()
    with pytest.raises(ValueError):
        promote_pay_table(canonical, "2099-01-01")


def test_promote_pay_table_adds_canonical_pay_banding_metadata_without_losing_source_labels():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"][0]["rows"] = [
        {"band": "Band 5", "level": "Level A", "weekly_rate": 1432.85},
    ]

    period = promote_pay_table(canonical, "2026-07-01")

    row = period["pay_table"]["rows"][0]
    assert row["band"] == "Band 5"
    assert row["level"] == "Level A"
    assert row["standard_band"] == "5"
    assert row["standard_level"] == "A"
    assert row["classification_key"] == "band_05_level_A"
    assert row["classification_label"] == "Band 5 Level A"
    assert row["classification_sort"] == 501


def test_promote_pay_table_prefers_weekly_values_for_period():
    canonical = _canonical_with_table_and_rule()
    tables = canonical["sections"]["pay_tables"]["tables"]
    tables.insert(0, {
        "effective_from": "2026-07-01",
        "table_title": "Annual rates",
        "rate_kind": "annual",
        "rows": [{"band": "1", "level": "1", "annual_rate": 46800.0}],
    })

    period = promote_pay_table(canonical, "2026-07-01")

    assert period["pay_table"]["table_title"] == "Base"
    assert period["pay_table"]["rows"] == [
        _governed_pay_row("1", "1", 900.0),
        _governed_pay_row("1", "2", 950.0),
    ]


def test_promote_pay_table_derives_weekly_values_from_annual_rates():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"] = [{
        "effective_from": "2026-07-01",
        "table_title": "Annual rates",
        "rate_kind": "annual",
        "rows": [{"band": "1", "level": "1", "annual_rate": 46800.0}],
    }]

    period = promote_pay_table(canonical, "2026-07-01")

    assert period["pay_table"]["rate_kind"] == "weekly"
    assert period["pay_table"]["rows"] == [
        _governed_pay_row("1", "1", 900.0, weekly_rate_basis="annual_rate/52"),
    ]


def test_promote_pay_table_rounds_derived_weekly_values_to_cents():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"] = [{
        "effective_from": "2026-07-01",
        "table_title": "Annual rates",
        "rate_kind": "annual",
        "rows": [{"band": "1", "level": "1", "annual_rate": 65974.28}],
    }]

    period = promote_pay_table(canonical, "2026-07-01")

    assert period["pay_table"]["rows"][0]["weekly_rate"] == 1268.74


def test_promote_pay_table_derives_weekly_values_from_fortnightly_rates():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"] = [{
        "effective_from": "2026-07-01",
        "table_title": "Fortnightly rates",
        "rate_kind": "fortnightly",
        "rows": [{"band": "1", "level": "1", "fortnightly_rate": 1800.0}],
    }]

    period = promote_pay_table(canonical, "2026-07-01")

    assert period["pay_table"]["rows"] == [
        _governed_pay_row("1", "1", 900.0, weekly_rate_basis="fortnightly_rate/2"),
    ]


def test_promote_pay_table_without_promotable_values_raises():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"] = [{
        "effective_from": "2026-07-01",
        "table_title": "Empty rates",
        "rate_kind": "annual",
        "rows": [{"band": "1", "level": "1", "annual_rate": None}],
    }]

    with pytest.raises(ValueError, match="No upstream pay table with weekly, annual, or fortnightly rates"):
        promote_pay_table(canonical, "2026-07-01")


def test_promote_pay_table_excludes_non_standard_specialist_rows():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"][0]["rows"].append({
        "band": None,
        "level": None,
        "title": "Maternal and Child Health Nurse Year 1",
        "weekly_rate": 2000.0,
    })

    period = promote_pay_table(canonical, "2026-07-01")

    assert len(period["pay_table"]["rows"]) == 2
    assert period["pay_table"]["source_rows_count"] == 3
    assert period["pay_table"]["standard_rows_count"] == 2
    assert period["pay_table"]["excluded_rows_count"] == 1


def test_promote_pay_table_deduplicates_standard_band_level_cells():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"][0]["rows"].append({
        "band": "1",
        "level": "1",
        "weekly_rate": 9999.0,
        "title": "Industry allowance duplicate",
    })

    period = promote_pay_table(canonical, "2026-07-01")

    assert period["pay_table"]["rows"] == [
        _governed_pay_row("1", "1", 900.0),
        _governed_pay_row("1", "2", 950.0),
    ]
    assert period["pay_table"]["source_rows_count"] == 3
    assert period["pay_table"]["standard_rows_count"] == 2
    assert period["pay_table"]["duplicate_standard_rows_count"] == 1
    assert period["pay_table"]["excluded_rows_count"] == 1


def test_promote_pay_table_rejects_specialist_only_table():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["pay_tables"]["tables"][0]["rows"] = [{
        "band": None,
        "level": None,
        "title": "Maternal and Child Health Nurse Year 1",
        "weekly_rate": 2000.0,
    }]

    with pytest.raises(ValueError, match="No upstream pay table"):
        promote_pay_table(canonical, "2026-07-01")


def test_promote_pay_table_deep_copies_rows():
    canonical = _canonical_with_table_and_rule()
    promote_pay_table(canonical, "2026-07-01")
    canonical["sections"]["pay_tables"]["tables"][0]["rows"][0]["weekly_rate"] = 1.0
    governed_rows = canonical["sections"]["uplifts"]["data"]["periods"][0]["pay_table"]["rows"]
    assert governed_rows[0]["weekly_rate"] == 900.0


def test_promote_uplift_rule_creates_period():
    canonical = _canonical_with_table_and_rule()
    period = promote_uplift_rule(canonical, "2026-07-01")
    assert period["uplift_rule"] is not None
    assert period["uplift_rule"]["pattern_archetype"] == "flat_pct"
    assert period["uplift_rule_governed_at"] is not None


def test_promote_uplift_rule_missing_raises():
    canonical = _canonical_with_table_and_rule()
    with pytest.raises(ValueError):
        promote_uplift_rule(canonical, "2099-01-01")


def test_promote_uplift_rule_filters_same_date_multi_employer_rules_by_lga():
    canonical = _multi_employer_canonical()
    period = promote_uplift_rule(canonical, "2025-07-01", lga_short_name="Central Goldfields")

    rule = period["uplift_rule"]
    assert rule["pct_component"] == 3.0
    assert rule["floor_dollar"] == 50.0
    assert rule["source_rule_id"] == "2025-07-01::Year 2 - Central Goldfields Shire Council"
    assert rule["pattern_variant"] == "3% or $50.00 per week, whichever is greater"


def test_promote_uplift_rule_does_not_fall_back_to_other_lga_when_scoped():
    canonical = _multi_employer_canonical()

    with pytest.raises(ValueError):
        promote_uplift_rule(canonical, "2024-07-01", lga_short_name="Central Goldfields")


def test_promote_both_same_period():
    canonical = _canonical_with_table_and_rule()
    promote_pay_table(canonical, "2026-07-01")
    promote_uplift_rule(canonical, "2026-07-01")
    periods = canonical["sections"]["uplifts"]["data"]["periods"]
    assert len(periods) == 1
    assert periods[0]["pay_table"] is not None
    assert periods[0]["uplift_rule"] is not None


def test_promote_uplift_rule_with_rate_cap_tracking():
    # Rule pct ~= cap (within 5%) => tracking
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0] = {
        "effective_date": "2026-07-01",
        "quantum": "Victorian rate cap for the financial year",
        "quantum_type": "conditional",
    }
    period = promote_uplift_rule(canonical, "2026-07-01", rate_cap_value=2.75)
    assert period["uplift_rule"]["pattern_archetype"] == "rate_cap_tracking"
    assert period["uplift_rule"]["rate_cap_component"] == 2.75
    assert period["uplift_rule"]["external_formula_pct"] == 2.75
    assert period["uplift_rule"]["resolved_pct"] == 2.75


def test_promote_uplift_rule_with_rate_cap_plus_margin():
    # Rule pct well above cap => plus_margin
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0] = {
        "effective_date": "2026-07-01",
        "quantum": "3% or Victorian rate cap, whichever is higher",
        "quantum_type": "conditional",
    }
    period = promote_uplift_rule(canonical, "2026-07-01", rate_cap_value=2.75)
    # 3% vs 2.75% cap: pct > cap * 1.05 => plus_margin
    assert period["uplift_rule"]["pattern_archetype"] == "rate_cap_plus_margin"
    assert period["uplift_rule"]["rate_cap_component"] == 2.75
    assert period["uplift_rule"]["pct_component"] == 3.0
    assert period["uplift_rule"]["resolved_pct"] == 3.0


def test_promote_uplift_rule_preserves_rate_cap_components():
    canonical = _canonical_with_table_and_rule()
    canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0] = {
        "effective_date": "2026-07-01",
        "quantum": "90% of the official rate cap, or 3.0% or $50 per week, whichever is greater",
        "quantum_type": "conditional",
    }
    period = promote_uplift_rule(
        canonical,
        "2026-07-01",
        rate_cap_value=3.0,
        rate_cap_resolution={
            "raw_rate_cap": 3.0,
            "fraction": 0.9,
            "effective_rate": 3.0,
            "fixed_floor_pct": 3.0,
            "dollar_floor_per_week": 50.0,
        },
    )
    rule = period["uplift_rule"]
    assert rule["pct_component"] == 3.0
    assert rule["internal_pct_component"] == 3.0
    assert rule["pct_of_rate_cap"] == 0.9
    assert rule["external_cap_pct"] == 3.0
    assert rule["external_formula_pct"] == 2.7
    assert rule["resolved_pct"] == 3.0
    assert rule["dollar_floor_component"] == 50.0
