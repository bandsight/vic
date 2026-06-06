from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from benchmarking_data_factory.workbench.audit_governed_evidence import (
    audit_governed_events as _audit_governed_events_impl,
    audit_row_level_treatment as _audit_row_level_treatment_impl,
)
from benchmarking_data_factory.workbench.audit_identity import (
    _COUNCIL_AUDIT_RENAME_ALIASES,
    _audit_compact_key,
    _audit_key,
    _audit_matches_any_name,
    _audit_target_keys,
    audit_candidate_council_names as _audit_candidate_council_names_impl,
    audit_candidate_matches_council as _audit_candidate_matches_council_impl,
    audit_council_reference as _audit_council_reference_impl,
)
from benchmarking_data_factory.workbench.audit_lineage import (
    _audit_int,
    _audit_source_size,
    audit_chronological_lineage_key as _audit_chronological_lineage_key_impl,
    audit_event_sort_key as _audit_event_sort_key_impl,
    audit_latest_lineage_key as _audit_latest_lineage_key_impl,
    audit_lineage_row as _audit_lineage_row_impl,
)
from benchmarking_data_factory.workbench.audit_qa_summary import (
    _audit_action_label,
    _audit_count_phrase,
    _audit_event_note,
    _audit_excerpt,
    _audit_governed_brief,
    _audit_human_list,
    _audit_pay_table_qa_brief,
    _audit_period_for_event,
    _audit_qa_brief,
    _audit_qa_detail,
    _audit_qa_fields,
    _audit_qa_label,
    _audit_qa_value,
    _audit_raw_qa_records,
    _audit_row_treatment_brief,
    _audit_scenario_action,
    _audit_scenario_qa_brief,
    _audit_unique_values,
    audit_qa_events as _audit_qa_events_impl,
)
from benchmarking_data_factory.workbench.audit_quality import (
    audit_quality_inputs as _audit_quality_inputs_impl,
    build_quality_standard as _build_quality_standard_impl,
)
from benchmarking_data_factory.workbench.review_sections import (
    REVIEW_SECTIONS,
    SECTION_LABELS,
    done_count as review_done_count,
    section_statuses,
)


@dataclass(frozen=True)
class AuditReportDependencies:
    load_canonical_councils: Callable[[], list[dict[str, Any]]]
    candidate_lgas: Callable[[dict[str, Any]], list[str]]
    candidate_date_ordinal: Callable[[Any], float]
    pdf_source_metadata: Callable[[str], dict[str, Any]]
    load_registry: Callable[[], dict[str, str]]
    load_multi_council_decisions: Callable[[], dict[str, dict[str, Any]]]
    split_ae_ids_from_decisions: Callable[[dict[str, dict[str, Any]]], set[str]]
    list_pdfs: Callable[[], list[str]]
    fetch_metadata_for_ae_id: Callable[..., dict[str, Any]]
    resolve_canonical_lga_short_name: Callable[..., str | None]
    get_canonical: Callable[[str], dict[str, Any]]
    read_scenario_override_state: Callable[[str], dict[str, Any]]
    is_standard_band_level_row: Callable[[dict[str, Any]], bool]
    load_candidate_agreement_rows: Callable[[], list[dict[str, Any]]]
    build_intake_candidate_rows: Callable[[], list[dict[str, Any]]]
    load_source_register_by_ae_id: Callable[[], dict[str, dict[str, Any]]]
    build_council_summary: Callable[..., dict[str, Any]]
    now_iso: Callable[[], str]
    geography_for_lga: Callable[[Any], dict[str, Any] | None]
    workspace_ae_ids: Callable[[set[str], set[str]], list[str]]
    workspace_matches_council: Callable[[dict[str, Any], set[str]], bool]
    workspace_snapshot: Callable[..., dict[str, Any]]
    governed_events: Callable[[str, dict[str, Any]], list[dict[str, Any]]]


