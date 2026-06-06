"""Invisible learning from review decisions.

This module does not mutate canonical records and does not decide future
reviews by itself. It turns saved human/pipeline choices into normalized
decision events so other modules can consume repeated patterns deliberately.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable


SCHEMA_VERSION = "review_learning.v1"
EXAMPLE_LIMIT = 5
FULL_REGRESSION_SUITE = "full"


PAY_EVENT_PATTERNS: dict[str, tuple[str, str]] = {
    "pay_table_added": ("pay_table_structure", "pay_table_added"),
    "pay_table_removed": ("pay_table_structure", "pay_table_removed"),
    "pay_table_date_changed": ("effective_date", "pay_table_effective_date_adjusted"),
    "pay_table_cell_value_changed": ("table_value", "pay_table_value_adjusted"),
    "pay_table_row_added": ("row_scope", "pay_table_row_added"),
    "pay_table_row_removed": ("row_scope", "pay_table_row_removed"),
    "pay_table_note_updated": ("review_note", "pay_table_note_recorded"),
    "pay_table_source_ref_updated": ("source_reference", "pay_table_source_ref_adjusted"),
}


def build_review_learning_snapshot(
    canonical_records: Iterable[tuple[str, dict[str, Any]]],
    *,
    scenario_states: dict[str, dict[str, Any]] | None = None,
    regression_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an invisible learning snapshot from canonical review decisions."""
    events: list[dict[str, Any]] = []
    scenario_states = scenario_states or {}
    for ae_id, canonical in canonical_records:
        if not isinstance(canonical, dict):
            continue
        events.extend(extract_review_decision_events(
            str(ae_id),
            canonical,
            scenario_state=scenario_states.get(str(ae_id)),
        ))

    patterns = _learned_patterns(events)
    policy_suggestions = _policy_suggestions(patterns)
    rule_promotions = evaluate_rule_promotions(policy_suggestions, regression_result=regression_result)
    return {
        "schema_version": SCHEMA_VERSION,
        "learning_mode": "invisible",
        "summary": {
            "agreements_scanned": len({event["ae_id"] for event in events}),
            "decision_events": len(events),
            "learned_patterns": len(patterns),
            "policy_suggestions": len(policy_suggestions),
            "rule_promotions": len(rule_promotions),
        },
        "decision_events": events,
        "learned_patterns": patterns,
        "policy_suggestions": policy_suggestions,
        "rule_promotions": rule_promotions,
    }


def extract_review_decision_events(
    ae_id: str,
    canonical: dict[str, Any],
    *,
    scenario_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Normalize one agreement's saved QA and scenario decisions."""
    events: list[dict[str, Any]] = []
    agreement_name = str(canonical.get("source_name") or ae_id)
    lga_short_name = canonical.get("canonical_lga_short_name")
    sections = canonical.get("sections") if isinstance(canonical.get("sections"), dict) else {}
    pay_section = sections.get("pay_tables") if isinstance(sections.get("pay_tables"), dict) else {}
    for index, event in enumerate(pay_section.get("qa_events") or []):
        if isinstance(event, dict):
            normalized = _normalise_pay_event(ae_id, agreement_name, lga_short_name, event, index)
            if normalized:
                events.append(normalized)

    uplift_section = sections.get("uplift_rules") if isinstance(sections.get("uplift_rules"), dict) else {}
    uplift_data = uplift_section.get("data") if isinstance(uplift_section.get("data"), dict) else {}
    for index, issue in enumerate(uplift_data.get("table_alignment_issues") or []):
        if isinstance(issue, dict):
            normalized = _normalise_uplift_alignment_issue(ae_id, agreement_name, lga_short_name, issue, index)
            if normalized:
                events.append(normalized)

    scenario_state = scenario_state if isinstance(scenario_state, dict) else {}
    for index, event in enumerate(scenario_state.get("audit_events") or []):
        if isinstance(event, dict):
            normalized = _normalise_scenario_event(ae_id, agreement_name, lga_short_name, event, index)
            if normalized:
                events.append(normalized)

    return events


def _normalise_pay_event(
    ae_id: str,
    agreement_name: str,
    lga_short_name: Any,
    event: dict[str, Any],
    index: int,
) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or "")
    decision_type, pattern = PAY_EVENT_PATTERNS.get(event_type, ("pay_table_review", event_type))
    if not pattern:
        return None
    period = event.get("effective_from") or event.get("period_effective_from")
    if event_type == "pay_table_date_changed":
        period = event.get("next") or event.get("previous") or period
    evidence = _compact_evidence([
        f"table={event.get('table_label')}" if event.get("table_label") else "",
        f"field={event.get('field')}" if event.get("field") else "",
        f"previous={event.get('previous')}" if event.get("previous") not in (None, "") else "",
        f"next={event.get('next')}" if event.get("next") not in (None, "") else "",
        f"row={event.get('row_key')}" if event.get("row_key") else "",
    ])
    return _decision_event(
        ae_id,
        agreement_name,
        lga_short_name,
        source="pay_tables.qa_events",
        index=index,
        raw_event=event,
        decision_type=decision_type,
        pattern=pattern,
        period=period,
        evidence=evidence,
        target={
            "table_label": event.get("table_label"),
            "row_key": event.get("row_key"),
            "field": event.get("field"),
            "scope": event.get("scope"),
        },
    )


