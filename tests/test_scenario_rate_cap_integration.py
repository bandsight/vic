"""Integration tests for Phase 4A: rate cap lifecycle in scenario engine,
needs_review detection, and the rate cap confirm admin endpoint.
"""
from __future__ import annotations

import csv

import pytest
from fastapi.testclient import TestClient

from benchmarking_data_factory.scenario_testing.engine import run_scenarios
from benchmarking_data_factory.scenario_testing.schema import (
    ExternalDep,
    ScenarioResult,
)
from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (
    RATE_CAP_DATA_DIR,
    invalidate_caches as invalidate_rate_cap_caches,
)


# --------------------------------------------------------------------------
# Canonical dict builder — matches the real canonical schema the engine reads.
# --------------------------------------------------------------------------

def _build_banyule_canonical(target_period: str) -> dict:
    """Minimal canonical with one baseline period + one target period whose
    uplift rule references the rate cap.

    Engine expects:
      canonical.sections.pay_tables.status == "done"
      canonical.sections.pay_tables.tables = [{effective_from, table_title, rows}]
      canonical.sections.uplift_rules.data.accepted.document.rules = [{effective_date, quantum_type, quantum}]
      rows use keys band/level/weekly_rate
    """
    baseline_period = "2025-07-01"
    baseline_rows = [
        {"band": "5", "level": "1", "weekly_rate": 1000.00},
        {"band": "5", "level": "2", "weekly_rate": 1040.00},
    ]
    # Target-period tables reflect a 3% uplift from baseline.
    target_rows = [
        {"band": "5", "level": "1", "weekly_rate": 1030.00},
        {"band": "5", "level": "2", "weekly_rate": 1071.20},
    ]
    return {
        "agreement_id": "ae530550",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": baseline_period,
                        "table_title": "Band 5",
                        "rows": baseline_rows,
                    },
                    {
                        "effective_from": target_period,
                        "table_title": "Band 5",
                        "rows": target_rows,
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "rule_id": "R1",
                                    "effective_date": target_period,
                                    "quantum_type": "conditional",
                                    "quantum": "greater of 3% or gazetted rate cap or $46 per week",
                                }
                            ]
                        }
                    }
                }
            },
        },
    }


# --------------------------------------------------------------------------
# Tests 1 & 2: engine behaviour for confirmed and pending rate cap FYs
# --------------------------------------------------------------------------

def test_pct_or_floor_parses_floor_from_quantum_text():
    canonical = {
        "agreement_id": "aetest-floor",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2025-01-01",
                        "table_title": "Baseline",
                        "rows": [{"band": "1", "level": "A", "weekly_rate": 1000.00}],
                    },
                    {
                        "effective_from": "2026-01-01",
                        "table_title": "Year 2",
                        "rows": [{"band": "1", "level": "A", "weekly_rate": 1050.00}],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "effective_date": "2026-01-01",
                                    "period_label": "Year 2",
                                    "quantum_type": "pct_OR_floor",
                                    "quantum": "3% or $50 per week, whichever is greater",
                                }
                            ]
                        }
                    }
                }
            },
        },
    }

    result = run_scenarios(canonical, overrides=None)

    assert result[-1].status == "consistent"


def test_same_date_specialised_rule_does_not_stack_on_general_table():
    canonical = {
        "agreement_id": "aetest-specialised",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2025-01-01",
                        "table_title": "General baseline",
                        "rows": [{"band": "1", "level": "A", "weekly_rate": 1000.00}],
                    },
                    {
                        "effective_from": "2026-01-01",
                        "table_title": "General year 2",
                        "rows": [{"band": "1", "level": "A", "weekly_rate": 1030.00}],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "effective_date": "2026-01-01",
                                    "period_label": "Year 2",
                                    "quantum_type": "percentage",
                                    "quantum": "3%",
                                },
                                {
                                    "effective_date": "2026-01-01",
                                    "period_label": "MCHN Year 2",
                                    "quantum_type": "percentage",
                                    "quantum": "3%",
                                },
                            ]
                        }
                    }
                }
            },
        },
    }

    result = run_scenarios(canonical, overrides=None)

    assert result[-1].status == "consistent"