_ACTIVE_DEPS: ContextVar[AuditReportDependencies | None] = ContextVar(
    "audit_report_dependencies",
    default=None,
)


@contextmanager
def audit_report_dependencies(deps: AuditReportDependencies) -> Iterator[None]:
    token = _ACTIVE_DEPS.set(deps)
    try:
        yield
    finally:
        _ACTIVE_DEPS.reset(token)


def _deps() -> AuditReportDependencies:
    deps = _ACTIVE_DEPS.get()
    if deps is None:
        raise RuntimeError("Audit report dependencies are not configured")
    return deps


def load_canonical_councils() -> list[dict[str, Any]]:
    return _deps().load_canonical_councils()


def _candidate_lgas(row: dict[str, Any]) -> list[str]:
    return _deps().candidate_lgas(row)


def candidate_date_ordinal(value: Any) -> float:
    return _deps().candidate_date_ordinal(value)


def pdf_source_metadata(ae_id: str) -> dict[str, Any]:
    return _deps().pdf_source_metadata(ae_id)


def load_registry() -> dict[str, str]:
    return _deps().load_registry()


def load_multi_council_decisions() -> dict[str, dict[str, Any]]:
    return _deps().load_multi_council_decisions()


def split_ae_ids_from_decisions(decisions: dict[str, dict[str, Any]]) -> set[str]:
    return _deps().split_ae_ids_from_decisions(decisions)


def list_pdfs() -> list[str]:
    return _deps().list_pdfs()


def fetch_metadata_for_ae_id(ae_id: str, decisions: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    return _deps().fetch_metadata_for_ae_id(ae_id, decisions)


def resolve_canonical_lga_short_name(
    ae_id: str,
    fetch_metadata: dict[str, Any] | None,
    decisions: dict[str, dict[str, Any]] | None,
) -> str | None:
    return _deps().resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)


def get_canonical(ae_id: str) -> dict[str, Any]:
    return _deps().get_canonical(ae_id)


def _read_scenario_override_state(ae_id: str) -> dict[str, Any]:
    return _deps().read_scenario_override_state(ae_id)


def is_standard_band_level_row(row: dict[str, Any]) -> bool:
    return _deps().is_standard_band_level_row(row)


def load_candidate_agreement_rows() -> list[dict[str, Any]]:
    return _deps().load_candidate_agreement_rows()


def build_intake_candidate_rows() -> list[dict[str, Any]]:
    return _deps().build_intake_candidate_rows()


def load_source_register_by_ae_id() -> dict[str, dict[str, Any]]:
    return _deps().load_source_register_by_ae_id()


