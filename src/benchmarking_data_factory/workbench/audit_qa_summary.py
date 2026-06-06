from __future__ import annotations

from collections import Counter
import json
import re
from typing import Any, Callable


def _audit_qa_label(event_type: Any) -> str:
    labels = {
        "pay_table_added": "Table added",
        "pay_table_removed": "Table removed",
        "pay_table_date_changed": "Effective date changed",
        "pay_table_cell_value_changed": "Pay rate changed",
        "pay_table_note_updated": "Reviewer note updated",
        "pay_table_source_ref_updated": "Source reference updated",
        "pay_table_row_added": "Row added",
        "pay_table_row_removed": "Row removed",
        "scenario_cell_override_added": "Scenario decision saved",
        "scenario_cell_override_changed": "Scenario decision changed",
        "scenario_cell_override_removed": "Scenario decision removed",
        "scenario_group_override_applied": "Scenario group decision saved",
        "scenario_note_updated": "Scenario note updated",
        "scenario_overrides_cleared": "Scenario decisions cleared",
    }
    clean = str(event_type or "Reviewer change")
    return labels.get(clean, clean.replace("_", " ").title())


def _audit_qa_count_label(event_type: Any, count: int) -> str:
    if count == 1:
        return _audit_qa_label(event_type)
    plurals = {
        "pay_table_added": "Tables added",
        "pay_table_removed": "Tables removed",
        "pay_table_date_changed": "Effective dates changed",
        "pay_table_cell_value_changed": "Pay rates changed",
        "pay_table_note_updated": "Reviewer notes updated",
        "pay_table_source_ref_updated": "Source references updated",
        "pay_table_row_added": "Rows added",
        "pay_table_row_removed": "Rows removed",
        "scenario_cell_override_added": "Scenario decisions saved",
        "scenario_cell_override_changed": "Scenario decisions changed",
        "scenario_cell_override_removed": "Scenario decisions removed",
        "scenario_group_override_applied": "Scenario group decisions saved",
        "scenario_note_updated": "Scenario notes updated",
        "scenario_overrides_cleared": "Scenario decisions cleared",
    }
    clean = str(event_type or "")
    return plurals.get(clean, f"{_audit_qa_label(event_type)}s")


def _audit_qa_value(value: Any) -> str:
    if value in (None, ""):
        return "blank"
    if isinstance(value, dict):
        if value.get("action") and value.get("weekly") is not None:
            return f"{value.get('action')} {value.get('weekly')}"
        if value.get("action"):
            return str(value.get("action"))
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _audit_qa_detail(event: dict[str, Any]) -> str:
    parts: list[str] = []
    if event.get("period_effective_from"):
        parts.append(str(event.get("period_effective_from")))
    if event.get("table_label"):
        parts.append(str(event.get("table_label")))
    if event.get("cell_key"):
        parts.append(str(event.get("cell_key")))
    if event.get("row_key"):
        parts.append(str(event.get("row_key")))
    if event.get("field"):
        parts.append(str(event.get("field")))
    if event.get("action"):
        parts.append(str(event.get("action")).replace("_", " "))
    if event.get("affected_count") is not None:
        count = event.get("affected_count")
        parts.append(f"{count} cell{'s' if count != 1 else ''}")
    if "previous" in event or "next" in event:
        parts.append(f"{_audit_qa_value(event.get('previous'))} to {_audit_qa_value(event.get('next'))}")
    if event.get("previous_length") is not None or event.get("next_length") is not None:
        parts.append(f"note length {event.get('previous_length') or 0} to {event.get('next_length') or 0} characters")
    return ", ".join(parts) or "Reviewer change recorded"


