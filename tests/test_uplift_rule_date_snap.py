"""Tests for snap_rule_dates_to_tables()."""
from __future__ import annotations

import pytest

from benchmarking_data_factory.uplift_rules import snap_rule_dates_to_tables


def _canonical(tables: list[dict], rules: list[dict] | None, *, accepted: bool = True) -> dict:
    rules_data: dict = {}
    if rules is not None:
        doc = {"rules": rules}
        if accepted:
            rules_data["accepted"] = {"document": doc}
        else:
            rules_data["suggestion"] = {"document": doc}
    return {
        "agreement_id": "aetest01",
        "sections": {
            "pay_tables": {"tables": tables},
            "uplift_rules": {"data": rules_data} if rules_data else {"data": {}},
        },
    }


def _rule(label: str, date: str) -> dict:
    return {
        "period_label": label,
        "quantum": "3%",
        "effective_date": date,
    }


def _table(ef: str) -> dict:
    return {"effective_from": ef, "rate_kind": "weekly", "rows": []}


# -------- Within-window snap --------

def test_snaps_rule_nine_days_ahead_of_table():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[_rule("Year 4", "2027-07-10")],
    )
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-01"
    assert rule["effective_date_original"] == "2027-07-10"
    assert rule["effective_date_snapped_at"].startswith("20")
    assert summary["snapped"] == [{"period_label": "Year 4", "from": "2027-07-10", "to": "2027-07-01"}]
    assert summary["restored"] == []
    assert summary["warnings"] == []


def test_snaps_rule_behind_table_when_within_window():
    canonical = _canonical(
        tables=[_table("2027-07-15")],
        rules=[_rule("Year 4", "2027-07-01")],  # 14d behind → in window
    )
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-15"
    assert len(summary["snapped"]) == 1


# -------- Window boundary --------

def test_exactly_30_days_is_in_window():
    canonical = _canonical(
        tables=[_table("2027-06-01")],
        rules=[_rule("Y", "2027-07-01")],  # exactly 30d
    )
    snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-06-01"


def test_thirty_one_days_out_of_window():
    canonical = _canonical(
        tables=[_table("2027-05-31")],
        rules=[_rule("Y", "2027-07-01")],  # 31d
    )
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-01"  # unchanged
    assert "effective_date_original" not in rule
    assert summary["snapped"] == []


# -------- Nearest table wins --------

def test_snaps_to_nearest_table():
    canonical = _canonical(
        tables=[_table("2025-07-01"), _table("2025-07-12")],
        rules=[_rule("Year 2", "2025-07-10")],  # 9d from Jul-01, 2d from Jul-12 → Jul-12
    )
    snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2025-07-12"


# -------- Exact tie is refused --------

def test_exact_tie_refuses_to_snap_and_warns():
    canonical = _canonical(
        tables=[_table("2025-07-01"), _table("2025-07-15")],
        rules=[_rule("Y", "2025-07-08")],  # 7d from both
    )
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2025-07-08"
    assert "effective_date_original" not in rule
    assert summary["snapped"] == []
    assert len(summary["warnings"]) == 1
    assert "equidistant" in summary["warnings"][0]


# -------- Idempotence --------

def test_idempotent_second_run_is_noop():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[_rule("Year 4", "2027-07-10")],
    )
    snap_rule_dates_to_tables(canonical)
    first_snap_ts = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]["effective_date_snapped_at"]
    summary2 = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-01"
    assert rule["effective_date_original"] == "2027-07-10"
    # No additional snap reported
    assert summary2["snapped"] == []
    # Unchanged reported (already aligned against baseline)
    assert [u["period_label"] for u in summary2["unchanged"]] == ["Year 4"]
    # Timestamp preserved (no re-stamp on no-op)
    assert rule["effective_date_snapped_at"] == first_snap_ts


# -------- Re-snap to a different table when tables change --------

def test_resnap_to_different_table_when_tables_change():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[_rule("Year 4", "2027-07-10")],
    )
    snap_rule_dates_to_tables(canonical)
    # Now add a CLOSER table
    canonical["sections"]["pay_tables"]["tables"].append(_table("2027-07-09"))
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-09"  # closer to baseline 2027-07-10
    assert rule["effective_date_original"] == "2027-07-10"  # preserved earliest
    assert len(summary["snapped"]) == 1
    assert summary["snapped"][0]["to"] == "2027-07-09"


# -------- Restore when tables move out of window --------

def test_restore_when_all_tables_move_out_of_window():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[_rule("Year 4", "2027-07-10")],
    )
    snap_rule_dates_to_tables(canonical)
    # User deletes Table 4, leaving only a table far away
    canonical["sections"]["pay_tables"]["tables"] = [_table("2024-01-01")]
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-10"
    assert "effective_date_original" not in rule
    assert "effective_date_snapped_at" not in rule
    assert len(summary["restored"]) == 1


def test_restore_when_tables_list_empties():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[_rule("Year 4", "2027-07-10")],
    )
    snap_rule_dates_to_tables(canonical)
    canonical["sections"]["pay_tables"]["tables"] = []
    summary = snap_rule_dates_to_tables(canonical)
    rule = canonical["sections"]["uplift_rules"]["data"]["accepted"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-10"
    assert "effective_date_original" not in rule
    assert len(summary["restored"]) == 1


# -------- Only touches accepted rules --------

def test_does_not_snap_suggestion_rules():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[_rule("Year 4", "2027-07-10")],
        accepted=False,
    )
    summary = snap_rule_dates_to_tables(canonical)
    # suggestion rules are unchanged
    rule = canonical["sections"]["uplift_rules"]["data"]["suggestion"]["document"]["rules"][0]
    assert rule["effective_date"] == "2027-07-10"
    assert "effective_date_original" not in rule
    assert summary["snapped"] == []


# -------- Defensive: missing / malformed sections --------

def test_no_uplift_rules_section_returns_empty_summary():
    canonical = {"sections": {"pay_tables": {"tables": [_table("2027-07-01")]}}}
    summary = snap_rule_dates_to_tables(canonical)
    assert summary == {"snapped": [], "unchanged": [], "restored": [], "warnings": []}


def test_rule_with_missing_effective_date_is_skipped():
    canonical = _canonical(
        tables=[_table("2027-07-01")],
        rules=[{"period_label": "Y", "quantum": "3%"}],  # no effective_date
    )
    summary = snap_rule_dates_to_tables(canonical)
    assert summary["snapped"] == []
    assert summary["restored"] == []
