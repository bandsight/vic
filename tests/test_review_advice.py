from __future__ import annotations

from benchmarking_data_factory.workbench.review_advice import (
    build_pay_table_review_hints,
    build_scenario_review_hints,
)


def _standard_rows(max_band: int = 8, levels: tuple[str, ...] = ("A", "B", "C", "D")) -> list[dict]:
    return [
        {"band": band, "level": level, "weekly_rate": 1000 + band * 10}
        for band in range(1, max_band + 1)
        for level in levels
    ]


def _canonical_with_rules(rules: list[dict]) -> dict:
    return {
        "agreement_id": "aetest01",
        "sections": {
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": rules,
                        }
                    }
                }
            }
        },
    }


def test_rules_first_hint_prefers_later_table_embedded_date():
    canonical = _canonical_with_rules([
        {
            "period_label": "Transition increase",
            "effective_date": "2025-09-01",
            "quantum_type": "percentage",
            "quantum": "3%",
        },
        {
            "period_label": "General Bands reform table",
            "effective_date": "2026-02-01",
            "quantum_type": "table_embedded",
            "quantum": "Reform rates in Schedule B",
        },
    ])
    tables = [{
        "table_title": "General Bands 1-8",
        "effective_from": "2025-09-01",
        "rows": _standard_rows(),
    }]

    hints = build_pay_table_review_hints(
        canonical,
        tables,
        suggestions=[{
            "index": 0,
            "current_effective_from": "2025-09-01",
            "suggested_effective_from": "2025-09-01",
        }],
    )

    hint = next(h for h in hints if h["code"] == "rules_first_table_embedded_effective_date")
    assert hint["target"]["preferred_effective_from"] == "2026-02-01"
    assert "bring later table rates forward" in hint["save_note"]


def test_rules_first_hint_does_not_move_table_already_on_embedded_date():
    canonical = _canonical_with_rules([
        {
            "period_label": "Year 1 reform table",
            "effective_date": "2026-02-01",
            "quantum_type": "table_embedded",
            "quantum": "Year 1 table",
        },
        {
            "period_label": "Year 2 reform table",
            "effective_date": "2027-02-01",
            "quantum_type": "table_embedded",
            "quantum": "Year 2 table",
        },
    ])
    tables = [{
        "table_title": "Year 1 standard table",
        "effective_from": "2026-02-01",
        "rows": _standard_rows(),
    }]

    hints = build_pay_table_review_hints(canonical, tables)

    assert not [
        hint for hint in hints
        if hint["code"] == "rules_first_table_embedded_effective_date"
    ]


def test_level_d_missing_hint_recommends_computed_values():
    canonical = _canonical_with_rules([])
    tables = [
        {
            "table_title": "Year 1",
            "effective_from": "2025-07-01",
            "rows": _standard_rows(max_band=1, levels=("A", "B", "C", "D")),
        },
        {
            "table_title": "Year 2",
            "effective_from": "2026-07-01",
            "rows": _standard_rows(max_band=1, levels=("A", "B", "C")),
        },
    ]

    hints = build_pay_table_review_hints(canonical, tables)

    hint = next(h for h in hints if h["code"] == "standard_level_d_missing")
    assert "Band 1 Level D" in hint["target"]["cells"]
    assert "use computed values" in hint["save_note"]


def test_starting_point_hint_tells_reviewer_to_suggest_dates():
    canonical = {
        "agreement_id": "aetest01",
        "sections": {
            "front_matter": {"data": {"operative_date": "2025-09-01"}},
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [{
                                "period_label": "Year 1",
                                "effective_date": "2025-09-01",
                                "quantum_type": "percentage",
                                "quantum": "3%",
                            }]
                        }
                    }
                }
            },
        },
    }
    tables = [{
        "table_title": "Standard Bands",
        "effective_from": None,
        "rows": _standard_rows(),
    }]

    hints = build_pay_table_review_hints(canonical, tables, suggestions=[])

    hint = next(h for h in hints if h["code"] == "run_suggest_effective_dates")
    assert "operative date" in hint["message"]
    assert any("2025-09-01" in item for item in hint["evidence"])


def test_undated_prior_table_hint_recommends_drop_if_needed():
    canonical = _canonical_with_rules([
        {
            "period_label": "Year 1",
            "effective_date": "2025-09-01",
            "quantum_type": "percentage",
            "quantum": "3%",
        },
    ])
    tables = [{
        "table_title": "Prior to Agreement commencing rates",
        "effective_from": None,
        "effective_from_note": "Prior to Agreement commencing",
        "rows": _standard_rows(),
    }]

    hints = build_pay_table_review_hints(canonical, tables, suggestions=[{"index": 0}])

    hint = next(h for h in hints if h["code"] == "drop_undated_prior_or_base_table")
    assert "Dropped undated prior/base table" in hint["save_note"]