def _audit_qa_fields(event: dict[str, Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    if "previous" in event or "next" in event:
        fields.append({
            "field": str(event.get("field") or event.get("cell_key") or event.get("row_key") or "Value"),
            "from": _audit_qa_value(event.get("previous")),
            "to": _audit_qa_value(event.get("next")),
        })
    if event.get("affected_count") is not None:
        fields.append({
            "field": "Affected cells",
            "from": "",
            "to": str(event.get("affected_count")),
        })
    if event.get("previous_length") is not None or event.get("next_length") is not None:
        fields.append({
            "field": "Note length",
            "from": str(event.get("previous_length") or 0),
            "to": str(event.get("next_length") or 0),
        })
    if event.get("scope"):
        fields.append({
            "field": "Scope",
            "from": "",
            "to": str(event.get("scope")),
        })
    return fields[:4]


def audit_qa_events(
    ae_id: str,
    workspace: dict[str, Any],
    *,
    sort_key: Callable[[dict[str, Any]], tuple[Any, ...]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    qa_events = workspace.get("qa_events") if isinstance(workspace, dict) else {}
    if not isinstance(qa_events, dict):
        return [], []
    sources = (
        ("Pay-table review", qa_events.get("pay_tables") or []),
        ("Scenario review", qa_events.get("scenarios") or []),
    )
    timeline: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for source_label, events in sources:
        for event in events:
            if not isinstance(event, dict):
                continue
            event_type = event.get("event_type")
            label = _audit_qa_label(event_type)
            detail = _audit_qa_detail(event)
            date_value = event.get("changed_at") or ""
            timeline.append({
                "date": date_value,
                "kind": "qa",
                "label": label,
                "detail": detail,
                "ae_id": ae_id,
                "source": source_label,
                "event_type": event_type,
            })
            changes.append({
                "date": date_value,
                "kind": "qa",
                "ae_id": ae_id,
                "source": source_label,
                "event_type": event_type,
                "summary": label,
                "detail": detail,
                "fields": _audit_qa_fields(event),
            })
    return timeline, sorted(changes, key=sort_key)


def _audit_count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or f'{singular}s')}"


def _audit_excerpt(value: Any, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _audit_unique_values(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _audit_excerpt(value, 120)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _audit_human_list(values: list[Any], limit: int = 4) -> str:
    unique = _audit_unique_values(values)
    if not unique:
        return ""
    visible = unique[:limit]
    if len(unique) > limit:
        visible.append(f"{len(unique) - limit} more")
    if len(visible) == 1:
        return visible[0]
    if len(visible) == 2:
        return f"{visible[0]} and {visible[1]}"
    return f"{', '.join(visible[:-1])}, and {visible[-1]}"


def _audit_period_for_event(event: dict[str, Any]) -> str:
    return str(event.get("period_effective_from") or event.get("effective_from") or "").strip()


def _audit_event_note(event: dict[str, Any]) -> str:
    for key in ("next_excerpt", "next", "previous_excerpt"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return _audit_excerpt(value)
    return ""


def _audit_scenario_action(event: dict[str, Any]) -> str:
    next_value = event.get("next")
    if isinstance(next_value, dict) and next_value.get("action"):
        return str(next_value.get("action"))
    context = event.get("change_context") if isinstance(event.get("change_context"), dict) else {}
    return str(event.get("action") or context.get("action") or "").strip()


def _audit_action_label(action: str) -> str:
    labels = {
        "accept": "accepted source rate",
        "accept_all": "accepted source rate",
        "use_computed": "used computed rate",
        "use_computed_all": "used computed rate",
        "delete": "excluded cell",
        "delete_all": "excluded cell",
    }
    clean = str(action or "").strip().lower()
    return labels.get(clean, clean.replace("_", " ") or "review decision")


def _audit_pay_table_note_source_phrase(note_count: int, source_count: int) -> str:
    if note_count and source_count:
        if note_count == 1 and source_count == 1:
            return "updated the reviewer note and source reference"
        return f"made {_audit_count_phrase(note_count + source_count, 'note/source update')}"
    if note_count:
        return f"updated {_audit_count_phrase(note_count, 'reviewer note')}"
    if source_count:
        return f"updated {_audit_count_phrase(source_count, 'source reference')}"
    return ""


def _audit_raw_qa_records(workspace_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pay_events: list[dict[str, Any]] = []
    scenario_events: list[dict[str, Any]] = []
    for ae_id, workspace in workspace_by_id.items():
        qa_events = workspace.get("qa_events") if isinstance(workspace, dict) else {}
        if not isinstance(qa_events, dict):
            continue
        for event in qa_events.get("pay_tables") or []:
            if isinstance(event, dict):
                pay_events.append({**event, "ae_id": ae_id})
        for event in qa_events.get("scenarios") or []:
            if isinstance(event, dict):
                scenario_events.append({**event, "ae_id": ae_id})
    return pay_events, scenario_events


def _audit_pay_table_qa_brief(pay_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pay_events:
        return None
    counts = Counter(str(event.get("event_type") or "") for event in pay_events)
    periods = _audit_unique_values([_audit_period_for_event(event) for event in pay_events])
    tables = _audit_unique_values([event.get("table_label") for event in pay_events])
    table_scope = f" for {_audit_human_list(tables, limit=3)}" if tables else ""
    body_parts: list[str] = []
    if counts["pay_table_added"]:
        body_parts.append(f"The pay-table review saved {_audit_count_phrase(counts['pay_table_added'], 'new table')}{table_scope}.")
    elif counts["pay_table_removed"]:
        body_parts.append(f"The pay-table review removed {_audit_count_phrase(counts['pay_table_removed'], 'table')}{table_scope}.")
    else:
        body_parts.append(f"The pay-table review updated the saved table evidence{table_scope}.")

    follow_up_actions: list[str] = []
    if counts["pay_table_date_changed"]:
        follow_up_actions.append(f"adjusted {_audit_count_phrase(counts['pay_table_date_changed'], 'effective date')}")
    if counts["pay_table_cell_value_changed"]:
        follow_up_actions.append(f"edited {_audit_count_phrase(counts['pay_table_cell_value_changed'], 'pay rate')}")
    if counts["pay_table_row_added"] or counts["pay_table_row_removed"]:
        row_count = counts["pay_table_row_added"] + counts["pay_table_row_removed"]
        follow_up_actions.append(f"changed {_audit_count_phrase(row_count, 'table row')}")
    note_source_phrase = _audit_pay_table_note_source_phrase(
        counts["pay_table_note_updated"],
        counts["pay_table_source_ref_updated"],
    )
    if note_source_phrase:
        follow_up_actions.append(note_source_phrase)
    if follow_up_actions:
        body_parts.append(f"It also {_audit_human_list(follow_up_actions)}.")
    if periods:
        body_parts.append(f"Effective periods reviewed: {_audit_human_list(periods)}.")
    notes = _audit_unique_values([
        _audit_event_note(event)
        for event in pay_events
        if event.get("event_type") in {"pay_table_note_updated", "pay_table_source_ref_updated"}
    ])
    return {
        "category": "pay_tables",
        "heading": "Pay-table review",
        "body": " ".join(body_parts),
        "impact": "These saved tables are now the inputs for scenario testing and any governed pay-table promotion.",
        "event_count": len(pay_events),
        "periods": periods[:8],
        "ae_ids": _audit_unique_values([event.get("ae_id") for event in pay_events]),
        "notes": notes[:4],
        "details": [_audit_qa_count_label(event_type, count) + f": {count}" for event_type, count in sorted(counts.items()) if event_type],
    }


def _audit_scenario_qa_brief(scenario_events: list[dict[str, Any]], workspace_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not scenario_events:
        return None
    counts = Counter(str(event.get("event_type") or "") for event in scenario_events)
    periods = _audit_unique_values([_audit_period_for_event(event) for event in scenario_events])
    cell_events = [
        event for event in scenario_events
        if str(event.get("event_type") or "").startswith("scenario_cell_override")
    ]
    cell_keys = {
        (str(event.get("ae_id") or ""), _audit_period_for_event(event), str(event.get("cell_key") or ""))
        for event in cell_events
        if event.get("cell_key")
    }
    group_events = [
        event for event in scenario_events
        if event.get("event_type") == "scenario_group_override_applied"
    ]
    group_affected = sum(int(event.get("affected_count") or 0) for event in group_events)
    decision_count = len(cell_keys) or max(group_affected, len(cell_events))
    current_cell_events = [
        event for event in cell_events
        if event.get("event_type") in {"scenario_cell_override_added", "scenario_cell_override_changed"}
    ]
    action_source = current_cell_events or group_events
    action_counts = Counter(
        _audit_action_label(_audit_scenario_action(event))
        for event in action_source
        if _audit_scenario_action(event)
    )
    action_detail = _audit_human_list([
        f"{count} {label}"
        for label, count in sorted(action_counts.items())
    ])
    notes = _audit_unique_values([
        _audit_event_note(event)
        for event in scenario_events
        if event.get("event_type") == "scenario_note_updated"
    ] + [
        workspace.get("scenario_notes")
        for workspace in workspace_by_id.values()
        if isinstance(workspace, dict) and workspace.get("scenario_notes")
    ])

    body_parts = [
        f"The scenario review saved {_audit_count_phrase(decision_count, 'cell decision')}."
    ]
    if periods:
        body_parts.append(f"Periods reviewed: {_audit_human_list(periods)}.")
    if action_detail:
        body_parts.append(f"Reviewer decisions: {action_detail}.")
    if group_events:
        body_parts.append(f"{_audit_count_phrase(len(group_events), 'group action')} recorded.")
    if counts["scenario_overrides_cleared"] or counts["scenario_cell_override_removed"]:
        body_parts.append("Earlier scenario overrides were cleared before the retained decisions were saved.")
    return {
        "category": "scenarios",
        "heading": "Scenario review",
        "body": " ".join(body_parts),
        "impact": "These decisions carry through when scenario-tested pay tables are promoted, including computed-rate selections, accepted source rates and exclusions.",
        "event_count": len(scenario_events),
        "periods": periods[:8],
        "ae_ids": _audit_unique_values([event.get("ae_id") for event in scenario_events]),
        "notes": notes[:4],
        "details": [_audit_qa_count_label(event_type, count) + f": {count}" for event_type, count in sorted(counts.items()) if event_type],
    }


def _audit_row_treatment_brief(row_level_treatment: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row_level_treatment, dict):
        return None
    has_treatment = bool(row_level_treatment.get("has_non_standard_row_level_treatment"))
    if not has_treatment:
        return None
    row_count = int(row_level_treatment.get("non_standard_row_count") or 0)
    table_count = int(row_level_treatment.get("affected_table_count") or 0)
    examples = _audit_unique_values([
        example.get("title") or f"Band {example.get('band')} Level {example.get('level')}"
        for example in row_level_treatment.get("examples") or []
        if isinstance(example, dict)
    ])
    body = (
        f"The review found {_audit_count_phrase(row_count, 'non-standard row')} "
        f"across {_audit_count_phrase(table_count, 'table')}."
    )
    if examples:
        body += f" Examples: {_audit_human_list(examples, limit=3)}."
    return {
        "category": "row_level_treatment",
        "heading": "Row-level treatment",
        "body": body,
        "impact": "These rows remain visible in the workspace evidence but are excluded from governed benchmark outputs so the dataset stays band/level comparable.",
        "event_count": row_level_treatment.get("validation_count") or row_count,
        "periods": [],
        "ae_ids": [],
        "notes": [],
        "details": [row_level_treatment.get("summary") or ""],
    }


def _audit_governed_brief(governed: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(governed, dict) or not (governed.get("periods") or governed.get("pay_table_rows")):
        return None
    pay_periods = int(governed.get("pay_table_periods") or 0)
    rule_periods = int(governed.get("uplift_rule_periods") or 0)
    rows = int(governed.get("pay_table_rows") or 0)
    body = (
        f"The latest governed set now contains {_audit_count_phrase(pay_periods, 'pay-table period')}, "
        f"{_audit_count_phrase(rule_periods, 'uplift-rule period')} and {_audit_count_phrase(rows, 'weekly pay row')}."
    )
    stamps = _audit_unique_values((governed.get("pay_table_governed_at") or []) + (governed.get("uplift_rule_governed_at") or []))
    if stamps:
        body += f" Governance stamps: {_audit_human_list(stamps, limit=3)}."
    return {
        "category": "governed_outputs",
        "heading": "Governed output impact",
        "body": body,
        "impact": "Downstream benchmark analysis reads these governed periods and rows after the QA decisions above have been applied.",
        "event_count": (governed.get("periods") or 0),
        "periods": [],
        "ae_ids": [],
        "notes": [],
        "details": [],
    }


def _audit_qa_brief(
    workspace_by_id: dict[str, dict[str, Any]],
    row_level_treatment: dict[str, Any],
    governed: dict[str, Any],
) -> list[dict[str, Any]]:
    pay_events, scenario_events = _audit_raw_qa_records(workspace_by_id)
    items = [
        _audit_pay_table_qa_brief(pay_events),
        _audit_scenario_qa_brief(scenario_events, workspace_by_id),
        _audit_row_treatment_brief(row_level_treatment),
        _audit_governed_brief(governed),
    ]
    return [item for item in items if item]