def _normalise_uplift_alignment_issue(
    ae_id: str,
    agreement_name: str,
    lga_short_name: Any,
    issue: dict[str, Any],
    index: int,
) -> dict[str, Any] | None:
    code = str(issue.get("code") or "")
    if code != "uplift_rule_table_binding_conflict":
        return None
    table_names = issue.get("table_names") if isinstance(issue.get("table_names"), list) else []
    evidence = _compact_evidence([
        f"period={issue.get('period_effective_from')}" if issue.get("period_effective_from") else "",
        f"rule_quantum={issue.get('rule_quantum')}" if issue.get("rule_quantum") else "",
        f"affected={issue.get('affected_cells')}" if issue.get("affected_cells") else "",
        f"mechanised_weekly_increase={issue.get('mechanised_weekly_increase')}" if issue.get("mechanised_weekly_increase") is not None else "",
        f"implied_weekly_increase={issue.get('implied_weekly_increase')}" if issue.get("implied_weekly_increase") is not None else "",
        f"tables={'; '.join(str(name) for name in table_names[:3])}" if table_names else "",
    ])
    return _decision_event(
        ae_id,
        agreement_name,
        lga_short_name,
        source="uplift_rules.table_alignment_issues",
        index=index,
        raw_event={"event_type": code, **issue},
        decision_type="uplift_extraction_binding",
        pattern=code,
        period=issue.get("period_effective_from"),
        evidence=evidence,
        target={
            "period": issue.get("period_effective_from"),
            "rule_id": issue.get("rule_id"),
            "basis": issue.get("basis"),
            "level": issue.get("level"),
        },
    )