def test_future_factor_hint_flags_rate_cap_rules():
    canonical = _canonical_with_rules([
        {
            "period_label": "Year 3",
            "effective_date": "2027-09-01",
            "quantum_type": "conditional",
            "quantum": "greater of 3% or the gazetted rate cap",
        },
    ])
    tables = [{
        "table_title": "Standard Bands",
        "effective_from": "2025-09-01",
        "rows": _standard_rows(),
    }]

    hints = build_pay_table_review_hints(canonical, tables, suggestions=[{"index": 0}])

    hint = next(h for h in hints if h["code"] == "future_factor_check")
    assert "rate cap" in hint["message"]
    assert hint["target"]["rule_dates"] == ["2027-09-01"]


def test_scenario_use_computed_hint_exposes_basis_and_save_note():
    scenario = {
        "period_effective_from": "2026-07-01",
        "status": "needs_attention",
        "sub_status": "conflict",
        "decision_recommendation": {
            "action": "use_computed",
            "basis": "confirmed_external_dependency_multi_cell_variance",
            "confidence": "high",
            "affected_cells": 2,
        },
        "cell_deltas": [
            {
                "band": "5",
                "level": "1",
                "computed_weekly": 1046.00,
                "actual_weekly": 1030.00,
                "within_tolerance": False,
                "recommended_action": "use_computed",
            },
            {
                "band": "5",
                "level": "2",
                "computed_weekly": 1086.00,
                "actual_weekly": 1071.20,
                "within_tolerance": False,
                "recommended_action": "use_computed",
            },
        ],
    }

    hints = build_scenario_review_hints({}, [scenario])

    hint = next(h for h in hints if h["code"] == "scenario_use_computed")
    assert hint["confidence"] == "high"
    assert "confirmed_external_dependency_multi_cell_variance" in hint["save_note"]
    assert any("printed $1,030.00" in item for item in hint["evidence"])


def test_scenario_use_computed_hint_separates_introduced_rows():
    scenario = {
        "period_effective_from": "2026-07-01",
        "status": "needs_attention",
        "sub_status": "partial_rule",
        "decision_recommendation": {
            "action": "use_computed",
            "basis": "confirmed_external_dependency_multi_cell_variance",
            "confidence": "high",
            "affected_cells": 1,
            "introduced_cells": 1,
            "introduced_action": "accept_table",
        },
        "cell_deltas": [
            {
                "band": "5",
                "level": "1",
                "computed_weekly": 1086.00,
                "actual_weekly": 1071.20,
                "within_tolerance": False,
                "recommended_action": "use_computed",
            },
            {
                "band": "6",
                "level": "D",
                "computed_weekly": None,
                "actual_weekly": 3650.00,
                "within_tolerance": False,
                "recommended_action": "accept_table",
            },
        ],
    }

    hints = build_scenario_review_hints({}, [scenario])

    hint = next(h for h in hints if h["code"] == "scenario_use_computed")
    assert "Computed variance cells: 1" in hint["evidence"]
    assert "Introduced rows accepted from table: 1" in hint["evidence"]
    assert all("Band 6" not in item for item in hint["evidence"])
    assert "introduced rows were kept" in hint["save_note"]


def test_scenario_human_review_hint_shows_values_and_fallback():
    scenario = {
        "period_effective_from": "2026-07-01",
        "status": "needs_attention",
        "sub_status": "conflict",
        "rule_quantum": "3%",
        "decision_recommendation": {
            "action": "needs_human_review",
            "basis": "isolated_variance_with_external_dependency",
            "fallback_action": "use_computed",
            "confidence": "medium",
        },
        "cell_deltas": [
            {
                "band": "5",
                "level": "1",
                "prior_weekly": 1000.00,
                "computed_weekly": 1030.00,
                "actual_weekly": 1040.00,
                "abs_delta": 10.00,
                "within_tolerance": False,
            },
        ],
    }

    hints = build_scenario_review_hints({}, [scenario])

    hint = next(h for h in hints if h["code"] == "scenario_inspect_values_before_choice")
    assert "Fallback action: use_computed" in hint["evidence"]
    assert any("computed $1,030.00" in item for item in hint["evidence"])


def test_scenario_rule_extraction_hint_points_upstream():
    scenario = {
        "period_effective_from": "2023-11-07",
        "status": "needs_attention",
        "sub_status": "conflict",
        "rule_quantum": "2.00% or $28.00 per week",
        "decision_recommendation": {
            "action": "needs_rule_extraction_review",
            "basis": "extracted_rule_conflicts_with_published_table_pattern",
            "confidence": "high",
            "implied_weekly_increase": 32.63,
            "mechanised_weekly_increase": 28.0,
            "consistent_offset": 4.63,
        },
        "cell_deltas": [
            {
                "band": "1",
                "level": "A",
                "prior_weekly": 1114.90,
                "computed_weekly": 1142.90,
                "actual_weekly": 1147.53,
                "abs_delta": 4.63,
                "within_tolerance": False,
            },
        ],
    }

    hints = build_scenario_review_hints({}, [scenario])

    hint = next(h for h in hints if h["code"] == "scenario_review_extracted_uplift_rule")
    assert hint["title"] == "Review extracted uplift rule"
    assert "correct the accepted rule" in hint["recommendation"]
    assert "Table implied weekly increase: 32.63" in hint["evidence"]