def test_multi_council_scenarios_do_not_use_foreign_council_baseline():
    canonical = {
        "agreement_id": "ae532042__central_goldfields",
        "source_name": "Ararat Rural City Council and Central Goldfields Shire Council Single Interest Employer Agreement",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2024-07-01",
                        "table_title": "Ararat Rural City Council Wage Rates",
                        "rows": [{"band": "1", "level": "A", "weekly_rate": 1000.00}],
                    },
                    {
                        "effective_from": "2024-11-01",
                        "table_title": "WAGE RATES - November 2024",
                        "rows": [{"band": "1", "level": "A", "weekly_rate": 1020.00}],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "effective_date": "2024-07-01",
                                    "period_label": "Year 1 (Ararat)",
                                    "quantum_type": "pct",
                                    "quantum": "4%",
                                },
                                {
                                    "effective_date": "2024-11-01",
                                    "period_label": "Year 1 (Central Goldfields)",
                                    "quantum_type": "pct",
                                    "quantum": "3%",
                                },
                            ]
                        }
                    }
                }
            },
        },
    }

    result = run_scenarios(canonical, overrides=None, lga_short_name="Central Goldfields")

    assert len(result) == 1
    assert result[0].period_effective_from == "2024-11-01"
    assert result[0].status == "baseline"


def test_confirmed_rate_cap_with_floor_collapses_to_computable():
    """FY 2026-27 is confirmed; 3% floor > 2.75% cap → effective rate 3%.
    Engine should resolve the conditional rule and run it as a normal
    percentage uplift."""
    invalidate_rate_cap_caches()
    canonical = _build_banyule_canonical(target_period="2026-07-01")
    results = run_scenarios(canonical, overrides=None, lga_short_name="Banyule")

    target = next(
        (r for r in results if r.period_effective_from == "2026-07-01"), None
    )
    assert target is not None, f"no 2026-07-01 result in: {[r.period_effective_from for r in results]}"

    assert target.status in ("consistent", "needs_attention"), (
        f"expected consistent/needs_attention, got {target.status!r} "
        f"(sub={target.sub_status!r}, reason={target.reason!r})"
    )
    assert target.status != "table_resolved"
    assert target.status != "awaiting_input"
    # Rule quantum should now be a percentage string like "3.0000%"
    assert target.rule_quantum is not None
    assert "%" in target.rule_quantum
    assert target.rule_quantum[0].isdigit(), f"rule_quantum={target.rule_quantum!r}"
    # Exactly one dep, confirmed
    assert len(target.external_deps) == 1
    dep = target.external_deps[0]
    assert dep.dep_kind == "rate_cap"
    assert dep.dep_status == "confirmed"
    assert dep.financial_year == "2026-27"
    assert dep.confirmed_at  # non-empty
    assert dep.raw_rate_cap == pytest.approx(2.75)
    assert dep.effective_rate == pytest.approx(3.0)
    assert dep.resolution_note


def test_confirmed_rate_cap_systemic_conflict_recommends_computed():
    """A confirmed rate cap can justify computed values, but only when the
    variance is systemic rather than a single isolated row."""
    invalidate_rate_cap_caches()
    canonical = _build_banyule_canonical(target_period="2026-07-01")
    results = run_scenarios(canonical, overrides=None, lga_short_name="Banyule")

    target = next(r for r in results if r.period_effective_from == "2026-07-01")
    assert target.status == "needs_attention"
    assert target.sub_status == "conflict"
    assert target.decision_recommendation["action"] == "use_computed"
    assert target.decision_recommendation["basis"] == "confirmed_external_dependency_multi_cell_variance"
    failed = [delta for delta in target.cell_deltas if not delta.within_tolerance]
    assert len(failed) >= 2
    assert all(delta.recommended_action == "use_computed" for delta in failed)


