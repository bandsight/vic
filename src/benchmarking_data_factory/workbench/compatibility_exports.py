from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from benchmarking_data_factory.workbench import analysis_workspace as analysis_workspace_module
from benchmarking_data_factory.workbench import audit_report as audit_report_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module


AUDIT_EXPORTS = (
    "_COUNCIL_AUDIT_RENAME_ALIASES",
    "_audit_key",
    "_audit_compact_key",
    "_audit_target_keys",
    "_audit_matches_any_name",
    "_audit_date_score",
    "_audit_int",
    "_audit_latest_lineage_key",
    "_audit_chronological_lineage_key",
    "_audit_event_sort_key",
    "_audit_source_size",
    "_audit_qa_label",
    "_audit_qa_value",
    "_audit_qa_detail",
    "_audit_qa_fields",
    "_audit_qa_events",
    "_audit_count_phrase",
    "_audit_excerpt",
    "_audit_unique_values",
    "_audit_human_list",
    "_audit_period_for_event",
    "_audit_event_note",
    "_audit_scenario_action",
    "_audit_action_label",
    "_audit_raw_qa_records",
    "_audit_pay_table_qa_brief",
    "_audit_scenario_qa_brief",
    "_audit_row_treatment_brief",
    "_audit_governed_brief",
    "_audit_qa_brief",
    "_audit_lineage_changes",
)

ANALYSIS_EXPORTS = (
    "_ANALYSIS_PCT_RE",
    "_ANALYSIS_RATE_CAP_TAIL_RE",
    "_ANALYSIS_DELTA_TAIL_RE",
    "_ANALYSIS_RATE_CAP_HEAD_RE",
    "_ANALYSIS_INVERTED_DELTA_RE",
    "_analysis_number",
    "_analysis_rule_has_rate_cap",
    "_analysis_pct_tokens",
    "_analysis_normalise_uplift_rule",
    "_analysis_sort_piece",
    "_shift_quarter_start_iso",
    "_distribution_band",
    "_distribution_level",
    "_distribution_level_sort_key",
    "_source_pages_from_rows",
    "_distribution_source_basis",
    "_distribution_source_rows",
)

SCENARIO_EXPORTS = (
    "QA_EVENT_LIMIT",
    "QA_RATE_FIELDS",
    "QA_TABLE_DATE_FIELDS",
    "_qa_json_equivalent",
    "_qa_numeric_equivalent",
    "_short_qa_excerpt",
    "_make_qa_event",
    "_append_qa_events",
    "_normalise_scenario_override_payload",
    "_scenario_cell_parts",
    "_scenario_override_events",
    "_scenario_note_events",
    "_pay_table_label",
    "_pay_row_key",
    "_pay_row_maps",
    "_pay_table_qa_events",
    "_apply_needs_review",
    "_scenario_compact_result",
    "_is_future_iso_date",
    "_future_trigger_date",
    "_scenario_future_trigger",
    "_scenario_section_resolution",
)


def _bind_exports(namespace: MutableMapping[str, Any], module: Any, names: tuple[str, ...]) -> None:
    for name in names:
        namespace[name] = getattr(module, name)


def bind_audit_exports(namespace: MutableMapping[str, Any]) -> None:
    _bind_exports(namespace, audit_report_module, AUDIT_EXPORTS)


def bind_analysis_exports(namespace: MutableMapping[str, Any]) -> None:
    _bind_exports(namespace, analysis_workspace_module, ANALYSIS_EXPORTS)


def bind_scenario_exports(namespace: MutableMapping[str, Any]) -> None:
    _bind_exports(namespace, scenario_governance_module, SCENARIO_EXPORTS)