def _normalise_scenario_event(
    ae_id: str,
    agreement_name: str,
    lga_short_name: Any,
    event: dict[str, Any],
    index: int,
) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or "")
    context = event.get("change_context") if isinstance(event.get("change_context"), dict) else {}
    action = str(context.get("action") or event.get("action") or "")
    if event_type == "scenario_group_override_applied" or action == "use_computed_all":
        decision_type = "scenario_override"
        pattern = "scenario_group_use_computed"
    elif event_type in {"scenario_cell_override_added", "scenario_cell_override_changed"} and action == "use_computed":
        decision_type = "scenario_override"
        pattern = "scenario_cell_use_computed"
    elif event_type == "scenario_cell_override_removed":
        decision_type = "scenario_override"
        pattern = "scenario_override_removed"
    elif event_type == "scenario_note_updated":
        decision_type = "review_note"
        pattern = "scenario_note_recorded"
    elif event_type == "scenario_overrides_cleared":
        decision_type = "scenario_override"
        pattern = "scenario_overrides_cleared"
    else:
        decision_type = "scenario_review"
        pattern = event_type
    if not pattern:
        return None
    evidence = _compact_evidence([
        f"period={event.get('period_effective_from')}" if event.get("period_effective_from") else "",
        f"cell={event.get('cell_key')}" if event.get("cell_key") else "",
        f"band={event.get('band')}" if event.get("band") else "",
        f"level={event.get('level')}" if event.get("level") else "",
        f"action={action}" if action else "",
        f"affected={event.get('affected_count')}" if event.get("affected_count") else "",
    ])
    return _decision_event(
        ae_id,
        agreement_name,
        lga_short_name,
        source="scenario_overrides.audit_events",
        index=index,
        raw_event=event,
        decision_type=decision_type,
        pattern=pattern,
        period=event.get("period_effective_from") or context.get("period"),
        evidence=evidence,
        target={
            "cell_key": event.get("cell_key"),
            "band": event.get("band"),
            "level": event.get("level"),
            "scope": event.get("scope"),
            "action": action,
        },
    )


def _decision_event(
    ae_id: str,
    agreement_name: str,
    lga_short_name: Any,
    *,
    source: str,
    index: int,
    raw_event: dict[str, Any],
    decision_type: str,
    pattern: str,
    period: Any,
    evidence: list[str],
    target: dict[str, Any],
) -> dict[str, Any]:
    event_type = str(raw_event.get("event_type") or pattern)
    clean_target = {key: value for key, value in target.items() if value not in (None, "")}
    return {
        "decision_id": f"{ae_id}::{source}::{index}::{event_type}",
        "ae_id": ae_id,
        "agreement_name": agreement_name,
        "canonical_lga_short_name": lga_short_name,
        "source": source,
        "event_type": event_type,
        "decision_type": decision_type,
        "pattern": pattern,
        "changed_at": raw_event.get("changed_at"),
        "changed_by": raw_event.get("changed_by"),
        "period": period,
        "target": clean_target,
        "evidence": evidence,
    }


