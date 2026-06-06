from __future__ import annotations

import re
from typing import Any, Callable


_SCENARIO_COMPUTED_NOTE_RE = re.compile(
    r"Used computed for\s+(?P<cell>[^\s(]+)\s+\((?P<period>\d{4}-\d{2}-\d{2})\)\s*[^0-9]*(?P<weekly>[0-9][0-9.]+)",
    re.IGNORECASE,
)


def _audit_excerpt(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _scenario_note_summary(notes: Any, overrides: Any = None) -> tuple[str, str | None]:
    full_note = str(notes or "").strip()
    if not full_note:
        return "Scenario table decisions recorded", None

    decisions_part, separator, reviewer_part = full_note.partition("---")
    computed_matches = list(_SCENARIO_COMPUTED_NOTE_RE.finditer(decisions_part))
    if computed_matches:
        periods = sorted({match.group("period") for match in computed_matches})
        period_preview = ", ".join(periods[:3])
        if len(periods) > 3:
            period_preview += f", +{len(periods) - 3} more"
        summary = (
            f"{len(computed_matches)} computed-rate selections"
            f" across {len(periods)} period{'s' if len(periods) != 1 else ''}"
            f" ({period_preview})."
        )
    elif isinstance(overrides, dict) and overrides:
        period_count = len(overrides)
        cell_count = sum(
            len(cells)
            for cells in overrides.values()
            if isinstance(cells, dict)
        )
        summary = (
            f"{cell_count} scenario override"
            f"{'' if cell_count == 1 else 's'} across {period_count} period"
            f"{'' if period_count == 1 else 's'}."
        )
    else:
        summary = _audit_excerpt(decisions_part)

    reviewer_note = _audit_excerpt(reviewer_part if separator else "", 120)
    if reviewer_note:
        summary = f"{summary} Reviewer note: {reviewer_note}"
    return summary, full_note if full_note != summary else None


def audit_row_level_treatment(
    sections: dict[str, Any],
    *,
    is_standard_band_level_row: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    pay_section = sections.get("pay_tables") if isinstance(sections, dict) else {}
    if not isinstance(pay_section, dict):
        pay_section = {}
    tables = pay_section.get("tables") if isinstance(pay_section.get("tables"), list) else []
    validations = pay_section.get("validations") if isinstance(pay_section.get("validations"), list) else []
    validation_items = [
        item for item in validations
        if isinstance(item, dict) and item.get("code") == "non_standard_band_level_rows"
    ]
    non_standard_rows: list[dict[str, Any]] = []
    affected_tables: set[int] = set()
    for table_idx, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        table_rows = table.get("rows") if isinstance(table.get("rows"), list) else []
        for row_idx, row in enumerate(table_rows):
            if not isinstance(row, dict) or is_standard_band_level_row(row):
                continue
            affected_tables.add(table_idx)
            non_standard_rows.append({
                "table_idx": table_idx,
                "row_idx": row_idx,
                "table_title": table.get("table_title") or f"Table {table_idx + 1}",
                "effective_from": table.get("effective_from"),
                "title": row.get("title") or "",
                "band": row.get("band"),
                "level": row.get("level"),
            })

    for item in validation_items:
        table_idx = item.get("table_idx")
        if isinstance(table_idx, int):
            affected_tables.add(table_idx)

    has_treatment = bool(non_standard_rows or validation_items)
    if has_treatment:
        row_count = len(non_standard_rows) or len(validation_items)
        table_count = len(affected_tables) or len(validation_items)
        status = "present"
        summary = (
            f"{row_count} non-standard row-level item(s) across {table_count} table(s); "
            "excluded from governed benchmark outputs."
        )
    elif tables:
        status = "not_detected"
        summary = "No non-standard row-level treatment detected in saved pay tables."
    else:
        status = "not_assessed"
        summary = "No saved pay tables assessed for row-level treatment."

    return {
        "status": status,
        "has_non_standard_row_level_treatment": has_treatment,
        "summary": summary,
        "non_standard_row_count": len(non_standard_rows),
        "affected_table_count": len(affected_tables),
        "validation_count": len(validation_items),
        "examples": non_standard_rows[:5],
    }


def audit_governed_events(
    ae_id: str,
    workspace: dict[str, Any],
    *,
    get_canonical: Callable[[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    canonical = get_canonical(ae_id)
    periods = ((((canonical.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
    pay_groups: dict[str, list[dict[str, Any]]] = {}
    rule_groups: dict[str, list[dict[str, Any]]] = {}
    for period in periods:
        if not isinstance(period, dict):
            continue
        if isinstance(period.get("pay_table"), dict) and period.get("pay_table_governed_at"):
            pay_groups.setdefault(str(period.get("pay_table_governed_at")), []).append(period)
        if isinstance(period.get("uplift_rule"), dict) and period.get("uplift_rule_governed_at"):
            rule_groups.setdefault(str(period.get("uplift_rule_governed_at")), []).append(period)

    events: list[dict[str, Any]] = []
    for governed_at, grouped in pay_groups.items():
        row_count = sum(len((period.get("pay_table") or {}).get("rows") or []) for period in grouped)
        events.append({
            "date": governed_at,
            "kind": "governance",
            "label": "Pay tables promoted",
            "detail": f"{len(grouped)} governed period(s), {row_count} weekly row(s)",
            "ae_id": ae_id,
            "source": "Governed Set",
        })
    for governed_at, grouped in rule_groups.items():
        events.append({
            "date": governed_at,
            "kind": "governance",
            "label": "Uplift rules promoted",
            "detail": f"{len(grouped)} governed period(s)",
            "ae_id": ae_id,
            "source": "Governed Set",
        })
    if workspace.get("scenario_saved_at"):
        scenario_summary, scenario_full_note = _scenario_note_summary(
            workspace.get("scenario_notes"),
            workspace.get("scenario_overrides"),
        )
        event = {
            "date": workspace.get("scenario_saved_at"),
            "kind": "validation",
            "label": "Scenario overrides saved",
            "detail": scenario_summary,
            "ae_id": ae_id,
            "source": "Scenario workspace",
        }
        if scenario_full_note:
            event["detail_full"] = scenario_full_note
        events.append(event)
    return events
