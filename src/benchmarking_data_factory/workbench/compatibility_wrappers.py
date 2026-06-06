from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from benchmarking_data_factory.workbench import analysis_workspace as analysis_workspace_module
from benchmarking_data_factory.workbench import audit_report as audit_report_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module


def bind_audit_wrappers(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def _audit_council_reference(council_name: str) -> dict[str, Any]:
        return ctx._with_audit_dependencies(audit_report_module._audit_council_reference, council_name)

    def _audit_candidate_council_names(row: dict[str, Any]) -> list[str]:
        return ctx._with_audit_dependencies(audit_report_module._audit_candidate_council_names, row)

    def _audit_candidate_matches_council(row: dict[str, Any], target_keys: set[str]) -> bool:
        return ctx._with_audit_dependencies(audit_report_module._audit_candidate_matches_council, row, target_keys)

    def _audit_lineage_row(
        candidate: dict[str, Any],
        *,
        intake_row: dict[str, Any] | None,
        register_entry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return ctx._with_audit_dependencies(
            audit_report_module._audit_lineage_row,
            candidate,
            intake_row=intake_row,
            register_entry=register_entry,
        )

    def _audit_workspace_matches_council(row: dict[str, Any], target_keys: set[str]) -> bool:
        return ctx._with_audit_dependencies(audit_report_module._audit_workspace_matches_council, row, target_keys)

    def _audit_workspace_ae_ids(target_keys: set[str], lineage_ids: set[str]) -> list[str]:
        return ctx._with_audit_dependencies(audit_report_module._audit_workspace_ae_ids, target_keys, lineage_ids)

    def _audit_workspace_snapshot(ae_id: str, summary_row: dict[str, Any] | None = None) -> dict[str, Any]:
        return ctx._with_audit_dependencies(audit_report_module._audit_workspace_snapshot, ae_id, summary_row)

    def _audit_row_level_treatment(sections: dict[str, Any]) -> dict[str, Any]:
        return ctx._with_audit_dependencies(audit_report_module._audit_row_level_treatment, sections)

    def _audit_governed_events(ae_id: str, workspace: dict[str, Any]) -> list[dict[str, Any]]:
        return ctx._with_audit_dependencies(audit_report_module._audit_governed_events, ae_id, workspace)

    def build_council_audit_report(council_name: str) -> dict[str, Any]:
        return audit_report_module.build_council_audit_report(council_name, ctx._audit_dependencies())

    namespace.update({
        "_audit_council_reference": _audit_council_reference,
        "_audit_candidate_council_names": _audit_candidate_council_names,
        "_audit_candidate_matches_council": _audit_candidate_matches_council,
        "_audit_lineage_row": _audit_lineage_row,
        "_audit_workspace_matches_council": _audit_workspace_matches_council,
        "_audit_workspace_ae_ids": _audit_workspace_ae_ids,
        "_audit_workspace_snapshot": _audit_workspace_snapshot,
        "_audit_row_level_treatment": _audit_row_level_treatment,
        "_audit_governed_events": _audit_governed_events,
        "build_council_audit_report": build_council_audit_report,
    })


def bind_analysis_wrappers(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def analysis_visible_ae_ids(include_split_parents: bool = False) -> list[str]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.analysis_visible_ae_ids,
            include_split_parents=include_split_parents,
        )

    def _rate_cap_resolution_for_rule(
        rule: dict[str, Any],
        *,
        lga_short_name: str | None = None,
        effective_from: str | None = None,
    ) -> dict[str, Any] | None:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module._rate_cap_resolution_for_rule,
            rule,
            lga_short_name=lga_short_name,
            effective_from=effective_from,
        )

    def _normalised_governed_rule_for_response(
        rule: dict[str, Any],
        *,
        lga_short_name: str | None = None,
        effective_from: str | None = None,
    ) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module._normalised_governed_rule_for_response,
            rule,
            lga_short_name=lga_short_name,
            effective_from=effective_from,
        )

    def normalised_governed_payload_for_response(
        governed: dict[str, Any] | None,
        *,
        lga_short_name: str | None = None,
    ) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.normalised_governed_payload_for_response,
            governed,
            lga_short_name=lga_short_name,
        )

    def _governed_data_for_rebuild(canonical: dict[str, Any]) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(analysis_workspace_module._governed_data_for_rebuild, canonical)

    def _clear_governed_entity_slots(canonical: dict[str, Any], data_set: str) -> dict[str, int]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module._clear_governed_entity_slots,
            canonical,
            data_set,
        )

    def _upstream_pay_table_dates(canonical: dict[str, Any]) -> list[str]:
        return ctx._with_analysis_dependencies(analysis_workspace_module._upstream_pay_table_dates, canonical)

    def _upstream_uplift_rule_dates(canonical: dict[str, Any], rules: list[dict[str, Any]]) -> list[str]:
        return ctx._with_analysis_dependencies(analysis_workspace_module._upstream_uplift_rule_dates, canonical, rules)

    def rebuild_analysis_data_set(data_set: str, *, include_split_parents: bool = False) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.rebuild_analysis_data_set,
            data_set,
            include_split_parents=include_split_parents,
        )

    def build_uplift_rules_analysis(include_split_parents: bool = False) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.build_uplift_rules_analysis,
            include_split_parents=include_split_parents,
        )

    def build_pay_tables_analysis(include_split_parents: bool = False) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.build_pay_tables_analysis,
            include_split_parents=include_split_parents,
        )

    def build_end_of_band_dollars_analysis(include_split_parents: bool = False) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.build_end_of_band_dollars_analysis,
            include_split_parents=include_split_parents,
        )

    def _analysis_iso_date(value: Any) -> str | None:
        return ctx._with_analysis_dependencies(analysis_workspace_module._analysis_iso_date, value)

    def _quarter_start_iso(value: Any) -> str | None:
        return ctx._with_analysis_dependencies(analysis_workspace_module._quarter_start_iso, value)

    def _distribution_quarters_for_row(row: dict[str, Any]) -> list[str]:
        return ctx._with_analysis_dependencies(analysis_workspace_module._distribution_quarters_for_row, row)

    def build_distribution_point_analysis(
        include_split_parents: bool = False,
        pay_tables_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.build_distribution_point_analysis,
            include_split_parents=include_split_parents,
            pay_tables_analysis=pay_tables_analysis,
        )

    def materialize_distribution_point_analysis(
        include_split_parents: bool = False,
        pay_tables_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return ctx._with_analysis_dependencies(
            analysis_workspace_module.materialize_distribution_point_analysis,
            include_split_parents=include_split_parents,
            pay_tables_analysis=pay_tables_analysis,
        )

    def load_distribution_point_analysis_asset() -> dict[str, Any] | None:
        return ctx._with_analysis_dependencies(analysis_workspace_module.load_distribution_point_analysis_asset)

    namespace.update({
        "analysis_visible_ae_ids": analysis_visible_ae_ids,
        "_rate_cap_resolution_for_rule": _rate_cap_resolution_for_rule,
        "_normalised_governed_rule_for_response": _normalised_governed_rule_for_response,
        "normalised_governed_payload_for_response": normalised_governed_payload_for_response,
        "_governed_data_for_rebuild": _governed_data_for_rebuild,
        "_clear_governed_entity_slots": _clear_governed_entity_slots,
        "_upstream_pay_table_dates": _upstream_pay_table_dates,
        "_upstream_uplift_rule_dates": _upstream_uplift_rule_dates,
        "rebuild_analysis_data_set": rebuild_analysis_data_set,
        "build_uplift_rules_analysis": build_uplift_rules_analysis,
        "build_pay_tables_analysis": build_pay_tables_analysis,
        "build_end_of_band_dollars_analysis": build_end_of_band_dollars_analysis,
        "_analysis_iso_date": _analysis_iso_date,
        "_quarter_start_iso": _quarter_start_iso,
        "_distribution_quarters_for_row": _distribution_quarters_for_row,
        "build_distribution_point_analysis": build_distribution_point_analysis,
        "materialize_distribution_point_analysis": materialize_distribution_point_analysis,
        "load_distribution_point_analysis_asset": load_distribution_point_analysis_asset,
    })


def bind_scenario_wrappers(namespace: MutableMapping[str, Any], ctx: Any) -> None:
    def _scenario_override_path(ae_id: str):
        return ctx._with_scenario_governance_dependencies(scenario_governance_module._scenario_override_path, ae_id)

    def _read_scenario_override_state(ae_id: str) -> dict[str, Any]:
        return ctx._with_scenario_governance_dependencies(
            scenario_governance_module._read_scenario_override_state,
            ae_id,
        )

    def _scenario_cell_overrides_for_period(ae_id: str, effective_from: str) -> dict[str, Any] | None:
        return ctx._with_scenario_governance_dependencies(
            scenario_governance_module._scenario_cell_overrides_for_period,
            ae_id,
            effective_from,
        )

    def _write_scenario_override_state(
        ae_id: str,
        overrides: dict[str, Any],
        notes: Any,
        saved_at: str | None,
        audit_events: Any = None,
    ) -> dict[str, Any]:
        return ctx._with_scenario_governance_dependencies(
            scenario_governance_module._write_scenario_override_state,
            ae_id,
            overrides,
            notes,
            saved_at,
            audit_events,
        )

    namespace.update({
        "_scenario_override_path": _scenario_override_path,
        "_read_scenario_override_state": _read_scenario_override_state,
        "_scenario_cell_overrides_for_period": _scenario_cell_overrides_for_period,
        "_write_scenario_override_state": _write_scenario_override_state,
    })