def test_confirmed_rate_cap_partial_rule_accepts_introduced_rows():
    """Continuing rows can use computed values while a new row keeps the
    published table value when there is no prior-period comparator."""
    invalidate_rate_cap_caches()
    canonical = {
        "agreement_id": "aetest-introduced-row",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2025-07-01",
                        "table_title": "General benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 2000.00},
                            {"band": "1", "level": "B", "weekly_rate": 3000.00},
                        ],
                    },
                    {
                        "effective_from": "2026-07-01",
                        "table_title": "General benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 2032.00},
                            {"band": "1", "level": "B", "weekly_rate": 3032.00},
                            {"band": "6", "level": "D", "weekly_rate": 3650.00},
                        ],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "rule_id": "R1",
                                    "effective_date": "2026-07-01",
                                    "quantum_type": "conditional",
                                    "quantum": "2% or $32 per week or 100% of the gazetted rate cap, whichever is greater",
                                }
                            ]
                        }
                    }
                }
            },
        },
    }

    results = run_scenarios(canonical, overrides=None, lga_short_name="Nillumbik")

    target = next(r for r in results if r.period_effective_from == "2026-07-01")
    assert target.status == "needs_attention"
    assert target.sub_status == "partial_rule"
    assert target.decision_recommendation["action"] == "use_computed"
    assert target.decision_recommendation["introduced_cells"] == 1
    assert target.decision_recommendation["introduced_action"] == "accept_table"

    continuing = [
        delta for delta in target.cell_deltas
        if delta.band == "1" and not delta.within_tolerance
    ]
    introduced = next(delta for delta in target.cell_deltas if delta.band == "6")
    assert len(continuing) == 2
    assert all(delta.recommended_action == "use_computed" for delta in continuing)
    assert introduced.recommended_action == "accept_table"
    assert introduced.recommendation_basis.endswith("_introduced_row")


def test_systemic_stale_prior_table_values_recommend_computed():
    canonical = {
        "agreement_id": "aetest-stale-prior",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2022-11-07",
                        "table_title": "General benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 1114.90},
                            {"band": "1", "level": "B", "weekly_rate": 1124.20},
                            {"band": "2", "level": "A", "weekly_rate": 1155.90},
                        ],
                    },
                    {
                        "effective_from": "2023-11-07",
                        "table_title": "General benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 1114.90},
                            {"band": "1", "level": "B", "weekly_rate": 1124.20},
                            {"band": "2", "level": "A", "weekly_rate": 1155.90},
                        ],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "rule_id": "R1",
                                    "effective_date": "2023-11-07",
                                    "quantum_type": "pct_OR_floor",
                                    "quantum": "2.00% or $28.00 (whichever is greater) per week",
                                    "quantum_floor": "$28.00",
                                }
                            ]
                        }
                    }
                }
            },
        },
    }

    results = run_scenarios(canonical, overrides=None, lga_short_name="Mansfield")

    target = next(r for r in results if r.period_effective_from == "2023-11-07")
    assert target.status == "needs_attention"
    assert target.decision_recommendation["action"] == "use_computed"
    assert target.decision_recommendation["basis"] == "systemic_stale_prior_table_values"
    failed = [delta for delta in target.cell_deltas if not delta.within_tolerance]
    assert all(delta.recommended_action == "use_computed" for delta in failed)


