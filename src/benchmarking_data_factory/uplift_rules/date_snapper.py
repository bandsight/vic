"""Snap uplift-rule effective_dates to nearby saved pay-table effective_from dates.

Called from main.api_pay_save after tables are saved and to_dates recalculated.
Only mutates accepted rules; suggestions are left alone.

Rules of the snap (see briefs/uplift-rule-date-snap.md):
- Window: ±30 days between rule.effective_date and table.effective_from.
- Nearest table (smaller |days|) wins.
- Exact tie (equal absolute distance to two tables): leave rule unchanged, warn.
- Idempotent: re-running with same inputs produces no further changes.
- Already-snapped rules may re-snap to a different table if tables moved.
- If a snapped rule no longer has any table within window, restore from
  effective_date_original and clear audit fields.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


SNAP_WINDOW_DAYS = 30


def _parse_iso(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_best_table(
    rule_date: date, table_dates: list[date]
) -> tuple[date | None, str | None]:
    """Return (best_table_date, warning). best_table_date is None if no snap should occur.

    warning is a human-readable string when we refuse to snap (e.g. exact tie),
    otherwise None.
    """
    candidates: list[tuple[int, date]] = []
    for td in table_dates:
        delta = abs((td - rule_date).days)
        if delta <= SNAP_WINDOW_DAYS:
            candidates.append((delta, td))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: (x[0], x[1].isoformat()))
    best_delta, best_td = candidates[0]
    # Tie detection: any other candidate with same abs-delta?
    ties = [td for d, td in candidates if d == best_delta and td != best_td]
    if ties:
        tied_list = ", ".join(sorted({best_td.isoformat(), *[t.isoformat() for t in ties]}))
        return None, (
            f"Rule effective_date {rule_date.isoformat()} is equidistant between "
            f"pay tables at {tied_list} — refusing to snap; resolve by adjusting tables."
        )
    return best_td, None


def snap_rule_dates_to_tables(canonical: dict[str, Any]) -> dict[str, Any]:
    """Mutate canonical.sections.uplift_rules.data.accepted.document.rules in place.

    Returns a summary dict:
        {
          "snapped":   [{"period_label": "...", "from": "2027-07-10", "to": "2027-07-01"}, ...],
          "unchanged": [{"period_label": "..."}, ...],       # in-window, already aligned
          "restored":  [{"period_label": "...", "from": "2027-07-01", "to": "2027-07-10"}, ...],
          "warnings":  ["Rule effective_date ... is equidistant between ..."],
        }
    """
    sections = canonical.get("sections") or {}
    tables = (sections.get("pay_tables") or {}).get("tables") or []
    rules_section = sections.get("uplift_rules") or {}
    data = rules_section.get("data")
    summary: dict[str, Any] = {"snapped": [], "unchanged": [], "restored": [], "warnings": []}

    if not isinstance(data, dict):
        return summary
    accepted = data.get("accepted")
    if not isinstance(accepted, dict):
        return summary
    document = accepted.get("document")
    if not isinstance(document, dict):
        return summary
    rules = document.get("rules")
    if not isinstance(rules, list) or not rules:
        return summary

    table_dates = sorted({
        d for d in (_parse_iso((t or {}).get("effective_from")) for t in tables) if d is not None
    })

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        label = rule.get("period_label") or "(unlabeled rule)"
        current = _parse_iso(rule.get("effective_date"))
        if current is None:
            continue  # nothing to snap to/from

        original_str = rule.get("effective_date_original")
        baseline = _parse_iso(original_str) or current

        if not table_dates:
            # No tables at all → restore if previously snapped, else leave.
            if original_str and current != baseline:
                rule["effective_date"] = baseline.isoformat()
                rule.pop("effective_date_original", None)
                rule.pop("effective_date_snapped_at", None)
                summary["restored"].append(
                    {"period_label": label, "from": current.isoformat(), "to": baseline.isoformat()}
                )
            continue

        # Match against the baseline (pre-snap) date so re-runs remain stable.
        best, warning = _find_best_table(baseline, table_dates)
        if warning:
            summary["warnings"].append(warning)
            # On tie: do NOT mutate. If previously snapped, leave snap in place.
            continue

        if best is None:
            # Out of window. If previously snapped, restore.
            if original_str and current != baseline:
                rule["effective_date"] = baseline.isoformat()
                rule.pop("effective_date_original", None)
                rule.pop("effective_date_snapped_at", None)
                summary["restored"].append(
                    {"period_label": label, "from": current.isoformat(), "to": baseline.isoformat()}
                )
            continue

        # In-window. Snap (or no-op if already aligned).
        if best == current:
            summary["unchanged"].append({"period_label": label})
            continue

        if original_str is None:
            rule["effective_date_original"] = baseline.isoformat()
        rule["effective_date"] = best.isoformat()
        rule["effective_date_snapped_at"] = _now_iso()
        summary["snapped"].append(
            {"period_label": label, "from": current.isoformat(), "to": best.isoformat()}
        )

    return summary