def _learned_patterns(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[str(event.get("pattern") or "unknown")].append(event)

    patterns: list[dict[str, Any]] = []
    for pattern, pattern_events in grouped.items():
        ae_ids = sorted({str(event.get("ae_id") or "") for event in pattern_events if event.get("ae_id")})
        decision_types = sorted({str(event.get("decision_type") or "") for event in pattern_events if event.get("decision_type")})
        event_counts = Counter(str(event.get("event_type") or "") for event in pattern_events)
        patterns.append({
            "pattern": pattern,
            "count": len(pattern_events),
            "agreement_count": len(ae_ids),
            "decision_types": decision_types,
            "event_types": [
                {"event_type": event_type, "count": count}
                for event_type, count in event_counts.most_common()
                if event_type
            ],
            "confidence": _pattern_confidence(len(pattern_events), len(ae_ids)),
            "examples": [
                {
                    "decision_id": event.get("decision_id"),
                    "ae_id": event.get("ae_id"),
                    "agreement_name": event.get("agreement_name"),
                    "period": event.get("period"),
                    "evidence": event.get("evidence") or [],
                }
                for event in pattern_events[:EXAMPLE_LIMIT]
            ],
        })
    patterns.sort(key=lambda item: (-int(item["count"]), str(item["pattern"])))
    return patterns


def _policy_suggestions(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_pattern = {str(item.get("pattern")): item for item in patterns}
    suggestions: list[dict[str, Any]] = []
    _maybe_add_suggestion(
        suggestions,
        by_pattern,
        "pay_table_effective_date_adjusted",
        "reinforce_effective_date_suggestion",
        "Run and explain suggested effective dates before pay-table save when dates move.",
        minimum=1,
    )
    _maybe_add_suggestion(
        suggestions,
        by_pattern,
        "scenario_cell_use_computed",
        "reinforce_computed_value_decision",
        "When repeated cell overrides use computed values, surface computed-vs-printed evidence before save.",
        minimum=1,
    )
    _maybe_add_suggestion(
        suggestions,
        by_pattern,
        "scenario_group_use_computed",
        "reinforce_group_computed_decision",
        "When group overrides use computed values, prefer a group-level save reason over per-cell chatter.",
        minimum=1,
    )
    _maybe_add_suggestion(
        suggestions,
        by_pattern,
        "pay_table_row_removed",
        "allow_pragmatic_row_drop_reason",
        "When rows are removed in review, require a short reason and preserve the event for future scope hints.",
        minimum=1,
    )
    _maybe_add_suggestion(
        suggestions,
        by_pattern,
        "pay_table_removed",
        "allow_pragmatic_table_drop_reason",
        "When tables are removed in review, treat table dropping as an intentional decision with a saved reason.",
        minimum=1,
    )
    _maybe_add_suggestion(
        suggestions,
        by_pattern,
        "uplift_rule_table_binding_conflict",
        "stop_at_uplift_rule_table_binding_conflict",
        "When accepted uplift rules conflict with a coherent published table pattern, stop at Uplift Rules and review extraction binding before scenario QA.",
        minimum=1,
    )
    return suggestions


def evaluate_rule_promotions(
    policy_suggestions: list[dict[str, Any]],
    *,
    regression_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return learned rules that may be added after a full passing regression.

    This is the self-improvement gate. Learning can observe continuously, but a
    rule is addable only when:
      - the learned suggestion is high/medium confidence,
      - it has concrete evidence,
      - the recorded regression result is the full suite and passed.
    """
    if not _full_regression_passed(regression_result):
        return []
    promotions: list[dict[str, Any]] = []
    for suggestion in policy_suggestions:
        confidence = str(suggestion.get("confidence") or "")
        evidence_count = int(suggestion.get("evidence_count") or 0)
        if confidence not in {"high", "medium"} or evidence_count <= 0:
            continue
        promotions.append({
            "rule": suggestion.get("rule"),
            "source_pattern": suggestion.get("source_pattern"),
            "evidence_count": evidence_count,
            "agreement_count": suggestion.get("agreement_count"),
            "promotion_status": "addable_after_full_regression",
            "regression": {
                "suite": regression_result.get("suite"),
                "passed": True,
                "test_count": regression_result.get("test_count"),
            },
            "message": suggestion.get("message"),
        })
    return promotions


def _full_regression_passed(regression_result: dict[str, Any] | None) -> bool:
    if not isinstance(regression_result, dict):
        return False
    suite = str(regression_result.get("suite") or "").strip().lower()
    return suite == FULL_REGRESSION_SUITE and regression_result.get("passed") is True


def _maybe_add_suggestion(
    suggestions: list[dict[str, Any]],
    patterns: dict[str, dict[str, Any]],
    pattern: str,
    rule: str,
    message: str,
    *,
    minimum: int,
) -> None:
    learned = patterns.get(pattern)
    if not learned or int(learned.get("count") or 0) < minimum:
        return
    suggestions.append({
        "rule": rule,
        "source_pattern": pattern,
        "evidence_count": learned.get("count"),
        "agreement_count": learned.get("agreement_count"),
        "confidence": learned.get("confidence"),
        "promotion_gate": {
            "required_suite": FULL_REGRESSION_SUITE,
            "requires_passed": True,
            "status": "waiting_for_full_regression",
        },
        "message": message,
    })


def _pattern_confidence(count: int, agreement_count: int) -> str:
    if count >= 5 and agreement_count >= 3:
        return "high"
    if count >= 2 or agreement_count >= 2:
        return "medium"
    return "low"


def _compact_evidence(values: list[str]) -> list[str]:
    return [value for value in values if value][:6]