def test_systemic_published_table_offset_flags_rule_extraction_review():
    canonical = {
        "agreement_id": "aetest-table-offset",
        "sections": {
            "pay_tables": {
                "status": "done",
                "tables": [
                    {
                        "effective_from": "2022-11-07",
                        "table_title": "General benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 1114.90},
                            {"band": "1", "level": "B", "weekly_rate": 1124.20},
                            {"band": "2", "level": "A", "weekly_rate": 1155.90},
                        ],
                    },
                    {
                        "effective_from": "2023-11-07",
                        "table_title": "General benchmark",
                        "rows": [
                            {"band": "1", "level": "A", "weekly_rate": 1147.53},
                            {"band": "1", "level": "B", "weekly_rate": 1156.83},
                            {"band": "2", "level": "A", "weekly_rate": 1188.53},
                        ],
                    },
                ],
            },
            "uplift_rules": {
                "data": {
                    "accepted": {
                        "document": {
                            "rules": [
                                {
                                    "rule_id": "R1",
                                    "effective_date": "2023-11-07",
                                    "quantum_type": "pct_OR_floor",
                                    "quantum": "2.00% or $28.00 (whichever is greater) per week",
                                    "quantum_floor": "$28.00",
                                }
                            ]
                        }
                    }
                }
            },
        },
    }

    results = run_scenarios(canonical, overrides=None, lga_short_name="Mansfield")

    target = next(r for r in results if r.period_effective_from == "2023-11-07")
    assert target.status == "needs_attention"
    assert target.decision_recommendation["action"] == "needs_rule_extraction_review"
    assert target.decision_recommendation["basis"] == "extracted_rule_conflicts_with_published_table_pattern"
    assert target.decision_recommendation["implied_weekly_increase"] == 32.63
    assert target.decision_recommendation["mechanised_weekly_increase"] == 28.0
    failed = [delta for delta in target.cell_deltas if not delta.within_tolerance]
    assert all(delta.recommended_action is None for delta in failed)


def test_confirmed_rate_cap_isolated_conflict_still_requires_review():
    invalidate_rate_cap_caches()
    canonical = _build_banyule_canonical(target_period="2026-07-01")
    # Make one row match the computed $46 floor outcome, leaving one isolated variance.
    canonical["sections"]["pay_tables"]["tables"][1]["rows"][0]["weekly_rate"] = 1046.00
    results = run_scenarios(canonical, overrides=None, lga_short_name="Banyule")

    target = next(r for r in results if r.period_effective_from == "2026-07-01")
    assert target.status == "needs_attention"
    assert target.sub_status == "conflict"
    assert target.decision_recommendation["action"] == "needs_human_review"
    assert target.decision_recommendation["basis"] == "isolated_variance_with_external_dependency"
    assert all(delta.recommended_action is None for delta in target.cell_deltas)


def test_pending_rate_cap_emits_table_resolved():
    """FY 2027-28 is pending_announcement → engine emits table_resolved with
    external dep dep_status='pending'."""
    invalidate_rate_cap_caches()
    canonical = _build_banyule_canonical(target_period="2027-07-01")
    results = run_scenarios(canonical, overrides=None, lga_short_name="Banyule")

    target = next(
        (r for r in results if r.period_effective_from == "2027-07-01"), None
    )
    assert target is not None, f"no 2027-07-01 result in: {[r.period_effective_from for r in results]}"

    assert target.status == "table_resolved", (
        f"expected table_resolved, got {target.status!r} "
        f"(sub={target.sub_status!r}, reason={target.reason!r})"
    )
    assert target.sub_status == "rate_cap_pending"
    assert len(target.external_deps) == 1
    dep = target.external_deps[0]
    assert dep.dep_status == "pending"
    assert dep.financial_year == "2027-28"
    assert dep.confirmed_at is None
    assert len(target.cell_deltas) > 0


# --------------------------------------------------------------------------
# Tests 3 & 4: _apply_needs_review logic
# --------------------------------------------------------------------------

def _make_table_resolved_result(
    confirmed_at: str | None, dep_status: str = "confirmed"
) -> ScenarioResult:
    dep = ExternalDep(
        dep_key="vic_gazetted_cap:2027-28",
        dep_kind="rate_cap",
        financial_year="2027-28",
        dep_status=dep_status,
        confirmed_at=confirmed_at,
    )
    return ScenarioResult(
        ae_id="ae530550",
        period_effective_from="2027-07-01",
        period_label="2027-07-01",
        status="table_resolved",
        sub_status="rate_cap_pending",
        reason="working assumption from tables",
        rule_id="R1",
        rule_quantum="greater of 3% or gazetted rate cap or $46 per week",
        prior_period_effective_from="2026-07-01",
        table_names=("Band 5",),
        cell_deltas=(),
        external_deps=(dep,),
    )