def build_council_summary(
    ae_id: str,
    registry: dict[str, str] | None = None,
    decisions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _deps().build_council_summary(ae_id, registry, decisions)


def now_iso() -> str:
    return _deps().now_iso()


def geography_for_lga(value: Any) -> dict[str, Any] | None:
    return _deps().geography_for_lga(value)


def build_council_audit_report(council_name: str, deps: AuditReportDependencies) -> dict[str, Any]:
    with audit_report_dependencies(deps):
        return _build_council_audit_report(council_name, deps)


def _audit_council_reference(council_name: str) -> dict[str, Any]:
    return _audit_council_reference_impl(council_name, load_canonical_councils=load_canonical_councils)


def _audit_candidate_council_names(row: dict[str, Any]) -> list[str]:
    return _audit_candidate_council_names_impl(row, candidate_lgas=_candidate_lgas)


def _audit_candidate_matches_council(row: dict[str, Any], target_keys: set[str]) -> bool:
    return _audit_candidate_matches_council_impl(row, target_keys, candidate_lgas=_candidate_lgas)


def _audit_date_score(value: Any) -> float:
    return candidate_date_ordinal(value)


def _audit_latest_lineage_key(row: dict[str, Any]) -> tuple[int, int, float, int, int]:
    return _audit_latest_lineage_key_impl(row, date_score=_audit_date_score)


def _audit_chronological_lineage_key(row: dict[str, Any]) -> tuple[float, int, str]:
    return _audit_chronological_lineage_key_impl(row, date_score=_audit_date_score)


def _audit_event_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    return _audit_event_sort_key_impl(row, date_score=_audit_date_score)


def _audit_lineage_row(
    candidate: dict[str, Any],
    *,
    intake_row: dict[str, Any] | None,
    register_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    return _audit_lineage_row_impl(
        candidate,
        intake_row=intake_row,
        register_entry=register_entry,
        pdf_source_metadata=pdf_source_metadata,
        candidate_council_names=_audit_candidate_council_names,
    )


def _audit_workspace_matches_council(row: dict[str, Any], target_keys: set[str]) -> bool:
    fetch_metadata = row.get("fetch_metadata") or {}
    names = [
        row.get("canonical_lga_short_name"),
        (row.get("geography") or {}).get("short_name"),
        fetch_metadata.get("lga_short_name"),
        fetch_metadata.get("lga_original_name"),
    ]
    names.extend(_audit_candidate_council_names(fetch_metadata))
    return _audit_matches_any_name(names, target_keys)


def _audit_workspace_ae_ids(target_keys: set[str], lineage_ids: set[str]) -> list[str]:
    registry = load_registry()
    decisions = load_multi_council_decisions()
    split_ae_ids = split_ae_ids_from_decisions(decisions)
    ae_ids = sorted(set(registry.keys()) | set(list_pdfs()) | split_ae_ids | lineage_ids)
    matched: set[str] = set()
    for ae_id in ae_ids:
        fetch_metadata = fetch_metadata_for_ae_id(ae_id, decisions)
        if fetch_metadata and _audit_candidate_matches_council(fetch_metadata, target_keys):
            matched.add(ae_id)
            continue
        resolved = resolve_canonical_lga_short_name(ae_id, fetch_metadata, decisions)
        if _audit_matches_any_name([resolved], target_keys):
            matched.add(ae_id)
    return sorted(matched)


def _audit_workspace_snapshot(ae_id: str, summary_row: dict[str, Any] | None = None) -> dict[str, Any]:
    canonical = get_canonical(ae_id)
    sections = canonical.get("sections") or {}
    statuses = section_statuses(sections)
    completed_sections = []
    governed_set_status = "not_started"
    governed_set_completed_at = None
    for section, label in SECTION_LABELS.items():
        data = sections.get(section) if isinstance(sections, dict) else {}
        if not isinstance(data, dict):
            continue
        if section == "uplifts":
            governed_set_status = str(data.get("status") or "not_started")
            governed_set_completed_at = data.get("completed_at")
        completed_sections.append({
            "section": section,
            "label": label,
            "status": data.get("status") or "not_started",
            "completed_at": data.get("completed_at"),
            "source_ref": data.get("source_ref") or "",
        })

    periods = (((sections.get("uplifts") or {}).get("data") or {}).get("periods") or [])
    governed_periods = [period for period in periods if isinstance(period, dict)]
    pay_periods = [period for period in governed_periods if isinstance(period.get("pay_table"), dict)]
    rule_periods = [period for period in governed_periods if isinstance(period.get("uplift_rule"), dict)]
    pay_rows = sum(
        len(period.get("pay_table", {}).get("rows") or [])
        for period in pay_periods
        if isinstance(period.get("pay_table"), dict)
    )
    scenario_state = _read_scenario_override_state(ae_id)
    pay_qa_events = [
        event for event in (((sections.get("pay_tables") or {}).get("qa_events") or []))
        if isinstance(event, dict)
    ]
    scenario_qa_events = [event for event in (scenario_state.get("audit_events") or []) if isinstance(event, dict)]
    row_level_treatment = _audit_row_level_treatment(sections)
    return {
        "ae_id": ae_id,
        "source_name": canonical.get("source_name") or (summary_row or {}).get("source_name") or ae_id,
        "canonical_lga_short_name": (summary_row or {}).get("canonical_lga_short_name"),
        "done_count": (summary_row or {}).get("done_count") or review_done_count(statuses),
        "total_sections": (summary_row or {}).get("total_sections") or len(REVIEW_SECTIONS),
        "section_statuses": statuses,
        "completed_sections": completed_sections,
        "governed": {
            "periods": len(governed_periods),
            "pay_table_periods": len(pay_periods),
            "uplift_rule_periods": len(rule_periods),
            "pay_table_rows": pay_rows,
            "pay_table_governed_at": sorted({str(p.get("pay_table_governed_at")) for p in pay_periods if p.get("pay_table_governed_at")}),
            "uplift_rule_governed_at": sorted({str(p.get("uplift_rule_governed_at")) for p in rule_periods if p.get("uplift_rule_governed_at")}),
            "governed_set_status": governed_set_status,
            "governed_set_completed_at": governed_set_completed_at,
        },
        "scenario_saved_at": scenario_state.get("saved_at"),
        "scenario_notes": scenario_state.get("notes"),
        "scenario_overrides": scenario_state.get("overrides") or {},
        "row_level_treatment": row_level_treatment,
        "qa_events": {
            "pay_tables": pay_qa_events,
            "scenarios": scenario_qa_events,
            "total": len(pay_qa_events) + len(scenario_qa_events),
        },
        "clear_records": [
            record
            for record in (canonical.get("review_clear_records") or [])
            if isinstance(record, dict)
        ],
        "pay_table_summary": (summary_row or {}).get("pay_table_summary") or [],
        "quality_inputs": _audit_quality_inputs_impl(canonical),
    }


def _audit_governed_snapshot(workspaces: list[dict[str, Any]]) -> dict[str, Any]:
    governed_items = [
        workspace.get("governed") or {}
        for workspace in workspaces
        if isinstance(workspace, dict)
    ]
    pay_table_governed_at: set[str] = set()
    uplift_rule_governed_at: set[str] = set()
    governed_set_completed_at: set[str] = set()
    statuses: list[str] = []
    agreement_count = 0
    periods = 0
    pay_table_periods = 0
    uplift_rule_periods = 0
    pay_table_rows = 0
    for governed in governed_items:
        item_periods = int(governed.get("periods") or 0)
        item_pay_periods = int(governed.get("pay_table_periods") or 0)
        item_rule_periods = int(governed.get("uplift_rule_periods") or 0)
        item_pay_rows = int(governed.get("pay_table_rows") or 0)
        if item_periods or item_pay_periods or item_rule_periods or item_pay_rows:
            agreement_count += 1
        periods += item_periods
        pay_table_periods += item_pay_periods
        uplift_rule_periods += item_rule_periods
        pay_table_rows += item_pay_rows
        pay_table_governed_at.update(str(value) for value in governed.get("pay_table_governed_at") or [] if value)
        uplift_rule_governed_at.update(str(value) for value in governed.get("uplift_rule_governed_at") or [] if value)
        completed_at = governed.get("governed_set_completed_at")
        if completed_at:
            governed_set_completed_at.add(str(completed_at))
        status = str(governed.get("governed_set_status") or "").strip()
        if status:
            statuses.append(status)

    latest_completed_at = max(
        governed_set_completed_at,
        key=lambda value: (_audit_date_score(value), value),
        default=None,
    )
    if statuses and all(status == "done" for status in statuses):
        governed_set_status = "done"
    elif any(status in {"flagged", "in_progress", "done"} for status in statuses):
        governed_set_status = "in_progress"
    else:
        governed_set_status = "not_started"

    return {
        "periods": periods,
        "pay_table_periods": pay_table_periods,
        "uplift_rule_periods": uplift_rule_periods,
        "pay_table_rows": pay_table_rows,
        "pay_table_governed_at": sorted(pay_table_governed_at, key=lambda value: (_audit_date_score(value), value)),
        "uplift_rule_governed_at": sorted(uplift_rule_governed_at, key=lambda value: (_audit_date_score(value), value)),
        "governed_set_status": governed_set_status,
        "governed_set_completed_at": latest_completed_at,
        "agreement_count": agreement_count,
    }


def _audit_row_level_treatment(sections: dict[str, Any]) -> dict[str, Any]:
    return _audit_row_level_treatment_impl(
        sections,
        is_standard_band_level_row=is_standard_band_level_row,
    )


def _audit_governed_events(ae_id: str, workspace: dict[str, Any]) -> list[dict[str, Any]]:
    return _audit_governed_events_impl(ae_id, workspace, get_canonical=get_canonical)


def _audit_qa_events(ae_id: str, workspace: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _audit_qa_events_impl(ae_id, workspace, sort_key=_audit_event_sort_key)


def _audit_lineage_changes(lineage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(lineage, key=_audit_chronological_lineage_key)
    changes: list[dict[str, Any]] = []
    for previous, current in zip(ordered, ordered[1:]):
        changed_fields: list[dict[str, str]] = []
        if (previous.get("title") or "") != (current.get("title") or ""):
            changed_fields.append({
                "field": "Agreement title",
                "from": str(previous.get("title") or ""),
                "to": str(current.get("title") or ""),
            })
        previous_period = f"{previous.get('operative_date') or 'not stated'} to {previous.get('expiry_date') or 'not stated'}"
        current_period = f"{current.get('operative_date') or 'not stated'} to {current.get('expiry_date') or 'not stated'}"
        if previous_period != current_period:
            changed_fields.append({
                "field": "Operative period",
                "from": previous_period,
                "to": current_period,
            })
        if (previous.get("matter_number") or "") != (current.get("matter_number") or ""):
            changed_fields.append({
                "field": "Matter number",
                "from": str(previous.get("matter_number") or "Not stated"),
                "to": str(current.get("matter_number") or "Not stated"),
            })
        superseded = previous.get("superseded_by_ae_id") == current.get("ae_id")
        summary_parts = [
            f"{current.get('ae_id', '').upper()} became the newer agreement record",
        ]
        if superseded:
            summary_parts.append(f"and superseded {previous.get('ae_id', '').upper()}")
        if current.get("operative_date"):
            summary_parts.append(f"from {current.get('operative_date')}")
        changes.append({
            "date": current.get("operative_date") or current.get("source_fetched_at") or "",
            "kind": "lineage",
            "from_ae_id": previous.get("ae_id"),
            "to_ae_id": current.get("ae_id"),
            "summary": " ".join(summary_parts),
            "fields": changed_fields,
        })
    return changes


def _build_council_audit_report(council_name: str, deps: AuditReportDependencies) -> dict[str, Any]:
    target_keys = _audit_target_keys(council_name)
    if not target_keys:
        raise HTTPException(status_code=400, detail="Council name is required")

    reference = _audit_council_reference(council_name)
    target_keys.update(_audit_target_keys(reference.get("short_name")))
    candidates = [row for row in load_candidate_agreement_rows() if _audit_candidate_matches_council(row, target_keys)]
    intake_rows = build_intake_candidate_rows()
    intake_rows_by_id = {row.get("ae_id"): row for row in intake_rows}
    register_by_ae_id = load_source_register_by_ae_id()
    lineage = [
        _audit_lineage_row(
            row,
            intake_row=intake_rows_by_id.get(str(row.get("Agreement ID") or "").strip().lower()),
            register_entry=register_by_ae_id.get(str(row.get("Agreement ID") or "").strip().lower()),
        )
        for row in candidates
    ]

    registry = load_registry()
    decisions = load_multi_council_decisions()
    workspace_rows = [
        build_council_summary(ae_id, registry, decisions)
        for ae_id in deps.workspace_ae_ids(
            target_keys,
            {str(row.get("ae_id") or "").lower() for row in lineage if row.get("ae_id")},
        )
    ]
    workspace_rows = [row for row in workspace_rows if deps.workspace_matches_council(row, target_keys)]
    lineage_by_id = {row.get("ae_id"): row for row in lineage if row.get("ae_id")}
    for workspace_row in workspace_rows:
        ae_id = str(workspace_row.get("ae_id") or "").lower()
        if not ae_id or ae_id in lineage_by_id:
            continue
        fetch_metadata = workspace_row.get("fetch_metadata") or {}
        if fetch_metadata.get("Agreement ID"):
            lineage_row = _audit_lineage_row(
                fetch_metadata,
                intake_row=intake_rows_by_id.get(ae_id),
                register_entry=register_by_ae_id.get(ae_id),
            )
        else:
            register_entry = register_by_ae_id.get(ae_id)
            lineage_row = {
                "ae_id": ae_id,
                "title": workspace_row.get("source_name") or ae_id,
                "operative_date": "",
                "expiry_date": "",
                "published_year": "",
                "matter_number": "",
                "print_id": "",
                "version": "",
                "agreement_number": "",
                "pipeline_status": "working_set",
                "likely_most_current": "",
                "superseded_by_ae_id": "",
                "matched_lgas": [workspace_row.get("canonical_lga_short_name")],
                "scope_resolution_status": "",
                "match_strength": "",
                "lineage_key": "",
                "lineage_basis": "",
                "source_ready": bool(register_entry or workspace_row.get("pdf_frozen")),
                "source_fetched_at": (register_entry or {}).get("fetched_at") or workspace_row.get("landed_at") or "",
                "source_status": (register_entry or {}).get("source_status") or "",
                "serviceability_status": (register_entry or {}).get("serviceability_status") or "",
                "source_size_bytes": _audit_source_size(register_entry),
                "source_origin": (register_entry or {}).get("source_origin") or "",
                "content_hash": (register_entry or {}).get("content_hash") or "",
                "intake_state": "",
                "intake_decided_at": "",
                "intake_decision_reason": "",
            }
        lineage_by_id[ae_id] = lineage_row
        lineage.append(lineage_row)

    if not lineage and not workspace_rows:
        available = sorted({
            name
            for row in load_candidate_agreement_rows()
            for name in _audit_candidate_council_names(row)
            if name
        })
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"No agreement lineage found for {council_name}",
                "reason": "No candidate, source register or workspace row matched that council.",
                "available": available[:25],
            },
        )

    lineage = sorted(lineage, key=_audit_chronological_lineage_key)
    latest = max(lineage, key=_audit_latest_lineage_key) if lineage else None
    workspace_by_id = {
        row.get("ae_id"): deps.workspace_snapshot(str(row.get("ae_id")), row)
        for row in workspace_rows
        if row.get("ae_id")
    }
    latest_workspace = workspace_by_id.get(latest.get("ae_id")) if latest else None

    events: list[dict[str, Any]] = []
    qa_changes: list[dict[str, Any]] = []
    for row in lineage:
        if row.get("operative_date"):
            events.append({
                "date": row.get("operative_date"),
                "kind": "lineage",
                "label": "Agreement operative",
                "detail": f"{row.get('ae_id', '').upper()} - {row.get('title') or 'Agreement'}",
                "ae_id": row.get("ae_id"),
                "source": "Fair Work candidate register",
            })
        if row.get("source_fetched_at"):
            events.append({
                "date": row.get("source_fetched_at"),
                "kind": "source",
                "label": "Source PDF fetched",
                "detail": f"{row.get('source_status') or 'Source'} / {row.get('serviceability_status') or 'recorded'}",
                "ae_id": row.get("ae_id"),
                "source": "Source document register",
            })
        if row.get("intake_decided_at"):
            events.append({
                "date": row.get("intake_decided_at"),
                "kind": "intake",
                "label": "Intake decision recorded",
                "detail": f"{row.get('intake_state') or 'decision'} - {row.get('intake_decision_reason') or 'No reason supplied'}",
                "ae_id": row.get("ae_id"),
                "source": "Intake decisions",
            })

    for ae_id, workspace in workspace_by_id.items():
        for record in workspace.get("clear_records") or []:
            if record.get("cleared_at"):
                events.append({
                    "date": record.get("cleared_at"),
                    "kind": "governance",
                    "label": "Review record cleared",
                    "detail": (
                        f"{record.get('moved_artifact_count') or 0} artifact(s) archived"
                        f" to {record.get('archive_id') or 'clear record'}"
                    ),
                    "ae_id": ae_id,
                    "source": "Clear record",
                })
        for section in workspace.get("completed_sections") or []:
            if section.get("completed_at"):
                events.append({
                    "date": section.get("completed_at"),
                    "kind": "review",
                    "label": f"{section.get('label')} completed",
                    "detail": section.get("source_ref") or "Workspace section marked done",
                    "ae_id": ae_id,
                    "source": "Agreement workspace",
                })
        events.extend(deps.governed_events(str(ae_id), workspace))
        qa_timeline, workspace_qa_changes = _audit_qa_events(str(ae_id), workspace)
        events.extend(qa_timeline)
        qa_changes.extend(workspace_qa_changes)

    events = sorted(events, key=_audit_event_sort_key)
    qa_changes = sorted(qa_changes, key=_audit_event_sort_key)
    changes = _audit_lineage_changes(lineage)
    governed = _audit_governed_snapshot(list(workspace_by_id.values()))
    row_level_treatment = (latest_workspace or {}).get("row_level_treatment") or _audit_row_level_treatment({})
    qa_brief = _audit_qa_brief(workspace_by_id, row_level_treatment, governed)
    quality_standard = _build_quality_standard_impl(lineage, workspace_by_id)
    return {
        "generated_at": now_iso(),
        "council": {
            **reference,
            "requested_name": council_name,
            "audit_key": _audit_key(reference.get("short_name") or council_name),
            "geography": geography_for_lga(reference.get("short_name") or council_name),
        },
        "latest": latest,
        "latest_workspace": latest_workspace,
        "governed": governed,
        "row_level_treatment": row_level_treatment,
        "qa_brief": qa_brief,
        "quality_standard": quality_standard,
        "summary": {
            "lineage_agreements": len(lineage),
            "source_pdfs": len([row for row in lineage if row.get("source_ready")]),
            "workspace_agreements": len(workspace_rows),
            "review_done_sections": (latest_workspace or {}).get("done_count") or 0,
            "review_total_sections": (latest_workspace or {}).get("total_sections") or len(REVIEW_SECTIONS),
            "governed_periods": governed.get("periods") or 0,
            "pay_table_periods": governed.get("pay_table_periods") or 0,
            "uplift_rule_periods": governed.get("uplift_rule_periods") or 0,
            "pay_table_rows": governed.get("pay_table_rows") or 0,
            "qa_governance_events": len(qa_changes),
            "qa_brief_items": len(qa_brief),
            "has_non_standard_row_level_treatment": bool(row_level_treatment.get("has_non_standard_row_level_treatment")),
            "non_standard_row_level_count": row_level_treatment.get("non_standard_row_count") or 0,
            "quality_standard_score": quality_standard.get("score") or 0,
            "quality_standard_max_score": quality_standard.get("max_score") or 1000,
            "quality_standard_rating": quality_standard.get("rating") or "Incomplete",
        },
        "lineage": lineage,
        "workspace": list(workspace_by_id.values()),
        "events": events,
        "qa_changes": qa_changes,
        "changes": changes,
    }
