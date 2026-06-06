from __future__ import annotations

import hashlib
import json
from typing import Any


QA_EVENT_LIMIT = 500
QA_RATE_FIELDS = ("weekly_rate", "fortnightly_rate", "annual_rate", "hourly_rate")
QA_TABLE_DATE_FIELDS = (
    "effective_from",
    "to_date",
    "source_date_raw",
    "source_date_iso",
    "canonical_date_iso",
    "effective_from_note",
)


def _qa_json_equivalent(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)


def _qa_numeric_equivalent(left: Any, right: Any) -> bool:
    if left in ("", None) and right in ("", None):
        return True
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return _qa_json_equivalent(left, right)


def _short_qa_excerpt(value: Any, limit: int = 140) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[: limit - 1]}..."


def _make_qa_event(changed_at: str, event_type: str, source: str, scope: str, **fields: Any) -> dict[str, Any]:
    event = {
        "changed_at": changed_at,
        "changed_by": "local analyst",
        "event_type": event_type,
        "source": source,
        "scope": scope,
        **fields,
    }
    digest_input = json.dumps(event, sort_keys=True, default=str)
    event["event_id"] = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    return event


def _append_qa_events(existing_events: Any, new_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = [event for event in (existing_events or []) if isinstance(event, dict)]
    if not new_events:
        return existing[-QA_EVENT_LIMIT:]
    return (existing + new_events)[-QA_EVENT_LIMIT:]


def _normalise_scenario_override_payload(overrides: Any) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(overrides, dict):
        return {}
    clean: dict[str, dict[str, dict[str, Any]]] = {}
    for period, cells in overrides.items():
        if not isinstance(cells, dict):
            continue
        clean_cells: dict[str, dict[str, Any]] = {}
        for cell_key, override in cells.items():
            if not isinstance(override, dict):
                continue
            action = override.get("action")
            if not action:
                continue
            item: dict[str, Any] = {"action": str(action)}
            if override.get("weekly") is not None:
                item["weekly"] = override.get("weekly")
            clean_cells[str(cell_key)] = item
        if clean_cells:
            clean[str(period)] = clean_cells
    return clean


def _scenario_cell_parts(cell_key: str) -> tuple[str, str]:
    if ":" in cell_key:
        band, level = cell_key.split(":", 1)
        return band, level
    return cell_key, ""


def _scenario_override_events(
    previous_overrides: Any,
    next_overrides: Any,
    changed_at: str,
    change_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    previous = _normalise_scenario_override_payload(previous_overrides)
    next_state = _normalise_scenario_override_payload(next_overrides)
    context = change_context if isinstance(change_context, dict) else {}
    events: list[dict[str, Any]] = []

    for period in sorted(set(previous) | set(next_state)):
        previous_cells = previous.get(period) or {}
        next_cells = next_state.get(period) or {}
        for cell_key in sorted(set(previous_cells) | set(next_cells)):
            before = previous_cells.get(cell_key)
            after = next_cells.get(cell_key)
            if _qa_json_equivalent(before, after):
                continue
            band, level = _scenario_cell_parts(cell_key)
            if before is None:
                event_type = "scenario_cell_override_added"
            elif after is None:
                event_type = "scenario_cell_override_removed"
            else:
                event_type = "scenario_cell_override_changed"
            event_fields: dict[str, Any] = {
                "period_effective_from": period,
                "cell_key": cell_key,
                "band": band,
                "level": level,
                "previous": before,
                "next": after,
            }
            if after:
                event_fields["action"] = after.get("action")
                if after.get("weekly") is not None:
                    event_fields["weekly"] = after.get("weekly")
            if context:
                event_fields["change_context"] = context
            events.append(_make_qa_event(changed_at, event_type, "scenario_override", "cell", **event_fields))

    if events and context.get("scope") == "group":
        period = context.get("period") or (events[0].get("period_effective_from") if events else None)
        affected_count = context.get("affected_cells")
        if not isinstance(affected_count, int):
            affected_count = len(events)
        events.insert(
            0,
            _make_qa_event(
                changed_at,
                "scenario_group_override_applied",
                "scenario_override",
                "group",
                period_effective_from=period,
                action=context.get("action"),
                affected_count=affected_count,
                changed_cell_count=len(events),
                change_context=context,
            ),
        )
    return events


def _scenario_note_events(
    previous_note: Any,
    next_note: Any,
    changed_at: str,
    change_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if (previous_note or "") == (next_note or ""):
        return []
    fields: dict[str, Any] = {
        "previous_excerpt": _short_qa_excerpt(previous_note),
        "next_excerpt": _short_qa_excerpt(next_note),
        "previous_length": len(str(previous_note or "")),
        "next_length": len(str(next_note or "")),
    }
    if isinstance(change_context, dict) and change_context:
        fields["change_context"] = change_context
    return [_make_qa_event(changed_at, "scenario_note_updated", "scenario_override", "note", **fields)]


def _pay_table_label(table: Any, table_index: int) -> str:
    if not isinstance(table, dict):
        return f"Table {table_index + 1}"
    return str(table.get("table_title") or table.get("effective_from") or f"Table {table_index + 1}")


def _pay_row_key(row: Any, row_index: int) -> str:
    if not isinstance(row, dict):
        return f"row:{row_index}"
    band = row.get("band")
    level = row.get("level")
    if band is not None or level is not None:
        return f"{band}:{level}"
    title = row.get("title")
    if title:
        return f"title:{title}"
    return f"row:{row_index}"


def _pay_row_maps(rows: Any) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    mapped: dict[str, dict[str, Any]] = {}
    indexes: dict[str, int] = {}
    if not isinstance(rows, list):
        return mapped, indexes
    for idx, row in enumerate(rows):
        key = _pay_row_key(row, idx)
        if key in mapped:
            key = f"row:{idx}"
        mapped[key] = row if isinstance(row, dict) else {}
        indexes[key] = idx
    return mapped, indexes


def _pay_table_qa_events(
    previous_tables: Any,
    next_tables: Any,
    previous_notes: Any,
    next_notes: Any,
    previous_source_ref: Any,
    next_source_ref: Any,
    changed_at: str,
    change_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    previous = previous_tables if isinstance(previous_tables, list) else []
    next_state = next_tables if isinstance(next_tables, list) else []
    context = change_context if isinstance(change_context, dict) else {}
    events: list[dict[str, Any]] = []

    for table_index in range(max(len(previous), len(next_state))):
        before = previous[table_index] if table_index < len(previous) and isinstance(previous[table_index], dict) else None
        after = next_state[table_index] if table_index < len(next_state) and isinstance(next_state[table_index], dict) else None
        table_label = _pay_table_label(after or before, table_index)
        common_fields = {
            "table_index": table_index,
            "table_label": table_label,
        }
        if before is None and after is not None:
            events.append(_make_qa_event(
                changed_at,
                "pay_table_added",
                "pay_tables_save",
                "table",
                **common_fields,
                effective_from=after.get("effective_from"),
                row_count=len(after.get("rows") or []),
                change_context=context,
            ))
            continue
        if before is not None and after is None:
            events.append(_make_qa_event(
                changed_at,
                "pay_table_removed",
                "pay_tables_save",
                "table",
                **common_fields,
                effective_from=before.get("effective_from"),
                row_count=len(before.get("rows") or []),
                change_context=context,
            ))
            continue
        if before is None or after is None:
            continue

        for field in QA_TABLE_DATE_FIELDS:
            if (before.get(field) or None) != (after.get(field) or None):
                events.append(_make_qa_event(
                    changed_at,
                    "pay_table_date_changed",
                    "pay_tables_save",
                    "table_date",
                    **common_fields,
                    field=field,
                    previous=before.get(field),
                    next=after.get(field),
                    change_context=context,
                ))

        previous_rows, previous_indexes = _pay_row_maps(before.get("rows") or [])
        next_rows, next_indexes = _pay_row_maps(after.get("rows") or [])
        for row_key in sorted(set(previous_rows) | set(next_rows)):
            row_before = previous_rows.get(row_key)
            row_after = next_rows.get(row_key)
            row_index = next_indexes.get(row_key, previous_indexes.get(row_key))
            row_fields = {
                **common_fields,
                "row_key": row_key,
                "row_index": row_index,
                "band": (row_after or row_before or {}).get("band"),
                "level": (row_after or row_before or {}).get("level"),
                "title": (row_after or row_before or {}).get("title"),
            }
            if row_before is None and row_after is not None:
                events.append(_make_qa_event(
                    changed_at,
                    "pay_table_row_added",
                    "pay_tables_save",
                    "row",
                    **row_fields,
                    change_context=context,
                ))
                continue
            if row_before is not None and row_after is None:
                events.append(_make_qa_event(
                    changed_at,
                    "pay_table_row_removed",
                    "pay_tables_save",
                    "row",
                    **row_fields,
                    change_context=context,
                ))
                continue
            if row_before is None or row_after is None:
                continue
            for field in QA_RATE_FIELDS:
                if not _qa_numeric_equivalent(row_before.get(field), row_after.get(field)):
                    events.append(_make_qa_event(
                        changed_at,
                        "pay_table_cell_value_changed",
                        "pay_tables_save",
                        "cell",
                        **row_fields,
                        field=field,
                        previous=row_before.get(field),
                        next=row_after.get(field),
                        change_context=context,
                    ))

    if (previous_notes or "") != (next_notes or ""):
        events.append(_make_qa_event(
            changed_at,
            "pay_table_note_updated",
            "pay_tables_save",
            "note",
            previous_excerpt=_short_qa_excerpt(previous_notes),
            next_excerpt=_short_qa_excerpt(next_notes),
            previous_length=len(str(previous_notes or "")),
            next_length=len(str(next_notes or "")),
            change_context=context,
        ))

    if (previous_source_ref or "") != (next_source_ref or ""):
        events.append(_make_qa_event(
            changed_at,
            "pay_table_source_ref_updated",
            "pay_tables_save",
            "source_ref",
            previous=previous_source_ref,
            next=next_source_ref,
            change_context=context,
        ))

    return events