def test_needs_review_when_dep_confirmed_after_save():
    """Dep confirmed_at > saved_at → status flips to needs_review."""
    from main import _apply_needs_review

    result = _make_table_resolved_result(
        confirmed_at="2026-05-01T00:00:00+00:00",
        dep_status="confirmed",
    )
    out = _apply_needs_review([result], saved_at="2026-04-15T00:00:00+00:00")
    assert len(out) == 1
    assert out[0].status == "needs_review"
    assert out[0].sub_status == "rate_cap_confirmed_since_save"
    assert "dep confirmed" in out[0].reason


def test_needs_review_not_triggered_when_dep_unchanged():
    """Dep confirmed_at < saved_at → status stays table_resolved."""
    from main import _apply_needs_review

    result = _make_table_resolved_result(
        confirmed_at="2026-03-01T00:00:00+00:00",
        dep_status="confirmed",
    )
    out = _apply_needs_review([result], saved_at="2026-04-15T00:00:00+00:00")
    assert len(out) == 1
    assert out[0].status == "table_resolved"
    assert out[0].sub_status == "rate_cap_pending"


# --------------------------------------------------------------------------
# Test 5: rate cap confirm endpoint updates both CSVs and invalidates cache
# --------------------------------------------------------------------------

YEAR_STATUS_PATH = RATE_CAP_DATA_DIR / "rate-cap-year-status.csv"
STANDARD_CAPS_PATH = RATE_CAP_DATA_DIR / "standard-statewide-rate-caps.csv"


@pytest.fixture
def restore_rate_cap_csvs():
    """Snapshot both rate cap CSVs before the test; restore after."""
    year_status_original = YEAR_STATUS_PATH.read_text(encoding="utf-8")
    standard_caps_original = STANDARD_CAPS_PATH.read_text(encoding="utf-8")
    try:
        yield
    finally:
        YEAR_STATUS_PATH.write_text(year_status_original, encoding="utf-8")
        STANDARD_CAPS_PATH.write_text(standard_caps_original, encoding="utf-8")
        invalidate_rate_cap_caches()


def test_rate_cap_confirm_endpoint_updates_both_csvs_and_invalidates_cache(
    restore_rate_cap_csvs,
):
    """POST /api/rate-caps/confirm should flip 2027-28 to confirmed in the
    year-status CSV and upsert 2027-28 into the standard caps CSV, then
    invalidate caches so subsequent lookups see the new values."""
    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/rate-caps/confirm",
        json={
            "financial_year": "2027-28",
            "rate_cap_value": 3.00,
            "confirmed_date": "2026-05-15",
            "notes": "Test confirmation (synthetic)",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["financial_year"] == "2027-28"
    assert body["rate_cap_value"] == 3.00
    assert body["confirmed_date"] == "2026-05-15"

    # Year-status CSV: 2027-28 now confirmed
    with YEAR_STATUS_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    target = next(r for r in rows if r["financial_year"] == "2027-28")
    assert target["resolution_status"] == "confirmed"
    assert target["confirmed_date"] == "2026-05-15"

    # Standard caps CSV: 2027-28 now has value 3.00
    with STANDARD_CAPS_PATH.open(newline="", encoding="utf-8") as f:
        std_rows = list(csv.DictReader(f))
    std_target = next(r for r in std_rows if r["period_year_label"] == "2027-28")
    assert float(std_target["rate_cap_value"]) == 3.00

    # Cache invalidation: resolver now returns the new status
    from benchmarking_data_factory.uplift_rules.rate_cap.resolver import (
        get_year_status_row,
    )
    fresh = get_year_status_row("2027-28")
    assert fresh is not None
    assert fresh["resolution_status"] == "confirmed"
