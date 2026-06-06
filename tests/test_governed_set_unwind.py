"""Tests for governed_set.unwind() cascade + prune semantics."""
from __future__ import annotations

import pytest

from benchmarking_data_factory.governed_set import unwind


def _make_canonical_with_periods(periods):
    return {
        "agreement_id": "aetest01",
        "sections": {
            "uplifts": {"data": {"periods": list(periods)}},
        },
    }


def _p(effective_from, pay=True, rule=True):
    return {
        "effective_from": effective_from,
        "pay_table": {"tag": f"pt-{effective_from}"} if pay else None,
        "pay_table_governed_at": "2026-04-22T09:00:00Z" if pay else None,
        "uplift_rule": {"tag": f"ur-{effective_from}"} if rule else None,
        "uplift_rule_governed_at": "2026-04-22T09:00:00Z" if rule else None,
    }


def test_unwind_rejects_unknown_kind():
    canonical = _make_canonical_with_periods([_p("2025-07-01")])
    with pytest.raises(ValueError):
        unwind(canonical, "2025-07-01", "bogus_kind")


def test_unwind_raises_when_period_missing():
    canonical = _make_canonical_with_periods([_p("2025-07-01")])
    with pytest.raises(ValueError):
        unwind(canonical, "2099-01-01", "pay_table")


def test_unwind_clears_primary_slot_only_when_no_downstream():
    canonical = _make_canonical_with_periods([_p("2025-07-01")])
    summary = unwind(canonical, "2025-07-01", "pay_table")
    # Primary period had pay_table cleared but uplift_rule remained → period still there.
    periods = canonical["sections"]["uplifts"]["data"]["periods"]
    assert len(periods) == 1
    assert periods[0]["pay_table"] is None
    assert periods[0]["pay_table_governed_at"] is None
    assert periods[0]["uplift_rule"] is not None
    assert summary["downstream_cleared"] == []
    assert summary["periods_removed"] == []


def test_unwind_prunes_primary_when_both_slots_become_none():
    # Only pay_table is promoted on this period, no uplift_rule.
    canonical = _make_canonical_with_periods([_p("2025-07-01", pay=True, rule=False)])
    summary = unwind(canonical, "2025-07-01", "pay_table")
    periods = canonical["sections"]["uplifts"]["data"]["periods"]
    assert periods == []
    assert summary["periods_removed"] == ["2025-07-01"]
    assert summary["periods_remaining"] == []


def test_unwind_cascades_and_clears_both_slots_on_later_periods():
    canonical = _make_canonical_with_periods([
        _p("2025-07-01"),
        _p("2026-07-01"),
        _p("2027-07-01"),
    ])
    summary = unwind(canonical, "2025-07-01", "pay_table")
    periods = canonical["sections"]["uplifts"]["data"]["periods"]
    # 2025-07-01 keeps only uplift_rule (pay cleared). Later two periods pruned entirely.
    assert len(periods) == 1
    assert periods[0]["effective_from"] == "2025-07-01"
    assert periods[0]["pay_table"] is None
    assert periods[0]["uplift_rule"] is not None
    assert sorted([d["effective_from"] for d in summary["downstream_cleared"]]) == ["2026-07-01", "2027-07-01"]
    for d in summary["downstream_cleared"]:
        assert sorted(d["slots_cleared"]) == ["pay_table", "uplift_rule"]
    assert sorted(summary["periods_removed"]) == ["2026-07-01", "2027-07-01"]


def test_unwind_does_not_touch_earlier_periods():
    canonical = _make_canonical_with_periods([
        _p("2024-07-01"),
        _p("2025-07-01"),
        _p("2026-07-01"),
    ])
    unwind(canonical, "2025-07-01", "uplift_rule")
    periods = canonical["sections"]["uplifts"]["data"]["periods"]
    earlier = next(p for p in periods if p["effective_from"] == "2024-07-01")
    assert earlier["pay_table"] is not None
    assert earlier["uplift_rule"] is not None
    assert earlier["pay_table_governed_at"] is not None
    assert earlier["uplift_rule_governed_at"] is not None
