"""Unwind (un-promote) scenario items from the Governed Set, with downstream cascade.

Rules (see briefs/governed-set-unwind.md):
- unwind(canonical, effective_from=E, kind=K) clears slot K on period E.
- Every period with effective_from > E has BOTH slots cleared (pay_table + uplift_rule).
- Any period ending up with both slots None is dropped from sections.uplifts.data.periods.
- Upstream draft sections (pay_tables, uplift_rules) are NEVER touched.
"""
from __future__ import annotations

from typing import Any


_VALID_KINDS = ("pay_table", "uplift_rule")


def _clear_slot(period: dict[str, Any], kind: str) -> None:
    period[kind] = None
    period[f"{kind}_governed_at"] = None


def _both_empty(period: dict[str, Any]) -> bool:
    return period.get("pay_table") is None and period.get("uplift_rule") is None


def unwind(
    canonical: dict[str, Any],
    effective_from: str,
    kind: str,
) -> dict[str, Any]:
    """See module docstring. Mutates canonical in place. Returns a summary dict."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind must be one of {_VALID_KINDS}, got {kind!r}")
    sections = canonical.setdefault("sections", {})
    uplifts = sections.setdefault("uplifts", {})
    data = uplifts.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"No governed period for effective_from={effective_from}")
    periods: list[dict[str, Any]] = data.get("periods") or []
    target = next((p for p in periods if p.get("effective_from") == effective_from), None)
    if target is None:
        raise ValueError(f"No governed period for effective_from={effective_from}")

    # 1. primary clear
    _clear_slot(target, kind)

    # 2. downstream cascade (both slots)
    downstream_cleared: list[dict[str, Any]] = []
    for q in periods:
        qef = q.get("effective_from") or ""
        if qef <= effective_from:
            continue
        had = []
        if q.get("pay_table") is not None:
            _clear_slot(q, "pay_table")
            had.append("pay_table")
        if q.get("uplift_rule") is not None:
            _clear_slot(q, "uplift_rule")
            had.append("uplift_rule")
        if had:
            downstream_cleared.append({
                "effective_from": qef,
                "slots_cleared": had,
            })

    # 3. prune empty + re-sort
    periods_removed: list[str] = [p["effective_from"] for p in periods if _both_empty(p)]
    remaining = [p for p in periods if not _both_empty(p)]
    remaining.sort(key=lambda p: p.get("effective_from") or "")
    data["periods"] = remaining

    return {
        "primary": {"effective_from": effective_from, "kind": kind},
        "downstream_cleared": downstream_cleared,
        "periods_removed": periods_removed,
        "periods_remaining": [
            {
                "effective_from": p["effective_from"],
                "pay_table_present": p.get("pay_table") is not None,
                "uplift_rule_present": p.get("uplift_rule") is not None,
            }
            for p in remaining
        ],
    }
