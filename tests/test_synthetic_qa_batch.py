from __future__ import annotations

from scripts.synthetic_qa_batch import (
    computed_overrides,
    filter_out_of_scope_specialist_tables,
    rule_extraction_review_blockers,
    resolve_cohorts,
    split_like_row,
)


def _table(title: str, rows: list[dict], effective: str = "2022-11-07") -> dict:
    return {
        "table_title": title,
        "effective_from": effective,
        "rate_kind": "annual",
        "rows": rows,
    }


def test_specialist_appendix_tables_are_removed_before_cohort_qa():
    tables = [
        _table("Base pay rates", [{"band": "1", "level": "A", "annual_rate": 60000}]),
        _table("M&CH Nurse Base Pay Rates", [{"band": "1", "level": "A", "annual_rate": 90000}]),
    ]

    filtered, decisions = filter_out_of_scope_specialist_tables(tables)

    assert [table["table_title"] for table in filtered] == ["Base pay rates"]
    assert decisions == [
        "Source hygiene excluded specialist appendix pay table M&CH Nurse Base Pay Rates | 2022-11-07 | annual before benchmark QA."
    ]


def test_indoor_outdoor_tables_merge_missing_lower_bands_only():
    indoor = _table(
        "Indoor - Other than Physical & Community Services",
        [
            {"band": "3", "level": "A", "annual_rate": 62000},
            {"band": "4", "level": "A", "annual_rate": 65000},
            {"band": "6", "level": "A", "annual_rate": 81000},
        ],
    )
    outdoor = _table(
        "Outdoor - Physical & Community Services inclusive of industry allowance",
        [
            {"band": "1", "level": "A", "annual_rate": 57000},
            {"band": "2", "level": "A", "annual_rate": 59000},
            {"band": "3", "level": "A", "annual_rate": 61000},
            {"band": "4", "level": "A", "annual_rate": 64000},
        ],
    )

    resolved, decisions, blockers = resolve_cohorts([indoor, outdoor], "Mansfield")

    assert blockers == []
    assert len(resolved) == 1
    cells = {(str(row["band"]), str(row["level"])): row["annual_rate"] for row in resolved[0]["rows"]}
    assert cells[("1", "A")] == 57000
    assert cells[("2", "A")] == 59000
    assert cells[("3", "A")] == 62000
    assert cells[("4", "A")] == 65000
    assert cells[("6", "A")] == 81000
    assert any("Indoor/Outdoor QA retained Indoor benchmark" in decision for decision in decisions)


def test_indoor_outdoor_selection_crosses_rate_kind_when_outdoor_is_loaded():
    indoor = _table(
        "Indoor - Other than Physical & Community Services",
        [
            {"band": "1", "level": "A", "annual_rate": 59430.80},
            {"band": "2", "level": "A", "annual_rate": 61562.80},
        ],
        effective="2023-11-07",
    )
    outdoor = {
        "table_title": "Outdoor - Physical & Community Services inclusive of industry allowance",
        "effective_from": "2023-11-07",
        "rate_kind": "weekly",
        "rows": [
            {"band": "1", "level": "A", "weekly_rate": 1176.18},
            {"band": "2", "level": "A", "weekly_rate": 1217.18},
        ],
    }

    resolved, decisions, blockers = resolve_cohorts([indoor, outdoor], "Mansfield")

    assert blockers == []
    assert [table["table_title"] for table in resolved] == ["Indoor - Other than Physical & Community Services"]
    assert any("dropped loaded Outdoor" in decision for decision in decisions)


def test_split_like_row_does_not_treat_single_council_context_as_split():
    row = {
        "ae_id": "ae516687",
        "canonical_lga_short_name": "Mansfield",
        "source_name": "Mansfield Shire Council Enterprise Agreement 2022",
    }
    canonical = {
        "source_name": "Mansfield Shire Council Enterprise Agreement 2022",
        "overview": {
            "document_structure_notes": "Standard EBA with main clauses and appendix tables.",
        },
    }

    assert split_like_row("ae516687", row, canonical) is False


def test_split_like_row_detects_true_multi_council_agreement():
    row = {
        "ae_id": "ae532042__central_goldfields",
        "canonical_lga_short_name": "Central Goldfields",
        "source_name": "Ararat Rural City Council and Central Goldfields Shire Council Single Interest Employer Agreement",
    }

    assert split_like_row("ae532042__central_goldfields", row, {}) is True


def test_computed_overrides_does_not_accept_published_table_conflict_recommendations():
    result = {
        "scenarios": [
            {
                "period_effective_from": "2023-11-07",
                "status": "needs_attention",
                "cell_deltas": [
                    {
                        "band": "1",
                        "level": "A",
                        "within_tolerance": False,
                        "override_action": None,
                        "recommended_action": None,
                        "computed_weekly": 1142.90,
                        "actual_weekly": 1147.53,
                    },
                    {
                        "band": "1",
                        "level": "B",
                        "within_tolerance": False,
                        "override_action": None,
                        "recommended_action": None,
                        "computed_weekly": 1152.20,
                        "actual_weekly": 1156.83,
                    },
                ],
            }
        ]
    }

    overrides, decisions = computed_overrides(result)

    assert overrides == {}
    assert decisions == []


def test_computed_overrides_accepts_introduced_table_rows_only():
    result = {
        "scenarios": [
            {
                "period_effective_from": "2023-11-07",
                "status": "needs_attention",
                "cell_deltas": [
                    {
                        "band": "6",
                        "level": "D",
                        "within_tolerance": False,
                        "override_action": None,
                        "recommended_action": "accept_table",
                        "computed_weekly": None,
                        "actual_weekly": 1500.0,
                    },
                ],
            }
        ]
    }

    overrides, decisions = computed_overrides(result)

    assert overrides == {
        "2023-11-07": {
            "6:D": {"action": "accept", "weekly": 1500.0},
        }
    }
    assert decisions == [
        "Accepted 1 introduced table row(s) without prior-period equivalents in 2023-11-07."
    ]


def test_rule_extraction_review_blockers_stop_scenario_qa():
    result = {
        "scenarios": [
            {
                "period_effective_from": "2023-11-07",
                "rule_quantum": "2.00% or $28.00 per week",
                "decision_recommendation": {
                    "action": "needs_rule_extraction_review",
                    "affected_cells": 28,
                    "covered_cells": 30,
                    "mechanised_weekly_increase": 28.0,
                    "implied_weekly_increase": 32.63,
                },
            }
        ]
    }

    blockers = rule_extraction_review_blockers(result)

    assert blockers == [
        "Uplift rule extraction review required for 2023-11-07; rule 2.00% or $28.00 per week; "
        "28/30 cells conflict; rule implies $28.00/week but table implies $32.63/week. "
        "Fix the uplift rule/table binding before scenario QA."
    ]
