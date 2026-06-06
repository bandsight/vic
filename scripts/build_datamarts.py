from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from benchmarking_data_factory.workbench.analysis_end_of_band import project_end_of_band_rows  # noqa: E402


MART_VERSION = "initial_datamart_suite.v2_3_horizon_aligned_curve_view"

MART_IDS = [
    "council_profile_mart",
    "pay_position_mart",
    "uplift_timing_mart",
    "cohort_comparison_mart",
    "report_readiness_mart",
    "evidence_trace_mart",
    "pay_rate_point_mart",
    "pay_range_summary_mart",
    "pay_progression_service_year_mart",
    "pay_distribution_point_mart",
    "pay_service_horizon_curve_view",
    "entitlement_summary_mart",
    "spatial_context_mart",
    "rate_cap_context_mart",
    "agreement_lineage_mart",
    "temporal_pay_movement_mart",
    "benchmark_question_mart",
    "report_product_input_mart",
    "data_quality_issue_mart",
]

GOVERNED_CANONICAL_IDS = [
    "council_agreements",
    "pay_rows",
    "uplift_rules",
    "end_of_band_dollars",
    "evidence_refs",
    "readiness_status",
    "cohort_memberships",
    "source_documents",
    "report_inputs",
    "spatial_reference",
    "entitlement_items",
    "rate_cap_reference",
    "benchmark_questions",
]

PAY_METRIC_TYPES = [
    "entry_rate",
    "capacity_rate",
    "range_midpoint_rate",
    "step_mean_rate",
    "service_year_0_rate",
    "service_year_1_rate",
    "service_year_2_rate",
    "service_year_3_rate",
    "service_year_4_rate",
    "service_year_5_rate",
    "service_year_6_rate",
    "progression_spread_abs",
    "progression_spread_pct",
    "time_to_capacity",
]

RANGE_ROLES = ["entry", "internal_step", "capacity", "singleton", "unknown", "blocked"]
DETERMINISTIC_PROGRESSION_BASES = {
    "annual_service_increment",
    "monthly_service_increment",
    "fixed_period_service_increment",
}
ESTIMATED_PROGRESSION_BASIS = "service_horizon_level_order_estimate"
NON_DETERMINISTIC_PROGRESSION_BASES = {
    "competency_based",
    "performance_based",
    "appointment_based",
    "classification_reclassification",
    "mixed",
    "not_specified",
    "source_unclear",
}
PROGRESSION_BASES = sorted(
    DETERMINISTIC_PROGRESSION_BASES
    | NON_DETERMINISTIC_PROGRESSION_BASES
    | {ESTIMATED_PROGRESSION_BASIS, "not_reviewed", "not_applicable"}
)
CALCULATION_STATUSES = [
    "calculated_from_governed_points",
    "calculated_from_governed_progression_rule",
    "calculated_from_level_ordinal_estimate",
    "blocked_missing_pay_points",
    "blocked_ambiguous_range_grouping",
    "blocked_missing_progression_rule",
    "blocked_non_deterministic_progression",
    "blocked_source_unclear",
    "staged_not_governed",
    "not_reviewed",
]

RESOLVED_VALUE_MODES = [
    "exact_level_point",
    "capacity_carry_forward",
    "blocked_missing_progression_rule",
    "blocked_non_deterministic_progression",
    "blocked_ambiguous_range_grouping",
    "not_reviewed",
]

SERVICE_HORIZON_WINDOWS: list[dict[str, Any]] = [
    {
        "service_horizon_window_id": "entry_only",
        "service_horizon_window_label": "Entry rate distribution",
        "included_metric_points": ["entry_rate"],
        "included_service_horizon_years": [],
    },
    {
        "service_horizon_window_id": "range_midpoint_only",
        "service_horizon_window_label": "Range midpoint rate distribution",
        "included_metric_points": ["range_midpoint_rate"],
        "included_service_horizon_years": [],
    },
    {
        "service_horizon_window_id": "y3_only",
        "service_horizon_window_label": "Year 3 service-horizon distribution",
        "included_metric_points": ["service_year_3_rate"],
        "included_service_horizon_years": [3],
    },
    {
        "service_horizon_window_id": "capacity_only",
        "service_horizon_window_label": "Capacity rate distribution",
        "included_metric_points": ["capacity_rate"],
        "included_service_horizon_years": [],
    },
    {
        "service_horizon_window_id": "entry_to_y3",
        "service_horizon_window_label": "Entry-to-Year-3 service-horizon distribution",
        "included_metric_points": ["entry_rate", "service_year_1_rate", "service_year_2_rate", "service_year_3_rate"],
        "included_service_horizon_years": [1, 2, 3],
    },
    {
        "service_horizon_window_id": "y3_to_y6",
        "service_horizon_window_label": "Year-3-to-Year-6 service-horizon distribution",
        "included_metric_points": ["service_year_3_rate", "service_year_4_rate", "service_year_5_rate", "service_year_6_rate"],
        "included_service_horizon_years": [3, 4, 5, 6],
    },
    {
        "service_horizon_window_id": "entry_to_y6",
        "service_horizon_window_label": "Entry-to-Year-6 service-horizon distribution",
        "included_metric_points": [
            "entry_rate",
            "service_year_1_rate",
            "service_year_2_rate",
            "service_year_3_rate",
            "service_year_4_rate",
            "service_year_5_rate",
            "service_year_6_rate",
        ],
        "included_service_horizon_years": [1, 2, 3, 4, 5, 6],
    },
    {
        "service_horizon_window_id": "entry_to_capacity_profile",
        "service_horizon_window_label": "Entry-to-capacity service-horizon profile",
        "included_metric_points": [
            "entry_rate",
            "service_year_1_rate",
            "service_year_2_rate",
            "service_year_3_rate",
            "service_year_4_rate",
            "service_year_5_rate",
            "service_year_6_rate",
            "capacity_rate",
        ],
        "included_service_horizon_years": [1, 2, 3, 4, 5, 6],
    },
]

CONTRACT_PATHS = {
    mart_id: f"docs/datamarts/contracts/{mart_id}.md"
    for mart_id in MART_IDS
}
GOVERNED_CANONICAL_CONTRACT_PATHS = {
    dataset_id: f"docs/governed_canonical/contracts/{dataset_id}.md"
    for dataset_id in GOVERNED_CANONICAL_IDS
}

COUNCIL_AGREEMENT_FIELDS = [
    "agreement_id",
    "base_agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "candidate_agreement_status",
    "matter_number",
    "print_id",
    "version",
    "pipeline_status",
    "superseded_by_ae_id",
    "lineage_key",
    "lineage_basis",
    "source_evidence_status",
    "canonical_record_status",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_PAY_ROW_FIELDS = [
    "pay_row_id",
    "agreement_id",
    "base_agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "period_index",
    "pay_row_index",
    "band",
    "level",
    "classification_key",
    "classification_label",
    "governed_rate_value",
    "governed_rate_unit",
    "weekly_rate",
    "annual_rate",
    "fortnightly_rate",
    "hourly_rate",
    "effective_from",
    "to_date",
    "period_basis",
    "source_table_title",
    "source_clause",
    "source_pages",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
    "date_snap_status",
    "snap_basis",
    "snap_note",
    "progression_basis",
    "progression_interval_months",
    "progression_rule_source",
    "progression_rule_status",
]

GOVERNED_UPLIFT_RULE_FIELDS = [
    "uplift_rule_id",
    "agreement_id",
    "base_agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "period_index",
    "effective_date",
    "timing_clause",
    "timing_pattern",
    "recurrence",
    "quantum",
    "quantum_type",
    "pct_component",
    "dollar_component",
    "dollar_basis",
    "resolved_pct",
    "resolved_basis",
    "fallback_status",
    "date_snap_status",
    "source_rule_id",
    "source_page",
    "source_clause",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_END_OF_BAND_DOLLAR_FIELDS = [
    "end_of_band_id",
    "agreement_id",
    "base_agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "period_index",
    "band",
    "effective_from",
    "to_date",
    "end_of_band_cash_amount",
    "amount_basis",
    "calculation_status",
    "rule_kind",
    "clause_number",
    "clause_heading",
    "source_page",
    "clause_extract",
    "max_weekly_rate",
    "next_band_min_weekly_rate",
    "end_of_band_weekly_rate",
    "end_of_band_rate_source_effective_from",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_EVIDENCE_REF_FIELDS = [
    "evidence_ref_id",
    "governed_record_id",
    "governed_record_type",
    "agreement_id",
    "base_agreement_id",
    "council_key",
    "source_document_id",
    "source_document_file",
    "source_page_ref",
    "source_clause_ref",
    "source_table_ref",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_READINESS_FIELDS = [
    "agreement_id",
    "base_agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "pay_canonical_status",
    "uplift_canonical_status",
    "identity_canonical_status",
    "source_evidence_status",
    "unresolved_issue_count",
    "blocked_reason",
    "recommended_next_review_action",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "review_governance_status",
    "governed_canonical_status",
]

GOVERNED_COHORT_MEMBERSHIP_FIELDS = [
    "cohort_membership_id",
    "council_key",
    "council_name",
    "cohort_type",
    "cohort_member",
    "cohort_definition_version",
    "inclusion_reason",
    "exclusion_unknown_handling",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_SOURCE_DOCUMENT_FIELDS = [
    "source_document_id",
    "agreement_id",
    "source_name",
    "source_type",
    "source_origin",
    "fetched_at",
    "content_hash",
    "frozen_path",
    "file_size_bytes",
    "source_status",
    "serviceability_status",
    "discovery_reference",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_REPORT_INPUT_FIELDS = [
    "report_input_id",
    "asset_id",
    "asset_type",
    "title",
    "source_dataset",
    "source_dataset_version",
    "input_mart_version",
    "asset_status",
    "pay_metric_set",
    "default_pay_metric",
    "available_pay_metrics",
    "blocked_pay_metrics",
    "metric_caveats",
    "service_horizon_window_id",
    "service_horizon_window_label",
    "included_metric_points",
    "weighting_method",
    "curve_source",
    "selected_council_points_source",
    "export_targets",
    "provenance_path",
    "quality_flags",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_SPATIAL_REFERENCE_FIELDS = [
    "council_key",
    "council_name",
    "spatial_key",
    "map_join_key",
    "lga_code",
    "abs_lga_code_2025",
    "abs_lga_name_2025",
    "has_abs_asgs",
    "abs_area_albers_sqkm",
    "office_township",
    "office_lat",
    "office_lon",
    "vif_metropolitan_region",
    "vif_regional_partnership",
    "vgccc_region",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_ENTITLEMENT_ITEM_FIELDS = [
    "entitlement_item_id",
    "entitlement_id",
    "entitlement_label",
    "category",
    "scope",
    "definition",
    "source_artifact_id",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

GOVERNED_RATE_CAP_REFERENCE_FIELDS = [
    "rate_cap_reference_id",
    "financial_year",
    "rate_cap_value",
    "council_key",
    "council_name",
    "approved_cap_pct",
    "resolution_status",
    "source_url",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

ENTITLEMENT_DEFINITION_OVERRIDES_PATH = Path("data") / "review" / "entitlement_definition_overrides.json"

GOVERNED_BENCHMARK_QUESTION_FIELDS = [
    "benchmark_question_id",
    "question_code",
    "question_text",
    "agreement_id",
    "artifact_id",
    "source_file_path",
    "source_agreement_id",
    "source_section_path",
    "governed_timestamp",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

COUNCIL_PROFILE_FIELDS = [
    "council_key",
    "canonical_council_name",
    "short_name",
    "status",
    "is_active",
    "council_category",
    "council_type",
    "official_name",
    "spatial_name",
    "lga_code",
    "abs_lga_code_2025",
    "vif_metropolitan_region",
    "vif_regional_partnership",
    "lgprf_group",
    "canonical_agreement_count",
    "canonical_agreement_ids",
    "candidate_agreement_count",
    "source_lineage_status",
    "source_lineage_notes",
]

PAY_POSITION_FIELDS = [
    "pay_position_id",
    "legacy_output_status",
    "metric_semantics_note",
    "recommended_metric_aware_mart",
    "council_key",
    "council_name",
    "agreement_id",
    "agreement_name",
    "period_index",
    "pay_row_index",
    "band",
    "level",
    "classification_key",
    "classification_label",
    "governed_rate_value",
    "governed_rate_unit",
    "weekly_rate",
    "annual_rate",
    "fortnightly_rate",
    "hourly_rate",
    "effective_from",
    "to_date",
    "period_basis",
    "source_table_title",
    "source_clause",
    "source_pages",
    "governed_at",
    "review_governance_status",
    "governed_canonical_status",
    "source_governed_record_reference",
    "value_status",
    "date_snap_status",
    "snap_basis",
    "snap_note",
]

UPLIFT_TIMING_FIELDS = [
    "uplift_rule_id",
    "agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "period_index",
    "effective_date",
    "timing_clause",
    "timing_pattern",
    "recurrence",
    "quantum",
    "quantum_type",
    "pct_component",
    "dollar_component",
    "dollar_basis",
    "resolved_pct",
    "resolved_basis",
    "fallback_status",
    "date_snap_status",
    "source_rule_id",
    "source_page",
    "source_clause",
    "governed_at",
    "review_governance_status",
    "governed_canonical_status",
    "value_status",
]

COHORT_COMPARISON_FIELDS = [
    "cohort_membership_id",
    "council_key",
    "council_name",
    "cohort_type",
    "cohort_member",
    "cohort_definition_version",
    "inclusion_reason",
    "exclusion_unknown_handling",
    "source_reference",
    "governed_canonical_status",
]

REPORT_READINESS_FIELDS = [
    "agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "pay_data_readiness",
    "uplift_readiness",
    "canonical_identity_readiness",
    "source_evidence_readiness",
    "unresolved_issue_count",
    "blocked_reason",
    "recommended_next_review_action",
    "readiness_status",
    "governed_canonical_status",
]

EVIDENCE_TRACE_FIELDS = [
    "evidence_trace_id",
    "governed_record_id",
    "governed_record_type",
    "agreement_id",
    "council_key",
    "source_document_id",
    "source_document_file",
    "source_page_ref",
    "source_clause_ref",
    "source_table_ref",
    "evidence_snippet",
    "confidence",
    "review_status",
    "absence_review_state",
    "source_layer",
]

PAY_RATE_POINT_FIELDS = [
    "pay_rate_point_id",
    "source_pay_row_id",
    "agreement_id",
    "ae_id",
    "canonical_council_id",
    "canonical_council_name",
    "classification_family",
    "classification_label_raw",
    "standard_band",
    "standard_level",
    "level_label_raw",
    "step_ordinal",
    "step_label_raw",
    "effective_from",
    "effective_to",
    "weekly_rate",
    "rate_basis",
    "range_group_id",
    "range_role",
    "is_entry_point",
    "is_capacity_point",
    "is_internal_progression_point",
    "is_singleton_rate",
    "progression_basis",
    "progression_interval_months",
    "progression_rule_source",
    "progression_rule_status",
    "source_clause",
    "source_pages",
    "source_row_ids",
    "governed_at",
    "governed_canonical_status",
    "review_governance_status",
    "value_status",
    "calculation_status",
    "blocker_reason",
]

PAY_RANGE_SUMMARY_FIELDS = [
    "pay_range_id",
    "agreement_id",
    "ae_id",
    "canonical_council_id",
    "canonical_council_name",
    "classification_family",
    "classification_label_raw",
    "standard_band",
    "range_group_id",
    "effective_from",
    "effective_to",
    "point_count",
    "entry_pay_rate_point_id",
    "capacity_pay_rate_point_id",
    "entry_weekly_rate",
    "capacity_weekly_rate",
    "range_midpoint_weekly_rate",
    "step_mean_weekly_rate",
    "progression_spread_abs",
    "progression_spread_pct",
    "has_incremental_structure",
    "has_singleton_rate",
    "progression_basis",
    "progression_interval_months",
    "progression_rule_source",
    "progression_rule_status",
    "calculation_status",
    "blocker_reason",
    "governed_canonical_status",
    "review_governance_status",
    "value_status",
]

PAY_PROGRESSION_SERVICE_YEAR_FIELDS = [
    "progression_value_id",
    "agreement_id",
    "ae_id",
    "canonical_council_id",
    "canonical_council_name",
    "classification_family",
    "classification_label_raw",
    "standard_band",
    "range_group_id",
    "effective_from",
    "effective_to",
    "service_year_index",
    "service_month_index",
    "service_horizon_year",
    "service_horizon_month",
    "assumed_start_point_id",
    "resolved_pay_rate_point_id",
    "ordinal_position_resolved",
    "resolved_level_label",
    "resolved_value_mode",
    "capacity_reached",
    "capacity_reached_at_service_horizon_year",
    "capacity_carry_forward",
    "actual_step_count",
    "comparison_horizon_note",
    "weekly_rate_at_service_year",
    "progression_basis",
    "progression_interval_months",
    "progression_rule_source",
    "progression_rule_status",
    "calculation_method",
    "calculation_status",
    "blocker_reason",
    "governed_canonical_status",
    "review_governance_status",
    "value_status",
]

PAY_DISTRIBUTION_POINT_FIELDS = [
    "distribution_point_id",
    "agreement_id",
    "ae_id",
    "canonical_council_id",
    "canonical_council_name",
    "cohort_id",
    "cohort_name",
    "standard_band",
    "classification_family",
    "range_group_id",
    "comparison_metric",
    "comparison_metric_label",
    "service_year_index",
    "service_horizon_year",
    "effective_from",
    "weekly_rate",
    "resolved_value_mode",
    "resolved_level_label",
    "actual_step_count",
    "capacity_carry_forward",
    "service_horizon_label",
    "metric_caveat",
    "entry_weekly_rate",
    "range_midpoint_weekly_rate",
    "capacity_weekly_rate",
    "service_year_1_weekly_rate",
    "service_year_2_weekly_rate",
    "service_year_3_weekly_rate",
    "service_year_4_weekly_rate",
    "service_year_5_weekly_rate",
    "service_year_6_weekly_rate",
    "metric_bundle_status",
    "metric_bundle_caveats",
    "percentile_rank",
    "cohort_min",
    "cohort_p25",
    "cohort_median",
    "cohort_p75",
    "cohort_max",
    "cohort_count",
    "selected_council_flag",
    "source_mart",
    "source_record_ids",
    "governed_canonical_status",
    "review_governance_status",
    "value_status",
    "calculation_status",
    "report_ready_status",
    "blocker_reason",
]

PAY_SERVICE_HORIZON_CURVE_VIEW_FIELDS = [
    "curve_id",
    "cohort_id",
    "cohort_name",
    "standard_band",
    "effective_from",
    "effective_to",
    "service_horizon_window_id",
    "service_horizon_window_label",
    "included_metric_points",
    "included_service_horizon_years",
    "curve_sample_count",
    "curve_council_count",
    "weighting_method",
    "curve_min",
    "curve_p25",
    "curve_median",
    "curve_p75",
    "curve_max",
    "density_points_json",
    "comparator_envelope_json",
    "horizon_envelope_json",
    "selected_council_points_json",
    "selected_council_id",
    "selected_council_name",
    "selected_range_group_id",
    "selected_classification_family",
    "selected_council_included_in_curve_sample",
    "selected_council_min",
    "selected_council_max",
    "selected_council_position_summary",
    "chart_title",
    "caveat_status",
    "metric_caveats",
    "report_ready_status",
    "blocker_reason",
]

ENTITLEMENT_SUMMARY_FIELDS = [
    "entitlement_summary_id",
    "entitlement_id",
    "entitlement_label",
    "category",
    "scope",
    "definition",
    "summary_status",
    "absence_review_state",
    "source_artifact_id",
    "source_reference",
    "governed_canonical_status",
    "value_status",
]

SPATIAL_CONTEXT_FIELDS = [
    "council_key",
    "council_name",
    "spatial_key",
    "map_join_key",
    "lga_code",
    "abs_lga_code_2025",
    "abs_lga_name_2025",
    "abs_area_albers_sqkm",
    "office_township",
    "office_lat",
    "office_lon",
    "vif_metropolitan_region",
    "vif_regional_partnership",
    "vgccc_region",
    "has_abs_asgs",
    "spatial_context_status",
    "blocked_reason",
]

RATE_CAP_CONTEXT_FIELDS = [
    "rate_cap_context_id",
    "financial_year",
    "standard_rate_cap_pct",
    "council_key",
    "council_name",
    "approved_cap_pct",
    "effective_cap_pct",
    "rate_cap_context_status",
    "source_url",
    "governed_canonical_status",
]

AGREEMENT_LINEAGE_FIELDS = [
    "agreement_id",
    "base_agreement_id",
    "agreement_name",
    "council_key",
    "council_name",
    "matter_number",
    "print_id",
    "version",
    "pipeline_status",
    "superseded_by_ae_id",
    "lineage_key",
    "lineage_basis",
    "source_evidence_status",
    "governed_canonical_status",
]

TEMPORAL_PAY_MOVEMENT_FIELDS = [
    "pay_movement_id",
    "agreement_id",
    "council_key",
    "range_group_id",
    "comparison_metric",
    "band",
    "level",
    "from_effective_date",
    "to_effective_date",
    "from_rate",
    "to_rate",
    "rate_unit",
    "delta_value",
    "delta_pct",
    "movement_status",
    "calculation_status",
    "governed_canonical_status",
]

BENCHMARK_QUESTION_FIELDS = [
    "benchmark_question_id",
    "question_code",
    "question_text",
    "agreement_id",
    "artifact_id",
    "question_status",
    "recommended_next_action",
    "governed_canonical_status",
]

REPORT_PRODUCT_INPUT_FIELDS = [
    "report_product_input_id",
    "asset_id",
    "asset_type",
    "title",
    "source_dataset",
    "source_dataset_version",
    "input_mart_version",
    "asset_status",
    "pay_metric_set",
    "default_pay_metric",
    "available_pay_metrics",
    "blocked_pay_metrics",
    "metric_caveats",
    "service_horizon_window_id",
    "service_horizon_window_label",
    "included_metric_points",
    "weighting_method",
    "curve_source",
    "selected_council_points_source",
    "report_input_status",
    "export_targets",
    "quality_flags",
    "recommended_next_action",
    "governed_canonical_status",
]

DATA_QUALITY_ISSUE_FIELDS = [
    "data_quality_issue_id",
    "issue_type",
    "severity",
    "agreement_id",
    "council_key",
    "source_dataset",
    "source_record_id",
    "issue_status",
    "issue_detail",
    "recommended_next_action",
    "governed_canonical_status",
]


@dataclass(frozen=True)
class MartStatus:
    mart_id: str
    status: str
    row_count: int
    output_files: list[str]
    reasons: list[str]
    next_actions: list[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def entitlement_definition_overrides(root: Path) -> dict[str, str]:
    payload = read_json(root / ENTITLEMENT_DEFINITION_OVERRIDES_PATH, {})
    raw_overrides = payload.get("overrides") if isinstance(payload, dict) else {}
    if not isinstance(raw_overrides, dict):
        return {}
    definitions: dict[str, str] = {}
    for entitlement_id, value in raw_overrides.items():
        definition = value.get("definition") if isinstance(value, dict) else value
        text = str(definition or "").strip()
        if text:
            definitions[str(entitlement_id)] = text
    return definitions


def read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return default if data is None else data


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def normalise_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def slug_key(value: Any) -> str:
    text = normalise_key(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def cohort_display_name(cohort_type: Any, cohort_member: Any) -> str:
    type_label = str(cohort_type or "cohort").replace("_", " ").strip().title()
    member_label = str(cohort_member or "Unknown").replace("_", " ").strip()
    return f"{type_label}: {member_label}"


def agreement_base_id(agreement_id: str) -> str:
    return str(agreement_id or "").split("__", 1)[0].lower()


def financial_year_for_date(value: Any) -> str | None:
    text = str(value or "")
    match = re.match(r"^(\d{4})-(\d{2})-\d{2}$", text)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    start = year if month >= 7 else year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def round_number(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(value, digits)


def level_sort_key(value: Any) -> tuple[int, str]:
    text = str(value or "").strip()
    if not text:
        return (999999, "")
    numeric = number_or_none(text)
    if numeric is not None:
        return (int(numeric * 1000), text)
    match = re.search(r"[A-Za-z]", text)
    if match:
        return (ord(match.group(0).upper()) - 64, text)
    return (999998, text)


def weekly_rate_and_basis(row: dict[str, Any]) -> tuple[float | None, str | None]:
    weekly = number_or_none(row.get("weekly_rate"))
    if weekly is not None:
        return weekly, "weekly_rate"
    fortnightly = number_or_none(row.get("fortnightly_rate"))
    if fortnightly is not None:
        return fortnightly / 2, "fortnightly_rate/2"
    annual = number_or_none(row.get("annual_rate"))
    if annual is not None:
        return annual / 52, "annual_rate/52"
    hourly = number_or_none(row.get("hourly_rate"))
    if hourly is not None:
        return hourly, "hourly_rate_not_weekly_comparable"
    return None, None


def metric_label(metric: str) -> str:
    labels = {
        "entry_rate": "Entry rate",
        "capacity_rate": "Capacity rate",
        "range_midpoint_rate": "Range midpoint rate",
        "step_mean_rate": "Step mean rate",
        "service_year_0_rate": "Commencement service-horizon rate",
        "service_year_1_rate": "Year 1 service-horizon rate",
        "service_year_2_rate": "Year 2 service-horizon rate",
        "service_year_3_rate": "Year 3 service-horizon rate",
        "service_year_4_rate": "Year 4 service-horizon rate",
        "service_year_5_rate": "Year 5 service-horizon rate",
        "service_year_6_rate": "Year 6 service-horizon rate",
        "progression_spread_abs": "Progression spread, absolute",
        "progression_spread_pct": "Progression spread, percent",
        "time_to_capacity": "Time to capacity",
    }
    return labels.get(metric, metric.replace("_", " "))


def service_horizon_label(
    service_horizon_year: Any,
    resolved_level_label: Any,
    resolved_value_mode: Any,
    actual_step_count: Any,
) -> str:
    if service_horizon_year in (None, ""):
        return ""
    year = int(service_horizon_year)
    level = str(resolved_level_label or "unresolved")
    mode = str(resolved_value_mode or "")
    if mode == "capacity_carry_forward":
        return f"Year {year} service-horizon rate, capacity carried forward from Level {level}"
    if mode == "exact_level_point":
        return f"Year {year} service-horizon rate, exact Level {level} point"
    if mode.startswith("blocked"):
        return f"Year {year} service-horizon rate blocked: {mode.replace('_', ' ')}"
    return f"Year {year} service-horizon rate, actual step count {actual_step_count or 'unknown'}"


def percentile(values: list[float], q: float) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(clean) - 1)
    fraction = position - lower
    return clean[lower] + (clean[upper] - clean[lower]) * fraction


def numeric_mean(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def ae_id_from_text(value: Any) -> str | None:
    match = re.search(r"(ae\d+)", str(value or ""), re.IGNORECASE)
    return match.group(1).lower() if match else None


def list_value(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def page_list(*values: Any) -> list[str]:
    pages: list[str] = []
    for value in values:
        for item in list_value(value):
            if item in (None, ""):
                continue
            text = str(item)
            if text not in pages:
                pages.append(text)
    return pages


def choose_governed_rate(row: dict[str, Any]) -> tuple[Any, str | None]:
    for field, unit in [
        ("weekly_rate", "weekly"),
        ("annual_rate", "annual"),
        ("fortnightly_rate", "fortnightly"),
        ("hourly_rate", "hourly"),
    ]:
        value = row.get(field)
        if value not in (None, ""):
            return value, unit
    return None, None


def csv_cell(value: Any) -> Any:
    if isinstance(value, list):
        return "|".join(str(item) for item in value if item not in (None, ""))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    return value


def is_missing(value: Any) -> bool:
    return value in (None, "", [], {})


def value_counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(field)
        if isinstance(value, list):
            values = value or ["<missing>"]
        else:
            values = [value if not is_missing(value) else "<missing>"]
        for item in values:
            key = str(item)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def governance_status_coverage(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = {}
    for field in ["governed_canonical_status", "review_governance_status", "value_status", "readiness_status"]:
        if any(field in row for row in rows):
            coverage[field] = value_counts(rows, field)
    return coverage


def key_missing_fields(rows: list[dict[str, Any]], fieldnames: list[str]) -> dict[str, int]:
    missing: dict[str, int] = {}
    for field in fieldnames:
        count = sum(1 for row in rows if is_missing(row.get(field)))
        if count:
            missing[field] = count
    return dict(sorted(missing.items(), key=lambda item: (-item[1], item[0]))[:20])


def write_rows(
    output_dir: Path,
    mart_id: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
    generated_at: str,
    *,
    inputs: list[str],
    caveats: list[str],
    status: str = "built",
    extra_output_files: list[str] | None = None,
) -> MartStatus:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{mart_id}.csv"
    json_path = output_dir / f"{mart_id}.json"
    status_path = output_dir / f"{mart_id}_status.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})

    json_path.write_text(
        json.dumps(
            {
                "schema_version": MART_VERSION,
                "mart_id": mart_id,
                "generated_at": generated_at,
                "row_count": len(rows),
                "rows": rows,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    output_files = [csv_path.name, json_path.name]
    if extra_output_files:
        output_files.extend(extra_output_files)
    status_payload = {
        "schema_version": "datamart.status.v1",
        "mart_id": mart_id,
        "status": status,
        "generated_at": generated_at,
        "row_count": len(rows),
        "contract": CONTRACT_PATHS[mart_id],
        "inputs": inputs,
        "caveats": caveats,
        "governance_status_coverage": governance_status_coverage(rows),
        "key_missing_fields": key_missing_fields(rows, fieldnames),
        "blockers": caveats,
        "recommended_next_action": "Review status JSON and filter report-facing uses by governed/reviewed status.",
        "output_files": output_files,
    }
    status_path.write_text(json.dumps(status_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return MartStatus(
        mart_id=mart_id,
        status=status,
        row_count=len(rows),
        output_files=[*output_files, status_path.name],
        reasons=[],
        next_actions=[],
    )


def write_curve_view_sqlite(output_dir: Path, rows: list[dict[str, Any]], generated_at: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "pay_service_horizon_curve_view.sqlite"
    if db_path.exists():
        db_path.unlink()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("PRAGMA temp_store=MEMORY")
        connection.execute(
            """
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE curve_rows (
                row_index INTEGER PRIMARY KEY,
                standard_band TEXT,
                effective_from TEXT,
                effective_to TEXT,
                cohort_id TEXT,
                cohort_name TEXT,
                curve_council_count INTEGER,
                selected_council_id TEXT,
                selected_council_name TEXT,
                service_horizon_window_id TEXT,
                service_horizon_window_label TEXT,
                selected_range_group_id TEXT,
                row_json TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO curve_rows (
                row_index,
                standard_band,
                effective_from,
                effective_to,
                cohort_id,
                cohort_name,
                curve_council_count,
                selected_council_id,
                selected_council_name,
                service_horizon_window_id,
                service_horizon_window_label,
                selected_range_group_id,
                row_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    index,
                    row.get("standard_band"),
                    row.get("effective_from"),
                    row.get("effective_to"),
                    row.get("cohort_id"),
                    row.get("cohort_name"),
                    row.get("curve_council_count"),
                    row.get("selected_council_id"),
                    row.get("selected_council_name"),
                    row.get("service_horizon_window_id"),
                    row.get("service_horizon_window_label"),
                    row.get("selected_range_group_id"),
                    json.dumps(row, ensure_ascii=True, sort_keys=True),
                )
                for index, row in enumerate(rows)
            ),
        )
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [
                ("schema_version", MART_VERSION),
                ("mart_id", "pay_service_horizon_curve_view"),
                ("store_id", "pay_service_horizon_curve_view.sqlite"),
                ("generated_at", generated_at),
                ("row_count", str(len(rows))),
            ],
        )
        connection.execute(
            """
            CREATE INDEX idx_curve_rows_filter
            ON curve_rows (
                standard_band,
                effective_from,
                cohort_id,
                selected_council_id,
                service_horizon_window_id
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX idx_curve_rows_filter_no_period
            ON curve_rows (
                standard_band,
                cohort_id,
                selected_council_id,
                service_horizon_window_id,
                effective_from
            )
            """
        )
        connection.execute("CREATE INDEX idx_curve_rows_options_cohort ON curve_rows (cohort_id, cohort_name)")
        connection.execute("CREATE INDEX idx_curve_rows_options_council ON curve_rows (selected_council_id, selected_council_name)")
        connection.execute("CREATE INDEX idx_curve_rows_options_window ON curve_rows (service_horizon_window_id, service_horizon_window_label)")
        connection.commit()
    finally:
        connection.close()
    return db_path


def write_blocked(
    output_dir: Path,
    mart_id: str,
    generated_at: str,
    *,
    reasons: list[str],
    next_actions: list[str],
    inputs_checked: list[str],
) -> MartStatus:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / f"{mart_id}_status.json"
    payload = {
        "schema_version": "datamart.status.v1",
        "mart_id": mart_id,
        "status": "blocked",
        "generated_at": generated_at,
        "row_count": 0,
        "contract": CONTRACT_PATHS[mart_id],
        "blocked_reasons": reasons,
        "recommended_next_actions": next_actions,
        "inputs_checked": inputs_checked,
        "governance_status_coverage": {},
        "key_missing_fields": {},
    }
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return MartStatus(
        mart_id=mart_id,
        status="blocked",
        row_count=0,
        output_files=[status_path.name],
        reasons=reasons,
        next_actions=next_actions,
    )


def write_governed_rows(
    output_dir: Path,
    dataset_id: str,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
    generated_at: str,
    *,
    inputs: list[str],
    caveats: list[str],
    status: str = "built",
) -> MartStatus:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"{dataset_id}.csv"
    json_path = output_dir / f"{dataset_id}.json"
    status_path = output_dir / f"{dataset_id}_status.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_cell(row.get(field)) for field in fieldnames})

    json_path.write_text(
        json.dumps(
            {
                "schema_version": "governed_canonical.dataset.v1",
                "dataset_id": dataset_id,
                "generated_at": generated_at,
                "row_count": len(rows),
                "rows": rows,
            },
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )
    status_payload = {
        "schema_version": "governed_canonical.status.v1",
        "dataset_id": dataset_id,
        "status": status,
        "generated_at": generated_at,
        "row_count": len(rows),
        "contract": GOVERNED_CANONICAL_CONTRACT_PATHS[dataset_id],
        "inputs": inputs,
        "caveats": caveats,
        "governance_status_coverage": governance_status_coverage(rows),
        "key_missing_fields": key_missing_fields(rows, fieldnames),
        "blockers": caveats,
        "recommended_next_action": "Review status coverage before treating rows as downstream report inputs.",
        "output_files": [csv_path.name, json_path.name],
    }
    status_path.write_text(json.dumps(status_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return MartStatus(
        mart_id=dataset_id,
        status=status,
        row_count=len(rows),
        output_files=[csv_path.name, json_path.name, status_path.name],
        reasons=[],
        next_actions=[],
    )


def write_governed_blocked(
    output_dir: Path,
    dataset_id: str,
    generated_at: str,
    *,
    reasons: list[str],
    next_actions: list[str],
    inputs_checked: list[str],
) -> MartStatus:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / f"{dataset_id}_status.json"
    payload = {
        "schema_version": "governed_canonical.status.v1",
        "dataset_id": dataset_id,
        "status": "blocked",
        "generated_at": generated_at,
        "row_count": 0,
        "contract": GOVERNED_CANONICAL_CONTRACT_PATHS[dataset_id],
        "blocked_reasons": reasons,
        "recommended_next_actions": next_actions,
        "inputs_checked": inputs_checked,
        "governance_status_coverage": {},
        "key_missing_fields": {},
    }
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return MartStatus(
        mart_id=dataset_id,
        status="blocked",
        row_count=0,
        output_files=[status_path.name],
        reasons=reasons,
        next_actions=next_actions,
    )


def load_canonical_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((root / "canonical").glob("*.yaml")):
        data = read_yaml(path, {})
        if not isinstance(data, dict):
            continue
        agreement_id = str(data.get("agreement_id") or path.stem).lower()
        records.append(
            {
                "agreement_id": agreement_id,
                "base_agreement_id": agreement_base_id(agreement_id),
                "path": path,
                "relative_path": path.relative_to(root).as_posix(),
                "data": data,
            }
        )
    return records


def council_indexes(master_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    indexes: dict[str, dict[str, str]] = {}
    for row in master_rows:
        for field in ["council_key", "short_name", "long_name", "official_name", "spatial_name"]:
            key = normalise_key(row.get(field))
            if key:
                indexes[key] = row
    return indexes


def find_council(hints: list[Any], indexes: dict[str, dict[str, str]], master_rows: list[dict[str, str]]) -> dict[str, str] | None:
    for hint in hints:
        key = normalise_key(hint)
        if key and key in indexes:
            return indexes[key]
    sorted_rows = sorted(master_rows, key=lambda row: len(row.get("long_name") or ""), reverse=True)
    for hint in hints:
        text = normalise_key(hint)
        if not text:
            continue
        for row in sorted_rows:
            names = [normalise_key(row.get(field)) for field in ["long_name", "official_name", "short_name"]]
            if any(name and name in text for name in names):
                return row
    return None


def candidate_rows_by_ae(candidate_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in candidate_rows:
        ae_id = ae_id_from_text(row.get("Agreement ID"))
        if ae_id:
            rows[ae_id] = row
    return rows


def candidate_counts_by_council(candidate_rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in candidate_rows:
        name = normalise_key(row.get("lga_short_name") or row.get("matched_lga_names"))
        if name:
            counts[name] = counts.get(name, 0) + 1
    return counts


def source_docs_by_ae(source_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    docs: dict[str, dict[str, str]] = {}
    for row in source_rows:
        ae_id = ae_id_from_text(row.get("discovery_reference")) or ae_id_from_text(row.get("frozen_path"))
        if ae_id:
            docs[ae_id] = row
    return docs


def accepted_uplift_lookup(canonical: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = (
        ((canonical.get("sections") or {}).get("uplift_rules") or {})
        .get("data")
        or {}
    )
    accepted = data.get("accepted") or {}
    document = accepted.get("document") if isinstance(accepted, dict) else {}
    rules = document.get("rules") if isinstance(document, dict) else []
    lookup: dict[str, dict[str, Any]] = {}
    if isinstance(document, dict):
        lookup["__document__"] = document
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            effective = str(rule.get("effective_date") or "")
            label = str(rule.get("period_label") or "")
            if effective:
                lookup[effective] = rule
            if effective and label:
                lookup[f"{effective}::{label}"] = rule
    return lookup


def canonical_hints(
    record: dict[str, Any],
    candidates_by_ae: dict[str, dict[str, Any]],
) -> list[Any]:
    data = record["data"]
    ae_id = record["base_agreement_id"]
    candidate = candidates_by_ae.get(ae_id) or {}
    hints: list[Any] = [
        candidate.get("lga_short_name"),
        candidate.get("matched_lga_names"),
        candidate.get("lga_original_name"),
    ]
    periods = ((((data.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
    for period in periods:
        if not isinstance(period, dict):
            continue
        table = period.get("pay_table")
        if isinstance(table, dict):
            provenance = table.get("provenance") or {}
            if isinstance(provenance, dict):
                hints.append(provenance.get("canonical_lga_short_name"))
    document = accepted_uplift_lookup(data).get("__document__") or {}
    hints.extend([document.get("council"), *(document.get("covered_councils") or [])])
    hints.append(data.get("source_name"))
    if "__" in record["agreement_id"]:
        hints.append(record["agreement_id"].split("__", 1)[1].replace("_", " "))
    return hints


def annotate_councils(
    records: list[dict[str, Any]],
    candidates_by_ae: dict[str, dict[str, Any]],
    council_index: dict[str, dict[str, str]],
    council_rows: list[dict[str, str]],
) -> None:
    for record in records:
        council = find_council(canonical_hints(record, candidates_by_ae), council_index, council_rows)
        record["council"] = council


def build_council_agreement_rows(
    records: list[dict[str, Any]],
    candidates_by_ae: dict[str, dict[str, Any]],
    source_docs: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        data = record["data"]
        council = record.get("council") or {}
        candidate = candidates_by_ae.get(record["base_agreement_id"]) or {}
        source_doc = source_docs.get(record["agreement_id"]) or source_docs.get(record["base_agreement_id"]) or {}
        has_governed_pay = False
        has_governed_uplift = False
        periods = ((((data.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
        for period in periods:
            if not isinstance(period, dict):
                continue
            if isinstance(period.get("pay_table"), dict) and period.get("pay_table_governed_at"):
                has_governed_pay = True
            if isinstance(period.get("uplift_rule"), dict) and period.get("uplift_rule_governed_at"):
                has_governed_uplift = True
        value_status = []
        if not council.get("council_key"):
            value_status.append("source_unclear_council_identity")
        if not source_doc:
            value_status.append("source_evidence_not_registered")
        if not (has_governed_pay or has_governed_uplift):
            value_status.append("blocked_missing_governed_pay_and_uplift")
        rows.append(
            {
                "agreement_id": record["agreement_id"],
                "base_agreement_id": record["base_agreement_id"],
                "agreement_name": data.get("source_name"),
                "council_key": council.get("council_key"),
                "council_name": council.get("long_name") or council.get("short_name"),
                "candidate_agreement_status": candidate.get("pipeline_status") or "candidate_not_governed",
                "matter_number": candidate.get("Matter Number"),
                "print_id": candidate.get("Print ID"),
                "version": candidate.get("Version"),
                "pipeline_status": candidate.get("pipeline_status"),
                "superseded_by_ae_id": candidate.get("superseded_by_ae_id"),
                "lineage_key": candidate.get("lineage_key"),
                "lineage_basis": candidate.get("lineage_basis"),
                "source_evidence_status": (
                    "frozen"
                    if source_doc.get("serviceability_status") == "frozen"
                    else "source_evidence_not_registered"
                    if not source_doc
                    else source_doc.get("serviceability_status")
                ),
                "canonical_record_status": "canonical_workspace_record",
                "source_file_path": record["relative_path"],
                "source_agreement_id": record["agreement_id"],
                "source_section_path": "canonical_document_root",
                "governed_timestamp": None,
                "review_governance_status": "canonical_reference_only",
                "governed_canonical_status": "canonical_reference_only",
                "value_status": value_status or ["not_applicable"],
            }
        )
    return rows


def build_governed_pay_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        data = record["data"]
        council = record.get("council") or {}
        periods = ((((data.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
        for period_index, period in enumerate(periods):
            if not isinstance(period, dict):
                continue
            pay_table = period.get("pay_table")
            governed_at = period.get("pay_table_governed_at")
            if not isinstance(pay_table, dict) or not governed_at:
                continue
            source_pages = page_list(pay_table.get("source_pages"), pay_table.get("source_page"))
            progression_basis = (
                pay_table.get("progression_basis")
                or period.get("progression_basis")
                or "not_reviewed"
            )
            progression_interval_months = (
                pay_table.get("progression_interval_months")
                or period.get("progression_interval_months")
            )
            progression_rule_source = (
                pay_table.get("progression_rule_source")
                or period.get("progression_rule_source")
            )
            progression_rule_status = (
                pay_table.get("progression_rule_status")
                or period.get("progression_rule_status")
                or ("governed" if pay_table.get("progression_rule_governed_at") or period.get("progression_rule_governed_at") else "not_reviewed")
            )
            for row_index, pay_row in enumerate(pay_table.get("rows") or []):
                if not isinstance(pay_row, dict):
                    continue
                value, unit = choose_governed_rate(pay_row)
                value_status = (
                    "governed_rate_value_present"
                    if value not in (None, "")
                    else "blocked_missing_governed_rate_value"
                )
                pay_row_id = f"payrow::{record['agreement_id']}::{period_index}::{row_index}"
                source_section_path = f"sections.uplifts.data.periods[{period_index}].pay_table.rows[{row_index}]"
                rows.append(
                    {
                        "pay_row_id": pay_row_id,
                        "council_key": council.get("council_key"),
                        "council_name": council.get("long_name") or council.get("short_name"),
                        "agreement_id": record["agreement_id"],
                        "base_agreement_id": record["base_agreement_id"],
                        "agreement_name": data.get("source_name"),
                        "period_index": period_index,
                        "pay_row_index": row_index,
                        "band": pay_row.get("standard_band") or pay_row.get("band"),
                        "level": pay_row.get("standard_level") or pay_row.get("level"),
                        "classification_key": pay_row.get("classification_key"),
                        "classification_label": pay_row.get("classification_label"),
                        "governed_rate_value": value,
                        "governed_rate_unit": unit,
                        "weekly_rate": pay_row.get("weekly_rate"),
                        "annual_rate": pay_row.get("annual_rate"),
                        "fortnightly_rate": pay_row.get("fortnightly_rate"),
                        "hourly_rate": pay_row.get("hourly_rate"),
                        "effective_from": period.get("effective_from") or pay_table.get("effective_from"),
                        "to_date": pay_table.get("to_date") or period.get("to_date"),
                        "period_basis": "effective_from_to_date",
                        "source_table_title": pay_table.get("table_title"),
                        "source_clause": pay_table.get("source_clause"),
                        "source_pages": source_pages,
                        "source_file_path": record["relative_path"],
                        "source_agreement_id": record["agreement_id"],
                        "source_section_path": source_section_path,
                        "governed_timestamp": governed_at,
                        "review_governance_status": "governed",
                        "governed_canonical_status": "governed",
                        "value_status": value_status,
                        "date_snap_status": (
                            "date_snapped"
                            if pay_table.get("date_snapped") is True
                            else "not_snapped"
                            if pay_table.get("date_snapped") is False
                            else "not_recorded"
                        ),
                        "snap_basis": pay_table.get("snap_basis"),
                        "snap_note": pay_table.get("snap_note"),
                        "progression_basis": progression_basis,
                        "progression_interval_months": progression_interval_months,
                        "progression_rule_source": progression_rule_source,
                        "progression_rule_status": progression_rule_status,
                    }
                )
    return rows


def build_pay_position_rows(governed_pay_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in governed_pay_rows:
        rows.append(
            {
                **row,
                "pay_position_id": str(row.get("pay_row_id") or "").replace("payrow::", "paypos::", 1),
                "legacy_output_status": "legacy_raw_pay_point_metric_aware_replacement_available",
                "metric_semantics_note": "This mart preserves governed pay rows for backwards compatibility; use pay_rate_point_mart/pay_range_summary_mart/pay_distribution_point_mart for comparison metrics.",
                "recommended_metric_aware_mart": "pay_distribution_point_mart",
                "governed_at": row.get("governed_timestamp"),
                "source_governed_record_reference": f"{row.get('source_file_path')}#{row.get('source_section_path')}",
            }
        )
    return rows


def build_governed_uplift_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        data = record["data"]
        council = record.get("council") or {}
        uplift_lookup = accepted_uplift_lookup(data)
        document = uplift_lookup.get("__document__") or {}
        periods = ((((data.get("sections") or {}).get("uplifts") or {}).get("data") or {}).get("periods") or [])
        for period_index, period in enumerate(periods):
            if not isinstance(period, dict):
                continue
            rule = period.get("uplift_rule")
            governed_at = period.get("uplift_rule_governed_at")
            if not isinstance(rule, dict) or not governed_at:
                continue
            source_rule_id = str(rule.get("source_rule_id") or "")
            accepted_rule = uplift_lookup.get(source_rule_id) or uplift_lookup.get(str(rule.get("effective_date") or ""))
            if accepted_rule is None and "::" in source_rule_id:
                effective, label = source_rule_id.split("::", 1)
                accepted_rule = uplift_lookup.get(f"{effective}::{label}") or uplift_lookup.get(effective)
            accepted_rule = accepted_rule or {}
            resolved_basis = rule.get("resolved_basis")
            fallback_status = (
                f"resolved_basis:{resolved_basis}"
                if resolved_basis and resolved_basis != "unresolved"
                else "unresolved_or_no_fallback_metadata"
            )
            value_status = "governed_rule_present" if rule.get("source_quantum") or rule.get("pattern_variant") else "source_unclear"
            source_section_path = f"sections.uplifts.data.periods[{period_index}].uplift_rule"
            rows.append(
                {
                    "uplift_rule_id": f"uplift::{record['agreement_id']}::{period_index}",
                    "agreement_id": record["agreement_id"],
                    "base_agreement_id": record["base_agreement_id"],
                    "agreement_name": data.get("source_name"),
                    "council_key": council.get("council_key"),
                    "council_name": council.get("long_name") or council.get("short_name"),
                    "period_index": period_index,
                    "effective_date": period.get("effective_from") or rule.get("effective_date"),
                    "timing_clause": accepted_rule.get("timing_clause"),
                    "timing_pattern": document.get("timing_pattern"),
                    "recurrence": document.get("timing_pattern"),
                    "quantum": rule.get("source_quantum") or rule.get("pattern_variant") or accepted_rule.get("quantum"),
                    "quantum_type": rule.get("source_quantum_type") or accepted_rule.get("quantum_type"),
                    "pct_component": rule.get("pct_component"),
                    "dollar_component": rule.get("dollar_component"),
                    "dollar_basis": rule.get("dollar_basis"),
                    "resolved_pct": rule.get("resolved_pct"),
                    "resolved_basis": resolved_basis,
                    "fallback_status": fallback_status,
                    "date_snap_status": "not_applicable_no_date_snap_metadata",
                    "source_rule_id": source_rule_id or None,
                    "source_page": accepted_rule.get("source_page"),
                    "source_clause": accepted_rule.get("source_clause"),
                    "source_file_path": record["relative_path"],
                    "source_agreement_id": record["agreement_id"],
                    "source_section_path": source_section_path,
                    "governed_timestamp": governed_at,
                    "review_governance_status": "governed",
                    "governed_canonical_status": "governed",
                    "value_status": value_status,
                }
            )
    return rows


def build_uplift_timing_rows(governed_uplift_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in governed_uplift_rows:
        rows.append({**row, "governed_at": row.get("governed_timestamp")})
    return rows


def build_council_profile_rows(
    council_rows: list[dict[str, str]],
    council_agreement_rows: list[dict[str, Any]],
    candidate_count_by_council: dict[str, int],
) -> list[dict[str, Any]]:
    agreement_ids_by_council: dict[str, list[str]] = {}
    for record in council_agreement_rows:
        council_key = record.get("council_key")
        if council_key:
            agreement_ids_by_council.setdefault(council_key, []).append(str(record.get("agreement_id")))

    rows: list[dict[str, Any]] = []
    for council in council_rows:
        council_key = council.get("council_key")
        agreement_ids = sorted(set(agreement_ids_by_council.get(council_key, [])))
        candidate_count = candidate_count_by_council.get(normalise_key(council.get("short_name")), 0)
        if agreement_ids:
            lineage_status = "canonical_agreements_present"
            lineage_notes = "One or more canonical agreement files map to this council."
        elif candidate_count:
            lineage_status = "candidate_only_not_governed"
            lineage_notes = "Candidate registry rows exist, but no canonical agreement maps to this council in the current working set."
        else:
            lineage_status = "no_current_working_set_record_not_absence"
            lineage_notes = "No current working-set record was found; this is not reviewed absence."
        rows.append(
            {
                "council_key": council_key,
                "canonical_council_name": council.get("long_name"),
                "short_name": council.get("short_name"),
                "status": council.get("status"),
                "is_active": council.get("is_active"),
                "council_category": council.get("council_category"),
                "council_type": council.get("council_type"),
                "official_name": council.get("official_name"),
                "spatial_name": council.get("spatial_name"),
                "lga_code": council.get("lga_code"),
                "abs_lga_code_2025": council.get("abs_lga_code_2025"),
                "vif_metropolitan_region": council.get("vif_metropolitan_region"),
                "vif_regional_partnership": council.get("vif_regional_partnership"),
                "lgprf_group": council.get("lgprf_group"),
                "canonical_agreement_count": len(agreement_ids),
                "canonical_agreement_ids": agreement_ids,
                "candidate_agreement_count": candidate_count,
                "source_lineage_status": lineage_status,
                "source_lineage_notes": lineage_notes,
            }
        )
    return rows


def build_cohort_comparison_rows(governed_cohort_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in governed_cohort_rows:
        rows.append(
            {
                "cohort_membership_id": row.get("cohort_membership_id"),
                "council_key": row.get("council_key"),
                "council_name": row.get("council_name"),
                "cohort_type": row.get("cohort_type"),
                "cohort_member": row.get("cohort_member"),
                "cohort_definition_version": row.get("cohort_definition_version"),
                "inclusion_reason": row.get("inclusion_reason"),
                "exclusion_unknown_handling": row.get("exclusion_unknown_handling"),
                "source_reference": f"{row.get('source_file_path')}::{row.get('source_section_path')}",
                "governed_canonical_status": row.get("governed_canonical_status"),
            }
        )
    return rows


def build_governed_readiness_rows(
    council_agreement_rows: list[dict[str, Any]],
    governed_pay_rows: list[dict[str, Any]],
    governed_uplift_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pay_count_by_ae: dict[str, int] = {}
    uplift_count_by_ae: dict[str, int] = {}
    for row in governed_pay_rows:
        pay_count_by_ae[str(row.get("agreement_id"))] = pay_count_by_ae.get(str(row.get("agreement_id")), 0) + 1
    for row in governed_uplift_rows:
        uplift_count_by_ae[str(row.get("agreement_id"))] = uplift_count_by_ae.get(str(row.get("agreement_id")), 0) + 1

    rows: list[dict[str, Any]] = []
    for record in council_agreement_rows:
        ae_id = str(record.get("agreement_id"))
        pay_ready = pay_count_by_ae.get(ae_id, 0) > 0
        uplift_ready = uplift_count_by_ae.get(ae_id, 0) > 0
        identity_ready = bool(record.get("council_key"))
        source_ready = record.get("source_evidence_status") == "frozen"
        reasons: list[str] = []
        actions: list[str] = []
        if not pay_ready:
            reasons.append("pay_not_governed_in_sections_uplifts")
            actions.append("Review or promote governed pay table periods.")
        if not uplift_ready:
            reasons.append("uplift_not_governed_in_sections_uplifts")
            actions.append("Review or promote governed uplift rules.")
        if not identity_ready:
            reasons.append("canonical_council_identity_unresolved")
            actions.append("Resolve council identity against council master.")
        if not source_ready:
            reasons.append("source_evidence_not_frozen_or_not_registered")
            actions.append("Freeze or register source PDF evidence.")
        rows.append(
            {
                "agreement_id": ae_id,
                "base_agreement_id": record.get("base_agreement_id"),
                "agreement_name": record.get("agreement_name"),
                "council_key": record.get("council_key"),
                "council_name": record.get("council_name"),
                "pay_canonical_status": "governed" if pay_ready else "blocked_missing_governance",
                "uplift_canonical_status": "governed" if uplift_ready else "blocked_missing_governance",
                "identity_canonical_status": "canonical_reference_only" if identity_ready else "source_unclear",
                "source_evidence_status": "frozen" if source_ready else "blocked_missing_source_evidence",
                "unresolved_issue_count": len(reasons),
                "blocked_reason": reasons,
                "recommended_next_review_action": actions[0] if actions else "Ready for downstream report filtering.",
                "source_file_path": record.get("source_file_path"),
                "source_agreement_id": record.get("source_agreement_id"),
                "source_section_path": "governed_canonical.readiness_status",
                "review_governance_status": "derived_from_governed_canonical",
                "governed_canonical_status": "governed" if not reasons else "blocked",
            }
        )
    return rows


def build_report_readiness_rows(readiness_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in readiness_rows:
        rows.append(
            {
                "agreement_id": row.get("agreement_id"),
                "agreement_name": row.get("agreement_name"),
                "council_key": row.get("council_key"),
                "council_name": row.get("council_name"),
                "pay_data_readiness": "ready" if row.get("pay_canonical_status") == "governed" else "blocked",
                "uplift_readiness": "ready" if row.get("uplift_canonical_status") == "governed" else "blocked",
                "canonical_identity_readiness": (
                    "ready" if row.get("identity_canonical_status") == "canonical_reference_only" else "blocked"
                ),
                "source_evidence_readiness": "ready" if row.get("source_evidence_status") == "frozen" else "blocked",
                "unresolved_issue_count": row.get("unresolved_issue_count"),
                "blocked_reason": row.get("blocked_reason"),
                "recommended_next_review_action": row.get("recommended_next_review_action"),
                "readiness_status": "ready" if row.get("governed_canonical_status") == "governed" else "blocked",
                "governed_canonical_status": row.get("governed_canonical_status"),
            }
        )
    return rows


def build_governed_evidence_refs(
    governed_pay_rows: list[dict[str, Any]],
    governed_uplift_rows: list[dict[str, Any]],
    source_docs: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pay_row in governed_pay_rows:
        ae_id = str(pay_row.get("agreement_id"))
        source_doc = source_docs.get(ae_id) or source_docs.get(agreement_base_id(ae_id)) or {}
        pages = pay_row.get("source_pages") or []
        clause = pay_row.get("source_clause")
        value_status = (
            "evidence_reference_present_snippet_not_materialized"
            if pages or clause
            else "evidence_reference_missing_not_reviewed_absence"
        )
        rows.append(
            {
                "evidence_ref_id": f"evidence::{pay_row.get('pay_row_id')}",
                "governed_record_id": pay_row.get("pay_row_id"),
                "governed_record_type": "pay_row",
                "agreement_id": ae_id,
                "base_agreement_id": pay_row.get("base_agreement_id"),
                "council_key": pay_row.get("council_key"),
                "source_document_id": source_doc.get("source_document_id"),
                "source_document_file": source_doc.get("discovery_reference"),
                "source_page_ref": pages,
                "source_clause_ref": clause,
                "source_table_ref": pay_row.get("source_table_title"),
                "source_file_path": pay_row.get("source_file_path"),
                "source_agreement_id": pay_row.get("source_agreement_id"),
                "source_section_path": pay_row.get("source_section_path"),
                "review_governance_status": pay_row.get("review_governance_status"),
                "governed_canonical_status": pay_row.get("governed_canonical_status"),
                "value_status": value_status,
            }
        )
    for uplift_row in governed_uplift_rows:
        ae_id = str(uplift_row.get("agreement_id"))
        source_doc = source_docs.get(ae_id) or source_docs.get(agreement_base_id(ae_id)) or {}
        page = uplift_row.get("source_page")
        clause = uplift_row.get("source_clause")
        value_status = (
            "evidence_reference_present_snippet_not_materialized"
            if page or clause
            else "evidence_reference_missing_not_reviewed_absence"
        )
        rows.append(
            {
                "evidence_ref_id": f"evidence::{uplift_row.get('uplift_rule_id')}",
                "governed_record_id": uplift_row.get("uplift_rule_id"),
                "governed_record_type": "uplift_rule",
                "agreement_id": ae_id,
                "base_agreement_id": uplift_row.get("base_agreement_id"),
                "council_key": uplift_row.get("council_key"),
                "source_document_id": source_doc.get("source_document_id"),
                "source_document_file": source_doc.get("discovery_reference"),
                "source_page_ref": [page] if page not in (None, "") else [],
                "source_clause_ref": clause,
                "source_table_ref": None,
                "source_file_path": uplift_row.get("source_file_path"),
                "source_agreement_id": uplift_row.get("source_agreement_id"),
                "source_section_path": uplift_row.get("source_section_path"),
                "review_governance_status": uplift_row.get("review_governance_status"),
                "governed_canonical_status": uplift_row.get("governed_canonical_status"),
                "value_status": value_status,
            }
        )
    return rows


def build_evidence_trace_rows(evidence_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in evidence_refs:
        value_status = row.get("value_status")
        absence_state = (
            "value_present_evidence_snippet_not_materialized"
            if value_status == "evidence_reference_present_snippet_not_materialized"
            else value_status
        )
        rows.append(
            {
                "evidence_trace_id": str(row.get("evidence_ref_id")).replace("evidence::", "evidencetrace::", 1),
                "governed_record_id": row.get("governed_record_id"),
                "governed_record_type": row.get("governed_record_type"),
                "agreement_id": row.get("agreement_id"),
                "council_key": row.get("council_key"),
                "source_document_id": row.get("source_document_id"),
                "source_document_file": row.get("source_document_file"),
                "source_page_ref": row.get("source_page_ref"),
                "source_clause_ref": row.get("source_clause_ref"),
                "source_table_ref": row.get("source_table_ref"),
                "evidence_snippet": None,
                "confidence": None,
                "review_status": row.get("review_governance_status"),
                "absence_review_state": absence_state,
                "source_layer": "governed_canonical",
            }
        )
    return rows


def pay_range_group_id(row: dict[str, Any]) -> str:
    band = str(row.get("band") or "").strip()
    if not band:
        return f"blocked_range::{row.get('pay_row_id')}"
    return "::".join(
        [
            "payrange",
            str(row.get("agreement_id") or ""),
            str(row.get("effective_from") or "unknown_effective_from"),
            str(row.get("to_date") or "open_ended"),
            f"band_{band}",
        ]
    )


def classification_family(row: dict[str, Any]) -> str | None:
    band = str(row.get("band") or "").strip()
    if band:
        return f"band_{band}"
    key = str(row.get("classification_key") or "").strip()
    return key.split("_level_", 1)[0] if key else None


def build_pay_rate_point_rows(governed_pay_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in governed_pay_rows:
        grouped.setdefault(pay_range_group_id(row), []).append(row)

    output: list[dict[str, Any]] = []
    for range_group_id, items in sorted(grouped.items()):
        usable: list[dict[str, Any]] = []
        for row in items:
            weekly_rate, rate_basis = weekly_rate_and_basis(row)
            usable.append({**row, "_weekly_rate": weekly_rate, "_rate_basis": rate_basis})

        level_labels = [str(row.get("level") or "").strip() for row in usable if row.get("level")]
        duplicate_levels = len(level_labels) != len(set(level_labels))
        missing_group_key = range_group_id.startswith("blocked_range::")
        missing_rate = any(row.get("_weekly_rate") is None for row in usable)
        missing_level = len(usable) > 1 and any(not str(row.get("level") or "").strip() for row in usable)
        ambiguous = missing_group_key or duplicate_levels or missing_level

        if ambiguous:
            sorted_rows = sorted(usable, key=lambda row: (str(row.get("pay_row_id") or "")))
        else:
            sorted_rows = sorted(
                usable,
                key=lambda row: (
                    level_sort_key(row.get("level")),
                    number_or_none(row.get("_weekly_rate")) or 0.0,
                    str(row.get("pay_row_id") or ""),
                ),
            )

        for ordinal, row in enumerate(sorted_rows):
            weekly_rate = row.get("_weekly_rate")
            if missing_group_key:
                role = "blocked"
                status = "blocked_ambiguous_range_grouping"
                blocker = "Missing standard band/classification range key."
            elif duplicate_levels:
                role = "blocked"
                status = "blocked_ambiguous_range_grouping"
                blocker = "Duplicate level labels within the range group."
            elif missing_level:
                role = "blocked"
                status = "blocked_ambiguous_range_grouping"
                blocker = "Multiple rows in range group but one or more levels are missing."
            elif weekly_rate is None:
                role = "blocked"
                status = "blocked_missing_pay_points"
                blocker = "No governed weekly-equivalent rate is available."
            elif len(sorted_rows) == 1:
                role = "singleton"
                status = "calculated_from_governed_points"
                blocker = None
            elif ordinal == 0:
                role = "entry"
                status = "calculated_from_governed_points"
                blocker = None
            elif ordinal == len(sorted_rows) - 1:
                role = "capacity"
                status = "calculated_from_governed_points"
                blocker = None
            else:
                role = "internal_step"
                status = "calculated_from_governed_points"
                blocker = None

            output.append(
                {
                    "pay_rate_point_id": str(row.get("pay_row_id") or "").replace("payrow::", "paypoint::", 1),
                    "source_pay_row_id": row.get("pay_row_id"),
                    "agreement_id": row.get("agreement_id"),
                    "ae_id": row.get("base_agreement_id") or agreement_base_id(str(row.get("agreement_id") or "")),
                    "canonical_council_id": row.get("council_key"),
                    "canonical_council_name": row.get("council_name"),
                    "classification_family": classification_family(row),
                    "classification_label_raw": row.get("classification_label"),
                    "standard_band": row.get("band"),
                    "standard_level": row.get("level"),
                    "level_label_raw": row.get("level"),
                    "step_ordinal": None if role == "blocked" else ordinal,
                    "step_label_raw": row.get("level"),
                    "effective_from": row.get("effective_from"),
                    "effective_to": row.get("to_date"),
                    "weekly_rate": round_number(weekly_rate, 4),
                    "rate_basis": row.get("_rate_basis"),
                    "range_group_id": range_group_id,
                    "range_role": role,
                    "is_entry_point": role == "entry",
                    "is_capacity_point": role == "capacity",
                    "is_internal_progression_point": role == "internal_step",
                    "is_singleton_rate": role == "singleton",
                    "progression_basis": row.get("progression_basis") or "not_reviewed",
                    "progression_interval_months": row.get("progression_interval_months"),
                    "progression_rule_source": row.get("progression_rule_source"),
                    "progression_rule_status": row.get("progression_rule_status") or "not_reviewed",
                    "source_clause": row.get("source_clause"),
                    "source_pages": row.get("source_pages"),
                    "source_row_ids": [row.get("pay_row_id")],
                    "governed_at": row.get("governed_timestamp"),
                    "governed_canonical_status": row.get("governed_canonical_status"),
                    "review_governance_status": row.get("review_governance_status"),
                    "value_status": row.get("value_status") if weekly_rate is not None else "blocked_missing_governed_value",
                    "calculation_status": status,
                    "blocker_reason": blocker,
                }
            )
    return output


def build_pay_range_summary_rows(pay_rate_point_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in pay_rate_point_rows:
        grouped.setdefault(str(row.get("range_group_id") or ""), []).append(row)

    rows: list[dict[str, Any]] = []
    for range_group_id, points in sorted(grouped.items()):
        template = points[0] if points else {}
        blocked = [row for row in points if str(row.get("calculation_status") or "").startswith("blocked")]
        valid_points = [row for row in points if row.get("weekly_rate") not in (None, "") and not str(row.get("calculation_status") or "").startswith("blocked")]
        if blocked or not valid_points:
            status = blocked[0].get("calculation_status") if blocked else "blocked_missing_pay_points"
            blocker = blocked[0].get("blocker_reason") if blocked else "No governed pay points available for the range."
            entry = capacity = None
        else:
            singleton = [row for row in valid_points if row.get("range_role") == "singleton"]
            entry = singleton[0] if singleton else next((row for row in valid_points if row.get("range_role") == "entry"), None)
            capacity = singleton[0] if singleton else next((row for row in valid_points if row.get("range_role") == "capacity"), None)
            if not entry or not capacity:
                status = "blocked_ambiguous_range_grouping"
                blocker = "Entry or capacity role could not be resolved."
            else:
                status = "calculated_from_governed_points"
                blocker = None

        rates = [number_or_none(row.get("weekly_rate")) for row in valid_points]
        clean_rates = [rate for rate in rates if rate is not None]
        entry_rate = number_or_none(entry.get("weekly_rate")) if entry else None
        capacity_rate = number_or_none(capacity.get("weekly_rate")) if capacity else None
        midpoint = ((entry_rate + capacity_rate) / 2) if entry_rate is not None and capacity_rate is not None else None
        step_mean = (sum(clean_rates) / len(clean_rates)) if clean_rates else None
        spread_abs = (capacity_rate - entry_rate) if entry_rate is not None and capacity_rate is not None else None
        spread_pct = (spread_abs / entry_rate) if spread_abs is not None and entry_rate else None
        progression_basis = next((row.get("progression_basis") for row in valid_points if row.get("progression_basis")), None) or "not_reviewed"
        progression_interval = next((row.get("progression_interval_months") for row in valid_points if row.get("progression_interval_months")), None)
        progression_source = next((row.get("progression_rule_source") for row in valid_points if row.get("progression_rule_source")), None)
        progression_status = next((row.get("progression_rule_status") for row in valid_points if row.get("progression_rule_status")), None) or "not_reviewed"

        rows.append(
            {
                "pay_range_id": f"paysummary::{range_group_id}",
                "agreement_id": template.get("agreement_id"),
                "ae_id": template.get("ae_id"),
                "canonical_council_id": template.get("canonical_council_id"),
                "canonical_council_name": template.get("canonical_council_name"),
                "classification_family": template.get("classification_family"),
                "classification_label_raw": template.get("classification_label_raw"),
                "standard_band": template.get("standard_band"),
                "range_group_id": range_group_id,
                "effective_from": template.get("effective_from"),
                "effective_to": template.get("effective_to"),
                "point_count": len(valid_points),
                "entry_pay_rate_point_id": entry.get("pay_rate_point_id") if entry else None,
                "capacity_pay_rate_point_id": capacity.get("pay_rate_point_id") if capacity else None,
                "entry_weekly_rate": round_number(entry_rate, 4),
                "capacity_weekly_rate": round_number(capacity_rate, 4),
                "range_midpoint_weekly_rate": round_number(midpoint, 4),
                "step_mean_weekly_rate": round_number(step_mean, 4),
                "progression_spread_abs": round_number(spread_abs, 4),
                "progression_spread_pct": round_number(spread_pct, 6),
                "has_incremental_structure": len(valid_points) > 1,
                "has_singleton_rate": len(valid_points) == 1 and valid_points[0].get("range_role") == "singleton",
                "progression_basis": progression_basis,
                "progression_interval_months": progression_interval,
                "progression_rule_source": progression_source,
                "progression_rule_status": progression_status,
                "calculation_status": status,
                "blocker_reason": blocker,
                "governed_canonical_status": "governed" if status == "calculated_from_governed_points" else "blocked",
                "review_governance_status": "derived_from_governed_pay_rows",
                "value_status": "present_unresolved" if status == "calculated_from_governed_points" else status,
            }
        )
    return rows


def build_pay_progression_service_year_rows(
    pay_range_summary_rows: list[dict[str, Any]],
    pay_rate_point_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    points_by_range: dict[str, list[dict[str, Any]]] = {}
    for point in pay_rate_point_rows:
        if point.get("weekly_rate") in (None, ""):
            continue
        if str(point.get("calculation_status") or "").startswith("blocked"):
            continue
        points_by_range.setdefault(str(point.get("range_group_id") or ""), []).append(point)
    for items in points_by_range.values():
        items.sort(key=lambda row: (int(row.get("step_ordinal") or 0), level_sort_key(row.get("standard_level"))))

    rows: list[dict[str, Any]] = []
    for summary in pay_range_summary_rows:
        range_group_id = str(summary.get("range_group_id") or "")
        points = points_by_range.get(range_group_id, [])
        entry_point = next((point for point in points if point.get("range_role") in {"entry", "singleton"}), None)
        capacity_point = points[-1] if points else None
        actual_step_count = len(points)
        progression_basis = summary.get("progression_basis") or "not_reviewed"
        progression_status = summary.get("progression_rule_status") or "not_reviewed"
        interval = number_or_none(summary.get("progression_interval_months"))
        if interval is None and progression_basis == "annual_service_increment":
            interval = 12
        if interval is None and progression_basis == "monthly_service_increment":
            interval = 1
        deterministic = progression_basis in DETERMINISTIC_PROGRESSION_BASES and progression_status in {"governed", "reviewed", "accepted"}
        estimate_capacity_horizon = actual_step_count if actual_step_count else None
        governed_capacity_horizon = max(actual_step_count - 1, 0) if actual_step_count else None

        for service_year in range(0, 7):
            resolved_point = None
            weekly_rate = None
            resolved_value_mode = "not_reviewed"
            ordinal_position_resolved = None
            capacity_reached = False
            capacity_carry_forward = False
            capacity_reached_at = None
            comparison_note = None
            if summary.get("calculation_status") != "calculated_from_governed_points" or not points or not entry_point:
                status = summary.get("calculation_status") or "blocked_missing_pay_points"
                blocker = summary.get("blocker_reason") or "Pay range is not safely calculable."
                method = "blocked_pay_range"
                resolved_value_mode = (
                    "blocked_ambiguous_range_grouping"
                    if status == "blocked_ambiguous_range_grouping"
                    else "blocked_missing_progression_rule"
                )
                comparison_note = blocker
            elif service_year == 0:
                resolved_point = entry_point
                weekly_rate = number_or_none(entry_point.get("weekly_rate"))
                status = "calculated_from_governed_points"
                blocker = None
                method = "service_year_0_entry_commencement_rate"
                ordinal_position_resolved = int(entry_point.get("step_ordinal") or 0) + 1
                capacity_reached = entry_point.get("range_role") == "singleton"
                capacity_reached_at = 0 if capacity_reached else estimate_capacity_horizon
                resolved_value_mode = "exact_level_point"
                comparison_note = "Service horizon year 0 is the entry or commencement rate."
            elif deterministic:
                step_index = min(service_year, len(points) - 1)
                resolved_point = points[step_index]
                weekly_rate = number_or_none(resolved_point.get("weekly_rate"))
                status = "calculated_from_governed_progression_rule"
                blocker = None
                method = "service_year_N_after_completed_years_from_governed_increment_rule"
                ordinal_position_resolved = step_index + 1
                capacity_reached_at = governed_capacity_horizon
                capacity_reached = bool(capacity_reached_at is not None and service_year >= capacity_reached_at)
                capacity_carry_forward = bool(capacity_reached_at is not None and service_year > capacity_reached_at)
                resolved_value_mode = "capacity_carry_forward" if capacity_carry_forward else "exact_level_point"
                if capacity_carry_forward:
                    comparison_note = f"Service horizon year {service_year} resolves to capacity carried forward from Level {resolved_point.get('standard_level')}."
                else:
                    comparison_note = f"Service horizon year {service_year} resolves to actual Level {resolved_point.get('standard_level')} under governed progression logic."
            elif progression_basis in NON_DETERMINISTIC_PROGRESSION_BASES:
                status = "blocked_non_deterministic_progression"
                blocker = f"Progression basis `{progression_basis}` is not deterministic for service-horizon calculations."
                method = "blocked_non_deterministic_progression"
                resolved_value_mode = "blocked_non_deterministic_progression"
                comparison_note = blocker
            else:
                step_index = min(service_year - 1, len(points) - 1)
                resolved_point = points[step_index]
                weekly_rate = number_or_none(resolved_point.get("weekly_rate"))
                status = "calculated_from_level_ordinal_estimate"
                blocker = "Service-horizon value from ordered governed pay points; not a governed progression rule."
                method = "service_horizon_level_order_estimate_A_equals_year_1_capacity_carry_forward"
                ordinal_position_resolved = step_index + 1
                capacity_reached_at = estimate_capacity_horizon
                capacity_reached = bool(capacity_reached_at is not None and service_year >= capacity_reached_at)
                capacity_carry_forward = bool(
                    capacity_reached_at is not None
                    and (
                        service_year > capacity_reached_at
                        or (actual_step_count == 1 and service_year >= capacity_reached_at)
                    )
                )
                resolved_value_mode = "capacity_carry_forward" if capacity_carry_forward else "exact_level_point"
                if capacity_carry_forward and actual_step_count == 1:
                    comparison_note = f"Service horizon year {service_year} resolves to singleton capacity Level {resolved_point.get('standard_level')} carried forward."
                elif capacity_carry_forward:
                    comparison_note = f"Service horizon year {service_year} exceeds the {actual_step_count}-step structure; capacity Level {resolved_point.get('standard_level')} is carried forward."
                else:
                    comparison_note = f"Service horizon year {service_year} resolves to actual Level {resolved_point.get('standard_level')} within the {actual_step_count}-step structure."

            rows.append(
                {
                    "progression_value_id": f"progression::{range_group_id}::service_year_{service_year}",
                    "agreement_id": summary.get("agreement_id"),
                    "ae_id": summary.get("ae_id"),
                    "canonical_council_id": summary.get("canonical_council_id"),
                    "canonical_council_name": summary.get("canonical_council_name"),
                    "classification_family": summary.get("classification_family"),
                    "classification_label_raw": summary.get("classification_label_raw"),
                    "standard_band": summary.get("standard_band"),
                    "range_group_id": range_group_id,
                    "effective_from": summary.get("effective_from"),
                    "effective_to": summary.get("effective_to"),
                    "service_year_index": service_year,
                    "service_month_index": service_year * 12,
                    "service_horizon_year": service_year,
                    "service_horizon_month": service_year * 12,
                    "assumed_start_point_id": entry_point.get("pay_rate_point_id") if entry_point else None,
                    "resolved_pay_rate_point_id": resolved_point.get("pay_rate_point_id") if resolved_point else None,
                    "ordinal_position_resolved": ordinal_position_resolved,
                    "resolved_level_label": resolved_point.get("standard_level") if resolved_point else None,
                    "resolved_value_mode": resolved_value_mode,
                    "capacity_reached": capacity_reached,
                    "capacity_reached_at_service_horizon_year": capacity_reached_at,
                    "capacity_carry_forward": capacity_carry_forward,
                    "actual_step_count": actual_step_count,
                    "comparison_horizon_note": comparison_note,
                    "weekly_rate_at_service_year": round_number(weekly_rate, 4),
                    "progression_basis": (
                        progression_basis
                        if status in {"calculated_from_governed_points", "calculated_from_governed_progression_rule", "blocked_non_deterministic_progression"}
                        else ESTIMATED_PROGRESSION_BASIS
                    ),
                    "progression_interval_months": round_number(interval, 4),
                    "progression_rule_source": summary.get("progression_rule_source"),
                    "progression_rule_status": (
                        progression_status
                        if status in {"calculated_from_governed_points", "calculated_from_governed_progression_rule", "blocked_non_deterministic_progression"}
                        else "estimated_not_governed"
                    ),
                    "calculation_method": method,
                    "calculation_status": status,
                    "blocker_reason": blocker,
                    "governed_canonical_status": "governed" if status in {"calculated_from_governed_points", "calculated_from_governed_progression_rule"} else "staged_not_governed" if status == "calculated_from_level_ordinal_estimate" else "blocked",
                    "review_governance_status": "derived_from_governed_pay_rows",
                    "value_status": "present_unresolved" if status.startswith("calculated") else status,
                }
            )
    return rows


def cohort_specs_by_council(governed_cohort_rows: list[dict[str, Any]] | None) -> dict[str, list[dict[str, str]]]:
    specs_by_council: dict[str, list[dict[str, str]]] = {}
    for row in governed_cohort_rows or []:
        council_key = str(row.get("council_key") or "")
        cohort_type = str(row.get("cohort_type") or "")
        cohort_member = str(row.get("cohort_member") or "")
        if not council_key or not cohort_type or not cohort_member:
            continue
        cohort_id = f"{slug_key(cohort_type)}__{slug_key(cohort_member)}"
        spec = {
            "cohort_id": cohort_id,
            "cohort_name": cohort_display_name(cohort_type, cohort_member),
        }
        current = specs_by_council.setdefault(council_key, [])
        if spec not in current:
            current.append(spec)
    return specs_by_council


def expand_distribution_rows_for_dynamic_cohorts(
    rows: list[dict[str, Any]],
    governed_cohort_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    specs_by_council = cohort_specs_by_council(governed_cohort_rows)
    if not specs_by_council:
        return rows
    expanded: list[dict[str, Any]] = []
    for row in rows:
        expanded.append(row)
        council_id = str(row.get("canonical_council_id") or "")
        for spec in specs_by_council.get(council_id, []):
            clone = {**row}
            clone["cohort_id"] = spec["cohort_id"]
            clone["cohort_name"] = spec["cohort_name"]
            clone["distribution_point_id"] = f"{row.get('distribution_point_id')}::cohort::{spec['cohort_id']}"
            expanded.append(clone)
    return expanded


def build_pay_distribution_point_rows(
    pay_range_summary_rows: list[dict[str, Any]],
    progression_rows: list[dict[str, Any]],
    governed_cohort_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    bundle_by_range: dict[str, dict[str, Any]] = {}
    for summary in pay_range_summary_rows:
        range_group_id = str(summary.get("range_group_id") or "")
        bundle_by_range[range_group_id] = {
            "entry_weekly_rate": summary.get("entry_weekly_rate"),
            "range_midpoint_weekly_rate": summary.get("range_midpoint_weekly_rate"),
            "capacity_weekly_rate": summary.get("capacity_weekly_rate"),
            "metric_bundle_status": "ready" if summary.get("calculation_status") == "calculated_from_governed_points" else "blocked",
            "metric_bundle_caveats": [],
        }
    for row in progression_rows:
        range_group_id = str(row.get("range_group_id") or "")
        year = row.get("service_year_index")
        if year not in {1, 2, 3, 4, 5, 6}:
            continue
        bundle = bundle_by_range.setdefault(
            range_group_id,
            {
                "entry_weekly_rate": None,
                "range_midpoint_weekly_rate": None,
                "capacity_weekly_rate": None,
                "metric_bundle_status": "blocked",
                "metric_bundle_caveats": [],
            },
        )
        bundle[f"service_year_{year}_weekly_rate"] = row.get("weekly_rate_at_service_year")
        status = row.get("calculation_status")
        if status == "calculated_from_level_ordinal_estimate":
            bundle["metric_bundle_status"] = "caveated_estimate_not_report_ready"
            caveat = "Service-horizon Y1-Y6 values use ordered governed pay points; later horizons carry capacity forward after the actual ladder is exhausted."
            if caveat not in bundle["metric_bundle_caveats"]:
                bundle["metric_bundle_caveats"].append(caveat)
        elif not str(status or "").startswith("calculated"):
            bundle["metric_bundle_status"] = "blocked"
            caveat = row.get("blocker_reason") or status
            if caveat and caveat not in bundle["metric_bundle_caveats"]:
                bundle["metric_bundle_caveats"].append(caveat)
    for bundle in bundle_by_range.values():
        for year in range(1, 7):
            bundle.setdefault(f"service_year_{year}_weekly_rate", None)

    rows: list[dict[str, Any]] = []
    for summary in pay_range_summary_rows:
        bundle = bundle_by_range.get(str(summary.get("range_group_id") or ""), {})
        metric_sources = [
            ("entry_rate", summary.get("entry_weekly_rate"), [summary.get("entry_pay_rate_point_id")]),
            ("capacity_rate", summary.get("capacity_weekly_rate"), [summary.get("capacity_pay_rate_point_id")]),
            ("range_midpoint_rate", summary.get("range_midpoint_weekly_rate"), [summary.get("pay_range_id")]),
            ("step_mean_rate", summary.get("step_mean_weekly_rate"), [summary.get("pay_range_id")]),
            ("progression_spread_abs", summary.get("progression_spread_abs"), [summary.get("pay_range_id")]),
            ("progression_spread_pct", summary.get("progression_spread_pct"), [summary.get("pay_range_id")]),
        ]
        for metric, rate, source_ids in metric_sources:
            status = summary.get("calculation_status")
            blocked = status != "calculated_from_governed_points" or rate in (None, "")
            rows.append(
                {
                    "distribution_point_id": f"paydist::{summary.get('range_group_id')}::{metric}",
                    "agreement_id": summary.get("agreement_id"),
                    "ae_id": summary.get("ae_id"),
                    "canonical_council_id": summary.get("canonical_council_id"),
                    "canonical_council_name": summary.get("canonical_council_name"),
                    "cohort_id": "all_governed",
                    "cohort_name": "All governed comparable rows",
                    "standard_band": summary.get("standard_band"),
                    "classification_family": summary.get("classification_family"),
                    "range_group_id": summary.get("range_group_id"),
                    "comparison_metric": metric,
                    "comparison_metric_label": metric_label(metric),
                    "service_year_index": None,
                    "service_horizon_year": None,
                    "effective_from": summary.get("effective_from"),
                    "weekly_rate": None if blocked else rate,
                    "resolved_value_mode": None,
                    "resolved_level_label": None,
                    "actual_step_count": None,
                    "capacity_carry_forward": None,
                    "service_horizon_label": None,
                    "metric_caveat": None,
                    **bundle,
                    "selected_council_flag": False,
                    "source_mart": "pay_range_summary_mart",
                    "source_record_ids": [item for item in source_ids if item],
                    "governed_canonical_status": summary.get("governed_canonical_status"),
                    "review_governance_status": summary.get("review_governance_status"),
                    "value_status": summary.get("value_status") if not blocked else status,
                    "calculation_status": status,
                    "report_ready_status": "ready" if not blocked else "blocked",
                    "blocker_reason": summary.get("blocker_reason") if blocked else None,
                }
            )

    for row in progression_rows:
        year = row.get("service_year_index")
        if year not in {0, 1, 2, 3, 4, 5, 6}:
            continue
        metric = f"service_year_{year}_rate"
        bundle = bundle_by_range.get(str(row.get("range_group_id") or ""), {})
        blocked = not str(row.get("calculation_status") or "").startswith("calculated")
        report_ready_status = (
            "ready"
            if row.get("calculation_status") == "calculated_from_governed_progression_rule"
            else "caveated_estimate_not_report_ready"
            if row.get("calculation_status") == "calculated_from_level_ordinal_estimate"
            else "ready"
            if row.get("calculation_status") == "calculated_from_governed_points"
            else "blocked"
        )
        rows.append(
            {
                "distribution_point_id": f"paydist::{row.get('range_group_id')}::{metric}",
                "agreement_id": row.get("agreement_id"),
                "ae_id": row.get("ae_id"),
                "canonical_council_id": row.get("canonical_council_id"),
                "canonical_council_name": row.get("canonical_council_name"),
                "cohort_id": "all_governed",
                "cohort_name": "All governed comparable rows",
                "standard_band": row.get("standard_band"),
                "classification_family": row.get("classification_family"),
                "range_group_id": row.get("range_group_id"),
                "comparison_metric": metric,
                "comparison_metric_label": metric_label(metric),
                "service_year_index": year,
                "service_horizon_year": row.get("service_horizon_year"),
                "effective_from": row.get("effective_from"),
                "weekly_rate": None if blocked else row.get("weekly_rate_at_service_year"),
                "resolved_value_mode": row.get("resolved_value_mode"),
                "resolved_level_label": row.get("resolved_level_label"),
                "actual_step_count": row.get("actual_step_count"),
                "capacity_carry_forward": row.get("capacity_carry_forward"),
                "service_horizon_label": service_horizon_label(
                    row.get("service_horizon_year"),
                    row.get("resolved_level_label"),
                    row.get("resolved_value_mode"),
                    row.get("actual_step_count"),
                ),
                "metric_caveat": row.get("comparison_horizon_note"),
                **bundle,
                "selected_council_flag": False,
                "source_mart": "pay_progression_service_year_mart",
                "source_record_ids": [row.get("progression_value_id")],
                "governed_canonical_status": row.get("governed_canonical_status"),
                "review_governance_status": row.get("review_governance_status"),
                "value_status": row.get("value_status"),
                "calculation_status": row.get("calculation_status"),
                "report_ready_status": report_ready_status if not blocked else "blocked",
                "blocker_reason": row.get("blocker_reason"),
            }
        )

    rows = expand_distribution_rows_for_dynamic_cohorts(rows, governed_cohort_rows)

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        rate = number_or_none(row.get("weekly_rate"))
        if rate is None:
            continue
        key = (
            str(row.get("cohort_id") or ""),
            str(row.get("standard_band") or ""),
            str(row.get("comparison_metric") or ""),
            str(row.get("effective_from") or ""),
        )
        groups.setdefault(key, []).append(row)

    for items in groups.values():
        values = sorted(number_or_none(item.get("weekly_rate")) for item in items if number_or_none(item.get("weekly_rate")) is not None)
        if not values:
            continue
        p25 = percentile(values, 0.25)
        median = percentile(values, 0.5)
        p75 = percentile(values, 0.75)
        for item in items:
            rate = number_or_none(item.get("weekly_rate"))
            rank = None
            if rate is not None:
                rank = sum(1 for value in values if value <= rate) / len(values)
            item["percentile_rank"] = round_number(rank, 6)
            item["cohort_min"] = round_number(values[0], 4)
            item["cohort_p25"] = round_number(p25, 4)
            item["cohort_median"] = round_number(median, 4)
            item["cohort_p75"] = round_number(p75, 4)
            item["cohort_max"] = round_number(values[-1], 4)
            item["cohort_count"] = len(values)

    for row in rows:
        row.setdefault("service_horizon_year", None)
        row.setdefault("resolved_value_mode", None)
        row.setdefault("resolved_level_label", None)
        row.setdefault("actual_step_count", None)
        row.setdefault("capacity_carry_forward", None)
        row.setdefault("service_horizon_label", None)
        row.setdefault("metric_caveat", None)
        row.setdefault("entry_weekly_rate", None)
        row.setdefault("range_midpoint_weekly_rate", None)
        row.setdefault("capacity_weekly_rate", None)
        for year in range(1, 7):
            row.setdefault(f"service_year_{year}_weekly_rate", None)
        row.setdefault("metric_bundle_status", "blocked")
        row.setdefault("metric_bundle_caveats", [])
        row.setdefault("percentile_rank", None)
        row.setdefault("cohort_min", None)
        row.setdefault("cohort_p25", None)
        row.setdefault("cohort_median", None)
        row.setdefault("cohort_p75", None)
        row.setdefault("cohort_max", None)
        row.setdefault("cohort_count", 0)
    return rows


def service_horizon_window_definitions() -> list[dict[str, Any]]:
    return [{**window} for window in SERVICE_HORIZON_WINDOWS]


def json_payload(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def curve_density_points(values: list[float], bins: int = 10) -> list[dict[str, Any]]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return []
    if clean[0] == clean[-1]:
        return [{"bin_min": round_number(clean[0], 4), "bin_max": round_number(clean[-1], 4), "count": len(clean)}]
    bin_count = min(bins, len(clean))
    width = (clean[-1] - clean[0]) / bin_count
    buckets = [{"bin_min": clean[0] + width * index, "bin_max": clean[0] + width * (index + 1), "count": 0} for index in range(bin_count)]
    for value in clean:
        index = min(int((value - clean[0]) / width), bin_count - 1)
        buckets[index]["count"] += 1
    return [
        {
            "bin_min": round_number(bucket["bin_min"], 4),
            "bin_max": round_number(bucket["bin_max"], 4),
            "count": bucket["count"],
        }
        for bucket in buckets
        if bucket["count"]
    ]


def service_horizon_year_for_metric(metric: str) -> int | None:
    match = re.match(r"service_year_(\d+)_rate$", metric)
    if not match:
        return None
    return int(match.group(1))


def horizon_metric_label(metric: str) -> str:
    if metric == "entry_rate":
        return "Entry"
    if metric == "capacity_rate":
        return "Capacity"
    if metric == "range_midpoint_rate":
        return "Range midpoint"
    year = service_horizon_year_for_metric(metric)
    if year is not None:
        return f"Y{year} service-horizon"
    return metric_label(metric)


def horizon_envelope_points(window_rows: list[dict[str, Any]], included_metrics: list[str]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for index, metric in enumerate(included_metrics):
        metric_rows = [row for row in window_rows if row.get("comparison_metric") == metric]
        sample_rows = [row for row in metric_rows if number_or_none(row.get("weekly_rate")) is not None]
        values = [number_or_none(row.get("weekly_rate")) for row in sample_rows]
        clean_values = [value for value in values if value is not None]
        metric_mean = numeric_mean(clean_values)
        metric_std_dev = None
        if metric_mean is not None and clean_values:
            metric_std_dev = (sum((value - metric_mean) ** 2 for value in clean_values) / len(clean_values)) ** 0.5
        council_ids = {
            str(row.get("canonical_council_id") or row.get("agreement_id") or "")
            for row in sample_rows
        }
        points.append(
            {
                "comparison_metric": metric,
                "display_label": horizon_metric_label(metric),
                "service_horizon_year": service_horizon_year_for_metric(metric),
                "horizon_ordinal": index,
                "sample_count": len(sample_rows),
                "council_count": len({item for item in council_ids if item}),
                "min": round_number(min(clean_values), 4) if clean_values else None,
                "p25": round_number(percentile(clean_values, 0.25), 4) if clean_values else None,
                "median": round_number(percentile(clean_values, 0.5), 4) if clean_values else None,
                "p75": round_number(percentile(clean_values, 0.75), 4) if clean_values else None,
                "max": round_number(max(clean_values), 4) if clean_values else None,
                "mean": round_number(metric_mean, 4) if metric_mean is not None else None,
                "std_dev": round_number(metric_std_dev, 4) if metric_std_dev is not None else None,
                "blocked_observation_count": len(
                    [row for row in metric_rows if number_or_none(row.get("weekly_rate")) is None]
                ),
                "capacity_carry_forward_count": len(
                    [row for row in sample_rows if str(row.get("capacity_carry_forward")).lower() == "true"]
                ),
                "caveated_observation_count": len(
                    [row for row in sample_rows if row.get("report_ready_status") != "ready"]
                ),
            }
        )
    return points


def selected_curve_point_label(row: dict[str, Any]) -> str:
    metric = str(row.get("comparison_metric") or "")
    if metric == "entry_rate":
        return "Entry"
    if metric == "capacity_rate":
        return "Capacity"
    year = row.get("service_horizon_year")
    if year not in (None, ""):
        label = f"Y{int(year)} service-horizon"
        if row.get("resolved_value_mode") == "capacity_carry_forward":
            label += f", capacity carried forward from Level {row.get('resolved_level_label') or 'unresolved'}"
        return label
    return metric_label(metric)


def capacity_reached_for_distribution_point(row: dict[str, Any]) -> bool | None:
    metric = str(row.get("comparison_metric") or "")
    if metric == "capacity_rate":
        return True
    if row.get("capacity_carry_forward") is True or str(row.get("capacity_carry_forward")).lower() == "true":
        return True
    year = number_or_none(row.get("service_horizon_year"))
    step_count = number_or_none(row.get("actual_step_count"))
    if year is not None and step_count is not None:
        return year >= step_count
    return None


def selected_curve_point_payload(row: dict[str, Any]) -> dict[str, Any]:
    weekly_rate = number_or_none(row.get("weekly_rate"))
    return {
        "comparison_metric": row.get("comparison_metric"),
        "service_horizon_year": row.get("service_horizon_year"),
        "display_label": selected_curve_point_label(row),
        "weekly_rate": round_number(weekly_rate, 4),
        "annual_rate": round_number(weekly_rate * 52, 4) if weekly_rate is not None else None,
        "resolved_level_label": row.get("resolved_level_label"),
        "resolved_value_mode": row.get("resolved_value_mode"),
        "actual_step_count": row.get("actual_step_count"),
        "capacity_carry_forward": row.get("capacity_carry_forward"),
        "capacity_reached": capacity_reached_for_distribution_point(row),
        "calculation_status": row.get("calculation_status"),
        "report_ready_status": row.get("report_ready_status"),
        "metric_caveat": row.get("metric_caveat"),
    }


def curve_position_summary(selected_values: list[float], curve_median: float | None) -> str | None:
    if not selected_values or curve_median is None:
        return None
    selected_median = percentile(selected_values, 0.5)
    if selected_median is None:
        return None
    if selected_median > curve_median:
        return "selected_window_median_above_curve_median"
    if selected_median < curve_median:
        return "selected_window_median_below_curve_median"
    return "selected_window_median_equals_curve_median"


def build_pay_service_horizon_curve_view_rows(pay_distribution_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    selected_pools: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in pay_distribution_rows:
        if row.get("cohort_id") == "all_governed":
            selected_key = (
                str(row.get("standard_band") or ""),
                str(row.get("effective_from") or ""),
                str(row.get("effective_to") or ""),
            )
            selected_pools.setdefault(selected_key, []).append(row)
        key = (
            str(row.get("cohort_id") or ""),
            str(row.get("cohort_name") or ""),
            str(row.get("standard_band") or ""),
            str(row.get("effective_from") or ""),
            str(row.get("effective_to") or ""),
        )
        groups.setdefault(key, []).append(row)

    rows: list[dict[str, Any]] = []
    windows = service_horizon_window_definitions()
    for (cohort_id, cohort_name, standard_band, effective_from, effective_to), group_rows in sorted(groups.items()):
        selected_pool = selected_pools.get((standard_band, effective_from, effective_to), group_rows)
        range_groups: dict[str, list[dict[str, Any]]] = {}
        for row in selected_pool:
            range_groups.setdefault(str(row.get("range_group_id") or ""), []).append(row)
        for window in windows:
            window_id = str(window["service_horizon_window_id"])
            included_metrics = list(window["included_metric_points"])
            included_years = list(window["included_service_horizon_years"])
            metric_set = set(included_metrics)
            window_rows = [row for row in group_rows if row.get("comparison_metric") in metric_set]
            sample_rows = [row for row in window_rows if number_or_none(row.get("weekly_rate")) is not None]
            values = [number_or_none(row.get("weekly_rate")) for row in sample_rows]
            clean_values = [value for value in values if value is not None]
            curve_min = round_number(min(clean_values), 4) if clean_values else None
            curve_p25 = round_number(percentile(clean_values, 0.25), 4) if clean_values else None
            curve_median = round_number(percentile(clean_values, 0.5), 4) if clean_values else None
            curve_p75 = round_number(percentile(clean_values, 0.75), 4) if clean_values else None
            curve_max = round_number(max(clean_values), 4) if clean_values else None
            curve_council_ids = {str(row.get("canonical_council_id") or row.get("agreement_id") or "") for row in sample_rows}
            curve_council_count = len({item for item in curve_council_ids if item})
            blocked_count = len([row for row in window_rows if number_or_none(row.get("weekly_rate")) is None])
            carry_forward_count = len([row for row in sample_rows if str(row.get("capacity_carry_forward")).lower() == "true"])
            caveated_count = len([row for row in sample_rows if row.get("report_ready_status") != "ready"])
            metric_caveats = [
                "Curve and selected dots are drawn from the same service_horizon_window metric universe.",
                "weighting_method=observation_weighted; each council-horizon observation contributes one value.",
            ]
            if blocked_count:
                metric_caveats.append(f"{blocked_count} blocked or missing observations were excluded from curve statistics.")
            if carry_forward_count:
                metric_caveats.append(f"{carry_forward_count} observations use capacity_carry_forward and must remain labelled.")
            if caveated_count:
                metric_caveats.append(f"{caveated_count} observations are caveated estimates and are not report-ready deterministic progression values.")
            if window_id == "entry_to_capacity_profile":
                metric_caveats.append("This profile deliberately includes capacity_rate in addition to service-horizon values.")
            if len(included_metrics) > 1:
                metric_caveats.append(
                    "Service-window path overlays should be read against horizon-aligned envelopes, not as movement through a pooled percentile curve."
                )
                metric_caveats.append(
                    "Selected council points are included in the horizon envelope when they belong to the chosen cohort."
                )
            envelope = {
                "service_horizon_window_id": window_id,
                "included_metric_points": included_metrics,
                "included_service_horizon_years": included_years,
                "weighting_method": "observation_weighted",
                "min": curve_min,
                "p25": curve_p25,
                "median": curve_median,
                "p75": curve_p75,
                "max": curve_max,
                "curve_sample_count": len(sample_rows),
                "curve_council_count": curve_council_count,
                "blocked_observation_count": blocked_count,
                "capacity_carry_forward_count": carry_forward_count,
            }
            density = curve_density_points(clean_values)
            horizon_envelope = horizon_envelope_points(window_rows, included_metrics)
            for range_group_id, selected_rows_all in sorted(range_groups.items()):
                selected_rows = [row for row in selected_rows_all if row.get("comparison_metric") in metric_set]
                if not selected_rows:
                    continue
                metric_order = {metric: index for index, metric in enumerate(included_metrics)}
                selected_rows.sort(key=lambda row: metric_order.get(str(row.get("comparison_metric") or ""), 999))
                selected_points = [selected_curve_point_payload(row) for row in selected_rows]
                selected_values = [
                    number_or_none(point.get("weekly_rate"))
                    for point in selected_points
                    if number_or_none(point.get("weekly_rate")) is not None
                ]
                selected_council_id = selected_rows[0].get("canonical_council_id") or selected_rows[0].get("agreement_id")
                selected_council_name = selected_rows[0].get("canonical_council_name")
                selected_council_included = bool(
                    selected_values
                    and str(selected_council_id or "") in curve_council_ids
                )
                selected_blocked = [point for point in selected_points if point.get("weekly_rate") is None]
                selected_caveated = [point for point in selected_points if point.get("report_ready_status") != "ready"]
                report_ready_status = (
                    "blocked"
                    if not clean_values or not selected_values
                    else "caveated_estimate_not_report_ready"
                    if caveated_count or selected_caveated
                    else "ready"
                )
                caveat_status = "blocked" if report_ready_status == "blocked" else "caveated" if report_ready_status != "ready" else "ready"
                blocker_reason = None
                if not clean_values:
                    blocker_reason = "No comparator observations were available for the selected service_horizon_window."
                elif not selected_values:
                    blocker_reason = "Selected council has no usable observations for the selected service_horizon_window."
                elif selected_blocked:
                    blocker_reason = "Selected council has blocked or missing observations in this window."
                label = str(window["service_horizon_window_label"])
                rows.append(
                    {
                        "curve_id": f"curve::{cohort_id}::band_{standard_band}::{effective_from or 'no_effective_date'}::{window_id}::{range_group_id}",
                        "cohort_id": cohort_id,
                        "cohort_name": cohort_name,
                        "standard_band": standard_band,
                        "effective_from": effective_from or None,
                        "effective_to": effective_to or None,
                        "service_horizon_window_id": window_id,
                        "service_horizon_window_label": label,
                        "included_metric_points": included_metrics,
                        "included_service_horizon_years": included_years,
                        "curve_sample_count": len(sample_rows),
                        "curve_council_count": curve_council_count,
                        "weighting_method": "observation_weighted",
                        "curve_min": curve_min,
                        "curve_p25": curve_p25,
                        "curve_median": curve_median,
                        "curve_p75": curve_p75,
                        "curve_max": curve_max,
                        "density_points_json": json_payload(density),
                        "comparator_envelope_json": json_payload(envelope),
                        "horizon_envelope_json": json_payload(horizon_envelope),
                        "selected_council_points_json": json_payload(selected_points),
                        "selected_council_id": selected_council_id,
                        "selected_council_name": selected_council_name,
                        "selected_range_group_id": range_group_id,
                        "selected_classification_family": selected_rows[0].get("classification_family"),
                        "selected_council_included_in_curve_sample": selected_council_included,
                        "selected_council_min": round_number(min(selected_values), 4) if selected_values else None,
                        "selected_council_max": round_number(max(selected_values), 4) if selected_values else None,
                        "selected_council_position_summary": curve_position_summary(selected_values, curve_median),
                        "chart_title": f"Band {standard_band} {label} - {cohort_name}",
                        "caveat_status": caveat_status,
                        "metric_caveats": metric_caveats,
                        "report_ready_status": report_ready_status,
                        "blocker_reason": blocker_reason,
                    }
                )
    return rows


def build_governed_end_of_band_dollar_rows(records: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        data = record["data"]
        council = record.get("council") or {}
        projected, _status = project_end_of_band_rows(
            ae_id=record["agreement_id"],
            canonical=data,
            root=root,
            registry_name=data.get("source_name"),
            lga_short_name=council.get("short_name") or council.get("long_name"),
            geography_fields={},
        )
        for row in projected:
            period_index = row.get("period_index")
            rows.append(
                {
                    "end_of_band_id": row.get("end_of_band_id"),
                    "agreement_id": record["agreement_id"],
                    "base_agreement_id": record["base_agreement_id"],
                    "agreement_name": data.get("source_name"),
                    "council_key": council.get("council_key"),
                    "council_name": council.get("long_name") or council.get("short_name"),
                    "period_index": period_index,
                    "band": row.get("band"),
                    "effective_from": row.get("effective_from"),
                    "to_date": row.get("to_date"),
                    "end_of_band_cash_amount": row.get("end_of_band_cash_amount"),
                    "amount_basis": row.get("amount_basis"),
                    "calculation_status": row.get("calculation_status"),
                    "rule_kind": row.get("rule_kind"),
                    "clause_number": row.get("clause_number"),
                    "clause_heading": row.get("clause_heading"),
                    "source_page": row.get("source_page"),
                    "clause_extract": row.get("clause_extract"),
                    "max_weekly_rate": row.get("max_weekly_rate"),
                    "next_band_min_weekly_rate": row.get("next_band_min_weekly_rate"),
                    "end_of_band_weekly_rate": row.get("end_of_band_weekly_rate"),
                    "end_of_band_rate_source_effective_from": row.get("end_of_band_rate_source_effective_from"),
                    "source_file_path": record["relative_path"],
                    "source_agreement_id": record["agreement_id"],
                    "source_section_path": f"derived.end_of_band_dollars.periods[{period_index}].bands[{row.get('band')}]",
                    "governed_timestamp": row.get("governed_at"),
                    "review_governance_status": "derived_from_governed_pay_rows_and_cached_clause_text",
                    "governed_canonical_status": "governed",
                    "value_status": "governed_end_of_band_cash_amount_present",
                }
            )
    return rows


def build_governed_cohort_memberships(
    council_rows: list[dict[str, str]],
    governed_pay_rows: list[dict[str, Any]],
    cohort_reference: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cohort_fields = [
        ("council_category", "Council category from controlled council master"),
        ("council_type", "Council type from controlled council master"),
        ("lgprf_group", "LGPRF group from controlled council master"),
        ("vif_regional_partnership", "VIF regional partnership from controlled council master"),
        ("vif_metropolitan_region", "VIF metropolitan region from controlled council master"),
        ("vgccc_region", "VGCCC region from controlled council master"),
    ]
    for council in council_rows:
        council_key = council.get("council_key")
        council_name = council.get("long_name") or council.get("short_name")
        for field, reason in cohort_fields:
            value = council.get(field)
            if value in (None, ""):
                continue
            rows.append(
                {
                    "cohort_membership_id": f"gcohort::{council_key}::{field}::{value}",
                    "council_key": council_key,
                    "council_name": council_name,
                    "cohort_type": field,
                    "cohort_member": value,
                    "cohort_definition_version": "victorian-council-master.csv",
                    "inclusion_reason": reason,
                    "exclusion_unknown_handling": "Blank reference fields are unknown, not reviewed exclusion.",
                    "source_file_path": "data/reference/victorian-council-master.csv",
                    "source_agreement_id": None,
                    "source_section_path": field,
                    "governed_timestamp": None,
                    "review_governance_status": "canonical_reference_only",
                    "governed_canonical_status": "canonical_reference_only",
                    "value_status": "present_unresolved",
                }
            )

    pay_council_keys = sorted({str(row.get("council_key")) for row in governed_pay_rows if row.get("council_key")})
    council_by_key = {row.get("council_key"): row for row in council_rows}
    cohort_version = str(cohort_reference.get("schema_version") or "unknown")
    for council_key in pay_council_keys:
        council = council_by_key.get(council_key) or {}
        rows.append(
            {
                "cohort_membership_id": f"gcohort::{council_key}::benchmark_lane::standard_band_core",
                "council_key": council_key,
                "council_name": council.get("long_name") or council.get("short_name"),
                "cohort_type": "benchmark_lane",
                "cohort_member": "standard_band_core",
                "cohort_definition_version": f"cohort-nomenclature.yaml::{cohort_version}",
                "inclusion_reason": "Council has at least one governed pay row in the standard band core lane.",
                "exclusion_unknown_handling": "Councils without governed pay rows are not emitted as excluded.",
                "source_file_path": "data/reference/cohorts/cohort-nomenclature.yaml",
                "source_agreement_id": None,
                "source_section_path": "cohorts.standard_band_core",
                "governed_timestamp": None,
                "review_governance_status": "governed_pay_presence",
                "governed_canonical_status": "governed",
                "value_status": "present_unresolved",
            }
        )
    return rows


def build_governed_source_documents(source_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in source_rows:
        agreement_id = ae_id_from_text(row.get("discovery_reference")) or ae_id_from_text(row.get("frozen_path"))
        serviceability = row.get("serviceability_status")
        status = (
            "governed"
            if serviceability == "frozen"
            else "candidate_not_governed"
            if row.get("source_status") == "candidate"
            else "staged_not_governed"
        )
        rows.append(
            {
                "source_document_id": row.get("source_document_id"),
                "agreement_id": agreement_id,
                "source_name": row.get("source_name"),
                "source_type": row.get("source_type"),
                "source_origin": row.get("source_origin"),
                "fetched_at": row.get("fetched_at"),
                "content_hash": row.get("content_hash"),
                "frozen_path": row.get("frozen_path"),
                "file_size_bytes": row.get("file_size_bytes"),
                "source_status": row.get("source_status"),
                "serviceability_status": serviceability,
                "discovery_reference": row.get("discovery_reference"),
                "source_file_path": "registers/source-document-register.csv",
                "source_agreement_id": agreement_id,
                "source_section_path": f"source_document_id:{row.get('source_document_id')}",
                "governed_timestamp": row.get("fetched_at") if serviceability == "frozen" else None,
                "review_governance_status": status,
                "governed_canonical_status": status,
                "value_status": "present_unresolved" if agreement_id else "source_unclear",
            }
        )
    return rows


def build_governed_report_inputs(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    asset_path = root / "data" / "analysis" / "distribution-point-analysis.asset.json"
    asset = read_json(asset_path, {})
    if isinstance(asset, dict) and asset:
        asset_status = str(asset.get("status") or "draft")
        canonical_status = "reviewed" if asset_status == "reviewed" else "staged_not_governed"
        if asset_status == "report_ready":
            canonical_status = "governed"
        available_pay_metrics = asset.get("available_pay_metrics") or [
            "entry_rate",
            "capacity_rate",
            "range_midpoint_rate",
            "service_year_1_rate",
            "service_year_2_rate",
            "service_year_3_rate",
            "service_year_4_rate",
            "service_year_5_rate",
            "service_year_6_rate",
        ]
        blocked_pay_metrics = asset.get("blocked_pay_metrics") or []
        metric_caveats = asset.get("metric_caveats") or [
            "Legacy distribution asset was originally midpoint-centred; use pay_distribution_point_mart for metric-aware truth.",
            "Service-horizon values use ordered governed pay points and carry capacity forward after the actual ladder is exhausted unless governed progression rules exist.",
        ]
        source_dataset = asset.get("source_dataset")
        if source_dataset in {None, "", "pay_tables"}:
            source_dataset = "pay_service_horizon_curve_view"
        visual_encoding = asset.get("visual_encoding") or {}
        input_mart_version = (
            visual_encoding.get("input_mart_version")
            or asset.get("source_dataset_version")
            or MART_VERSION
        )
        rows.append(
            {
                "report_input_id": f"reportinput::{asset.get('asset_id') or asset_path.stem}",
                "asset_id": asset.get("asset_id"),
                "asset_type": asset.get("asset_type"),
                "title": asset.get("title"),
                "source_dataset": source_dataset,
                "source_dataset_version": asset.get("source_dataset_version") or MART_VERSION,
                "input_mart_version": input_mart_version,
                "asset_status": asset_status,
                "pay_metric_set": asset.get("pay_metric_set") or "pay_structure_semantics_v1",
                "default_pay_metric": asset.get("default_pay_metric") or "range_midpoint_rate",
                "available_pay_metrics": available_pay_metrics,
                "blocked_pay_metrics": blocked_pay_metrics,
                "metric_caveats": metric_caveats,
                "service_horizon_window_id": asset.get("service_horizon_window_id") or visual_encoding.get("service_horizon_window_id"),
                "service_horizon_window_label": asset.get("service_horizon_window_label") or visual_encoding.get("service_horizon_window_label"),
                "included_metric_points": asset.get("included_metric_points") or visual_encoding.get("included_metric_points") or [],
                "weighting_method": asset.get("weighting_method") or visual_encoding.get("weighting_method"),
                "curve_source": asset.get("curve_source") or visual_encoding.get("curve_source"),
                "selected_council_points_source": asset.get("selected_council_points_source") or visual_encoding.get("selected_council_points_source"),
                "export_targets": asset.get("export_targets") or [],
                "provenance_path": (asset.get("provenance") or {}).get("asset_file"),
                "quality_flags": asset.get("quality_flags") or [],
                "source_file_path": asset_path.relative_to(root).as_posix(),
                "source_agreement_id": None,
                "source_section_path": "report_asset_manifest",
                "governed_timestamp": asset.get("generated_at") if asset_status in {"reviewed", "report_ready"} else None,
                "review_governance_status": asset_status,
                "governed_canonical_status": canonical_status,
                "value_status": "present_unresolved" if asset_status != "report_ready" else "not_applicable",
            }
        )
    return rows


def build_governed_spatial_reference(council_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for council in council_rows:
        missing = []
        for field in ["spatial_key", "map_join_key", "abs_lga_code_2025"]:
            if not council.get(field):
                missing.append(field)
        rows.append(
            {
                "council_key": council.get("council_key"),
                "council_name": council.get("long_name") or council.get("short_name"),
                "spatial_key": council.get("spatial_key"),
                "map_join_key": council.get("map_join_key"),
                "lga_code": council.get("lga_code"),
                "abs_lga_code_2025": council.get("abs_lga_code_2025"),
                "abs_lga_name_2025": council.get("abs_lga_name_2025"),
                "has_abs_asgs": council.get("has_abs_asgs"),
                "abs_area_albers_sqkm": council.get("abs_area_albers_sqkm"),
                "office_township": council.get("office_township"),
                "office_lat": council.get("office_lat"),
                "office_lon": council.get("office_lon"),
                "vif_metropolitan_region": council.get("vif_metropolitan_region"),
                "vif_regional_partnership": council.get("vif_regional_partnership"),
                "vgccc_region": council.get("vgccc_region"),
                "source_file_path": "data/reference/victorian-council-master.csv",
                "source_agreement_id": None,
                "source_section_path": "spatial_and_geographic_reference_fields",
                "governed_timestamp": None,
                "review_governance_status": "canonical_reference_only",
                "governed_canonical_status": "canonical_reference_only",
                "value_status": "present_unresolved" if not missing else "source_unclear",
            }
        )
    return rows


def build_governed_entitlement_items(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    exemplar_path = root / "wiki" / "artifacts" / "downstream-analysis-exemplars" / "ballarat-entitlement-benchmark-exemplar.json"
    exemplar = read_json(exemplar_path, {})
    definition_overrides = entitlement_definition_overrides(root)
    if isinstance(exemplar, dict):
        for category in exemplar.get("categories") or []:
            if not isinstance(category, dict):
                continue
            for entitlement in category.get("entitlements") or []:
                if not isinstance(entitlement, dict):
                    continue
                entitlement_id = entitlement.get("entitlement_id")
                definition = definition_overrides.get(str(entitlement_id)) or entitlement.get("definition")
                rows.append(
                    {
                        "entitlement_item_id": f"entitlement::{entitlement_id}",
                        "entitlement_id": entitlement_id,
                        "entitlement_label": entitlement.get("entitlement_label"),
                        "category": category.get("label") or entitlement.get("category"),
                        "scope": (entitlement.get("scope") or {}).get("scope") if isinstance(entitlement.get("scope"), dict) else entitlement.get("scope"),
                        "definition": definition,
                        "source_artifact_id": exemplar.get("artifact_id"),
                        "source_file_path": exemplar_path.relative_to(root).as_posix(),
                        "source_agreement_id": None,
                        "source_section_path": f"categories.{category.get('category_id')}.entitlements.{entitlement_id}",
                        "governed_timestamp": None,
                        "review_governance_status": "staged_not_governed",
                        "governed_canonical_status": "staged_not_governed",
                        "value_status": "not_reviewed",
                    }
                )
    return rows


def build_governed_rate_cap_reference(root: Path, council_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    base = root / "src" / "benchmarking_data_factory" / "uplift_rules" / "external" / "rate-cap"
    standard_rows = read_csv(base / "standard-statewide-rate-caps.csv")
    status_rows = {row.get("financial_year"): row for row in read_csv(base / "rate-cap-year-status.csv")}
    exception_rows = read_csv(base / "higher-cap-exceptions.csv")
    council_by_short = {normalise_key(row.get("short_name")): row for row in council_rows}
    rows: list[dict[str, Any]] = []
    for row in standard_rows:
        fy = row.get("period_year_label")
        status = status_rows.get(fy) or {}
        rows.append(
            {
                "rate_cap_reference_id": f"ratecap::standard::{fy}",
                "financial_year": fy,
                "rate_cap_value": row.get("rate_cap_value"),
                "council_key": None,
                "council_name": None,
                "approved_cap_pct": None,
                "resolution_status": status.get("resolution_status") or "source_unclear",
                "source_url": row.get("source_reference"),
                "source_file_path": "src/benchmarking_data_factory/uplift_rules/external/rate-cap/standard-statewide-rate-caps.csv",
                "source_agreement_id": None,
                "source_section_path": f"financial_year:{fy}",
                "governed_timestamp": status.get("confirmed_date"),
                "review_governance_status": "external_reference",
                "governed_canonical_status": "external_reference",
                "value_status": "present_unresolved",
            }
        )
    for row in exception_rows:
        council = council_by_short.get(normalise_key(row.get("lga_short_name"))) or {}
        fy = row.get("financial_year")
        rows.append(
            {
                "rate_cap_reference_id": f"ratecap::exception::{fy}::{row.get('lga_short_name')}",
                "financial_year": fy,
                "rate_cap_value": None,
                "council_key": council.get("council_key"),
                "council_name": council.get("long_name") or row.get("council_name"),
                "approved_cap_pct": row.get("approved_cap_pct"),
                "resolution_status": "confirmed_exception",
                "source_url": row.get("source_url"),
                "source_file_path": "src/benchmarking_data_factory/uplift_rules/external/rate-cap/higher-cap-exceptions.csv",
                "source_agreement_id": None,
                "source_section_path": f"financial_year:{fy};lga_short_name:{row.get('lga_short_name')}",
                "governed_timestamp": row.get("captured_date"),
                "review_governance_status": "external_reference",
                "governed_canonical_status": "external_reference",
                "value_status": "present_unresolved",
            }
        )
    return rows


def build_governed_benchmark_questions(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "wiki" / "questions").glob("*.json")):
        data = read_json(path, {})
        questions = data.get("questions") if isinstance(data, dict) else None
        if not isinstance(questions, list):
            questions = data if isinstance(data, list) else []
        for index, question in enumerate(questions):
            if not isinstance(question, dict):
                continue
            text = question.get("question") or question.get("text") or question.get("summary") or question.get("title")
            code = question.get("code") or question.get("question_code") or "benchmark_question"
            agreement_id = question.get("agreement_id") or question.get("ae_id")
            rows.append(
                {
                    "benchmark_question_id": f"bq::{path.stem}::{index}",
                    "question_code": code,
                    "question_text": text,
                    "agreement_id": agreement_id,
                    "artifact_id": path.stem,
                    "source_file_path": path.relative_to(root).as_posix(),
                    "source_agreement_id": agreement_id,
                    "source_section_path": f"questions[{index}]",
                    "governed_timestamp": None,
                    "review_governance_status": "staged_not_governed",
                    "governed_canonical_status": "staged_not_governed",
                    "value_status": "not_reviewed",
                }
            )
    return rows


def build_spatial_context_rows(spatial_reference_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for council in spatial_reference_rows:
        missing: list[str] = []
        if not council.get("spatial_key"):
            missing.append("spatial_key_missing")
        if not boolish(council.get("has_abs_asgs")):
            missing.append("abs_asgs_reference_not_available")
        rows.append(
            {
                "council_key": council.get("council_key"),
                "council_name": council.get("long_name") or council.get("short_name"),
                "spatial_key": council.get("spatial_key"),
                "map_join_key": council.get("map_join_key"),
                "lga_code": council.get("lga_code"),
                "abs_lga_code_2025": council.get("abs_lga_code_2025"),
                "abs_lga_name_2025": council.get("abs_lga_name_2025"),
                "abs_area_albers_sqkm": council.get("abs_area_albers_sqkm"),
                "office_township": council.get("office_township"),
                "office_lat": council.get("office_lat"),
                "office_lon": council.get("office_lon"),
                "vif_metropolitan_region": council.get("vif_metropolitan_region"),
                "vif_regional_partnership": council.get("vif_regional_partnership"),
                "vgccc_region": council.get("vgccc_region"),
                "has_abs_asgs": council.get("has_abs_asgs"),
                "spatial_context_status": "ready" if not missing else "blocked",
                "blocked_reason": missing,
            }
        )
    return rows


def build_entitlement_summary_rows(entitlement_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in entitlement_items:
        rows.append(
            {
                "entitlement_summary_id": str(item.get("entitlement_item_id")).replace("entitlement::", "entsummary::", 1),
                "entitlement_id": item.get("entitlement_id"),
                "entitlement_label": item.get("entitlement_label"),
                "category": item.get("category"),
                "scope": item.get("scope"),
                "definition": item.get("definition"),
                "summary_status": "prototype_blocked_not_governed",
                "absence_review_state": "not_reviewed",
                "source_artifact_id": item.get("source_artifact_id"),
                "source_reference": f"{item.get('source_file_path')}::{item.get('source_section_path')}",
                "governed_canonical_status": item.get("governed_canonical_status"),
                "value_status": item.get("value_status"),
            }
        )
    return rows


def build_rate_cap_context_rows(rate_cap_reference_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    standard_by_year: dict[str, Any] = {}
    for row in rate_cap_reference_rows:
        if row.get("rate_cap_value") not in (None, ""):
            standard_by_year[str(row.get("financial_year"))] = row.get("rate_cap_value")

    rows: list[dict[str, Any]] = []
    for row in rate_cap_reference_rows:
        fy = row.get("financial_year")
        standard = standard_by_year.get(str(fy)) or row.get("rate_cap_value")
        approved = row.get("approved_cap_pct")
        effective = approved if approved not in (None, "") else standard
        context_kind = "council_exception" if row.get("council_key") else "statewide_standard"
        rows.append(
            {
                "rate_cap_context_id": str(row.get("rate_cap_reference_id")).replace("ratecap::", "ratecapcontext::", 1),
                "financial_year": fy,
                "standard_rate_cap_pct": standard,
                "council_key": row.get("council_key"),
                "council_name": row.get("council_name"),
                "approved_cap_pct": approved,
                "effective_cap_pct": effective,
                "rate_cap_context_status": f"external_reference_{context_kind}",
                "source_url": row.get("source_url"),
                "governed_canonical_status": row.get("governed_canonical_status"),
            }
        )
    return rows


def build_agreement_lineage_rows(council_agreement_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in council_agreement_rows:
        rows.append({field: row.get(field) for field in AGREEMENT_LINEAGE_FIELDS})
    return rows


def build_temporal_pay_movement_rows(pay_distribution_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracked_metrics = {
        "entry_rate",
        "capacity_rate",
        "range_midpoint_rate",
        "service_year_3_rate",
    }
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in pay_distribution_rows:
        metric = str(row.get("comparison_metric") or "")
        value = number_or_none(row.get("weekly_rate"))
        if metric not in tracked_metrics or value is None or not row.get("effective_from"):
            continue
        key = (
            str(row.get("agreement_id") or ""),
            str(row.get("canonical_council_id") or ""),
            str(row.get("standard_band") or ""),
            str(row.get("classification_family") or ""),
            metric,
        )
        grouped.setdefault(key, []).append(row)

    rows: list[dict[str, Any]] = []
    for (agreement_id, council_key, band, classification_family, metric), items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (str(item.get("effective_from") or ""), str(item.get("distribution_point_id") or "")))
        for previous, current in zip(ordered, ordered[1:]):
            prev_value = number_or_none(previous.get("weekly_rate"))
            curr_value = number_or_none(current.get("weekly_rate"))
            if prev_value is None or curr_value is None:
                continue
            delta = curr_value - prev_value
            pct = (delta / prev_value * 100) if prev_value else None
            movement_id = f"paymove::{agreement_id}::{band}::{metric}::{current.get('effective_from')}"
            rows.append(
                {
                    "pay_movement_id": movement_id,
                    "agreement_id": agreement_id,
                    "council_key": council_key,
                    "range_group_id": current.get("range_group_id"),
                    "comparison_metric": metric,
                    "band": band,
                    "level": classification_family,
                    "from_effective_date": previous.get("effective_from"),
                    "to_effective_date": current.get("effective_from"),
                    "from_rate": previous.get("weekly_rate"),
                    "to_rate": current.get("weekly_rate"),
                    "rate_unit": "weekly",
                    "delta_value": round(delta, 4),
                    "delta_pct": round(pct, 4) if pct is not None else None,
                    "movement_status": f"derived_from_{metric}",
                    "calculation_status": (
                        "calculated_from_governed_points"
                        if metric != "service_year_3_rate"
                        else current.get("calculation_status")
                    ),
                    "governed_canonical_status": current.get("governed_canonical_status"),
                }
            )
    return rows


def build_benchmark_question_rows(benchmark_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in benchmark_questions:
        rows.append(
            {
                "benchmark_question_id": row.get("benchmark_question_id"),
                "question_code": row.get("question_code"),
                "question_text": row.get("question_text"),
                "agreement_id": row.get("agreement_id"),
                "artifact_id": row.get("artifact_id"),
                "question_status": row.get("review_governance_status"),
                "recommended_next_action": "Review and bind to governed canonical inputs before using as a report requirement.",
                "governed_canonical_status": row.get("governed_canonical_status"),
            }
        )
    return rows


def build_report_product_input_rows(report_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report_inputs:
        report_ready = row.get("asset_status") == "report_ready"
        rows.append(
            {
                "report_product_input_id": str(row.get("report_input_id")).replace("reportinput::", "reportproductinput::", 1),
                "asset_id": row.get("asset_id"),
                "asset_type": row.get("asset_type"),
                "title": row.get("title"),
                "source_dataset": row.get("source_dataset"),
                "source_dataset_version": row.get("source_dataset_version"),
                "input_mart_version": row.get("input_mart_version") or row.get("source_dataset_version"),
                "asset_status": row.get("asset_status"),
                "pay_metric_set": row.get("pay_metric_set"),
                "default_pay_metric": row.get("default_pay_metric"),
                "available_pay_metrics": row.get("available_pay_metrics"),
                "blocked_pay_metrics": row.get("blocked_pay_metrics"),
                "metric_caveats": row.get("metric_caveats"),
                "service_horizon_window_id": row.get("service_horizon_window_id"),
                "service_horizon_window_label": row.get("service_horizon_window_label"),
                "included_metric_points": row.get("included_metric_points"),
                "weighting_method": row.get("weighting_method"),
                "curve_source": row.get("curve_source"),
                "selected_council_points_source": row.get("selected_council_points_source"),
                "report_input_status": "report_ready" if report_ready else "draft_not_report_ready",
                "export_targets": row.get("export_targets"),
                "quality_flags": row.get("quality_flags"),
                "recommended_next_action": (
                    "Ready for product assembly filtering."
                    if report_ready
                    else "Resolve quality flags and promote the asset before report publication."
                ),
                "governed_canonical_status": row.get("governed_canonical_status"),
            }
        )
    return rows


def build_data_quality_issue_rows(
    governed_readiness_rows: list[dict[str, Any]],
    governed_pay_rows: list[dict[str, Any]],
    governed_evidence_refs: list[dict[str, Any]],
    report_inputs: list[dict[str, Any]],
    spatial_reference_rows: list[dict[str, Any]],
    entitlement_items: list[dict[str, Any]],
    pay_rate_point_rows: list[dict[str, Any]] | None = None,
    progression_rows: list[dict[str, Any]] | None = None,
    pay_distribution_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add_issue(
        issue_id: str,
        issue_type: str,
        severity: str,
        source_dataset: str,
        source_record_id: Any,
        detail: Any,
        next_action: str,
        *,
        agreement_id: Any = None,
        council_key: Any = None,
        status: str = "open",
        canonical_status: str = "blocked",
    ) -> None:
        rows.append(
            {
                "data_quality_issue_id": issue_id,
                "issue_type": issue_type,
                "severity": severity,
                "agreement_id": agreement_id,
                "council_key": council_key,
                "source_dataset": source_dataset,
                "source_record_id": source_record_id,
                "issue_status": status,
                "issue_detail": detail,
                "recommended_next_action": next_action,
                "governed_canonical_status": canonical_status,
            }
        )

    for row in governed_readiness_rows:
        if row.get("unresolved_issue_count"):
            add_issue(
                f"dq::readiness::{row.get('agreement_id')}",
                "readiness_blocker",
                "high",
                "readiness_status",
                row.get("agreement_id"),
                row.get("blocked_reason"),
                row.get("recommended_next_review_action") or "Review blocked readiness dimensions.",
                agreement_id=row.get("agreement_id"),
                council_key=row.get("council_key"),
            )

    for row in governed_pay_rows:
        if row.get("value_status") != "governed_rate_value_present":
            add_issue(
                f"dq::pay::{row.get('pay_row_id')}",
                "pay_value_blocker",
                "high",
                "pay_rows",
                row.get("pay_row_id"),
                row.get("value_status"),
                "Review the governed pay table row and either populate the governed value or record a reviewed absence state.",
                agreement_id=row.get("agreement_id"),
                council_key=row.get("council_key"),
            )

    for row in governed_evidence_refs:
        if row.get("value_status") == "evidence_reference_missing_not_reviewed_absence":
            add_issue(
                f"dq::evidence::{row.get('evidence_ref_id')}",
                "evidence_lineage_gap",
                "medium",
                "evidence_refs",
                row.get("evidence_ref_id"),
                row.get("value_status"),
                "Attach page, clause, table, or snippet evidence to the governed record.",
                agreement_id=row.get("agreement_id"),
                council_key=row.get("council_key"),
            )

    for row in pay_rate_point_rows or []:
        if row.get("calculation_status") == "blocked_ambiguous_range_grouping":
            add_issue(
                f"dq::pay_range::{row.get('pay_rate_point_id')}",
                "ambiguous_range_grouping",
                "high",
                "pay_rate_point_mart",
                row.get("pay_rate_point_id"),
                row.get("blocker_reason"),
                "Review band/level/range grouping before using entry, capacity, or midpoint metrics.",
                agreement_id=row.get("agreement_id"),
                council_key=row.get("canonical_council_id"),
            )
        if row.get("range_role") in {"unknown", "blocked"}:
            add_issue(
                f"dq::range_role::{row.get('pay_rate_point_id')}",
                "missing_range_role",
                "high",
                "pay_rate_point_mart",
                row.get("pay_rate_point_id"),
                row.get("range_role"),
                "Resolve the pay point range role or keep the row blocked from comparison metrics.",
                agreement_id=row.get("agreement_id"),
                council_key=row.get("canonical_council_id"),
            )

    for row in progression_rows or []:
        status = row.get("calculation_status")
        if status == "blocked_missing_progression_rule":
            issue_type = "blocked_missing_progression_rule"
        elif status == "blocked_non_deterministic_progression":
            issue_type = "blocked_non_deterministic_progression"
        else:
            continue
        add_issue(
            f"dq::progression::{row.get('progression_value_id')}",
            issue_type,
            "medium",
            "pay_progression_service_year_mart",
            row.get("progression_value_id"),
            row.get("blocker_reason"),
            "Review progression semantics before presenting deterministic service-horizon values.",
            agreement_id=row.get("agreement_id"),
            council_key=row.get("canonical_council_id"),
        )

    for row in pay_distribution_rows or []:
        if not row.get("comparison_metric"):
            add_issue(
                f"dq::distribution_metric::{row.get('distribution_point_id')}",
                "midpoint_used_without_metric_label",
                "high",
                "pay_distribution_point_mart",
                row.get("distribution_point_id"),
                "Distribution row has no comparison_metric.",
                "Block the row until the comparison metric is explicit.",
                agreement_id=row.get("agreement_id"),
                council_key=row.get("canonical_council_id"),
            )

    for row in report_inputs:
        source_dataset = str(row.get("source_dataset") or "")
        if source_dataset and source_dataset not in {"pay_distribution_point_mart", "pay_service_horizon_curve_view", "pay_structure_semantics_v1"}:
            add_issue(
                f"dq::chart_metric_backing::{row.get('report_input_id')}",
                "chart_asset_not_backed_by_metric_aware_mart",
                "medium",
                "report_inputs",
                row.get("report_input_id"),
                f"source_dataset={source_dataset}",
                "Re-point the distribution chart asset to pay_service_horizon_curve_view before report-ready promotion.",
                canonical_status=row.get("governed_canonical_status") or "staged_not_governed",
            )
        if row.get("default_pay_metric") in (None, ""):
            add_issue(
                f"dq::report_metric::{row.get('report_input_id')}",
                "midpoint_used_without_metric_label",
                "high",
                "report_inputs",
                row.get("report_input_id"),
                "Report input has no default_pay_metric.",
                "Declare a pay metric before using the report input.",
                canonical_status=row.get("governed_canonical_status") or "staged_not_governed",
            )
        if row.get("asset_status") != "report_ready":
            add_issue(
                f"dq::report_input::{row.get('report_input_id')}",
                "report_input_not_report_ready",
                "medium",
                "report_inputs",
                row.get("report_input_id"),
                row.get("quality_flags"),
                "Resolve quality flags and promote the report input asset when reviewed.",
                canonical_status=row.get("governed_canonical_status") or "staged_not_governed",
            )

    for row in spatial_reference_rows:
        if row.get("value_status") == "source_unclear":
            add_issue(
                f"dq::spatial::{row.get('council_key')}",
                "spatial_reference_gap",
                "low",
                "spatial_reference",
                row.get("council_key"),
                "One or more spatial reference fields are missing.",
                "Review council master spatial fields before relying on map outputs.",
                council_key=row.get("council_key"),
                canonical_status=row.get("governed_canonical_status") or "canonical_reference_only",
            )

    for row in entitlement_items:
        if row.get("governed_canonical_status") != "governed":
            add_issue(
                f"dq::entitlement::{row.get('entitlement_item_id')}",
                "entitlement_not_governed",
                "medium",
                "entitlement_items",
                row.get("entitlement_item_id"),
                row.get("value_status"),
                "Promote reviewed entitlement evidence before treating this as an entitlement fact.",
                canonical_status=row.get("governed_canonical_status") or "staged_not_governed",
            )

    return rows


def append_status_details(lines: list[str], output_dir: Path, statuses: list[MartStatus], heading: str) -> None:
    lines.extend(["", f"## {heading}", ""])
    for status in statuses:
        payload = read_json(output_dir / f"{status.mart_id}_status.json", {})
        inputs = payload.get("inputs") or payload.get("inputs_checked") or []
        blockers = payload.get("blocked_reasons") or payload.get("blockers") or payload.get("caveats") or []
        next_actions = payload.get("recommended_next_actions") or payload.get("recommended_next_action") or []
        if isinstance(next_actions, str):
            next_actions = [next_actions]
        lines.extend(
            [
                f"### `{status.mart_id}`",
                f"- Status: `{payload.get('status', status.status)}`",
                f"- Row count: `{payload.get('row_count', status.row_count)}`",
                f"- Input sources: {', '.join(f'`{item}`' for item in inputs) if inputs else '`none recorded`'}",
                f"- Governance status coverage: `{json.dumps(payload.get('governance_status_coverage') or {}, sort_keys=True)}`",
                f"- Key missing fields: `{json.dumps(payload.get('key_missing_fields') or {}, sort_keys=True)}`",
                f"- Blockers/caveats: {', '.join(str(item) for item in blockers) if blockers else 'none recorded'}",
                f"- Recommended next action: {'; '.join(str(item) for item in next_actions) if next_actions else 'none recorded'}",
                "",
            ]
        )


def write_summary(output_dir: Path, statuses: list[MartStatus], generated_at: str) -> None:
    lines = [
        "# Datamart Build Summary",
        "",
        f"Generated: `{generated_at}`",
        "",
        "| Mart | Status | Rows | Outputs |",
        "| --- | --- | ---: | --- |",
    ]
    for status in statuses:
        outputs = ", ".join(status.output_files)
        lines.append(f"| `{status.mart_id}` | {status.status} | {status.row_count} | {outputs} |")
    blocked = [status for status in statuses if status.status == "blocked"]
    if blocked:
        lines.extend(["", "## Blocked Marts", ""])
        for status in blocked:
            lines.append(f"### `{status.mart_id}`")
            for reason in status.reasons:
                lines.append(f"- Reason: {reason}")
            for action in status.next_actions:
                lines.append(f"- Next action: {action}")
            lines.append("")
    append_status_details(lines, output_dir, statuses, "Per-Mart Build Details")
    lines.extend(
        [
            "## Safety Notes",
            "",
            "- Datamarts use `data/governed_canonical/` as their stable upstream layer.",
            "- Missing values remain blockers or unknowns; they are not converted to absence.",
            "- Evidence snippets are not synthesized by this build.",
        ]
    )
    (output_dir / "datamart_build_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_governed_summary(output_dir: Path, statuses: list[MartStatus], generated_at: str) -> None:
    lines = [
        "# Governed Canonical Build Summary",
        "",
        f"Generated: `{generated_at}`",
        "",
        "| Dataset | Status | Rows | Outputs |",
        "| --- | --- | ---: | --- |",
    ]
    for status in statuses:
        outputs = ", ".join(status.output_files)
        lines.append(f"| `{status.mart_id}` | {status.status} | {status.row_count} | {outputs} |")
    append_status_details(lines, output_dir, statuses, "Per-Dataset Build Details")
    lines.extend(
        [
            "",
            "## Safety Notes",
            "",
            "- Governed pay and uplift rows come only from `sections.uplifts` records with governed timestamps.",
            "- Canonical/reference-only rows carry explicit `governed_canonical_status` values.",
            "- Missing values carry value/status fields and are not treated as absence.",
        ]
    )
    (output_dir / "governed_canonical_build_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_datamarts(
    root: Path,
    output_dir: Path | None = None,
    generated_at: str | None = None,
    governed_output_dir: Path | None = None,
) -> list[MartStatus]:
    root = root.resolve()
    output_dir = output_dir or root / "data" / "datamarts"
    governed_output_dir = governed_output_dir or root / "data" / "governed_canonical"
    generated_at = generated_at or now_iso()
    output_dir.mkdir(parents=True, exist_ok=True)
    governed_output_dir.mkdir(parents=True, exist_ok=True)

    council_rows = read_csv(root / "data" / "reference" / "victorian-council-master.csv")
    candidate_rows = read_json(
        root / "data" / "bronze" / "phase1_source_build" / "candidate_agreements" / "candidate_agreements.json",
        [],
    )
    if not isinstance(candidate_rows, list):
        candidate_rows = []
    cohort_reference = read_yaml(root / "data" / "reference" / "cohorts" / "cohort-nomenclature.yaml", {})
    if not isinstance(cohort_reference, dict):
        cohort_reference = {}
    source_register_rows = read_csv(root / "registers" / "source-document-register.csv")
    source_docs = source_docs_by_ae(source_register_rows)
    candidates_by_ae = candidate_rows_by_ae(candidate_rows)
    candidate_counts = candidate_counts_by_council(candidate_rows)
    records = load_canonical_records(root)
    index = council_indexes(council_rows)
    annotate_councils(records, candidates_by_ae, index, council_rows)

    governed_statuses: list[MartStatus] = []
    statuses: list[MartStatus] = []

    council_agreement_rows = build_council_agreement_rows(records, candidates_by_ae, source_docs)
    if council_agreement_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "council_agreements",
                council_agreement_rows,
                COUNCIL_AGREEMENT_FIELDS,
                generated_at,
                inputs=["canonical/*.yaml", "data/reference/victorian-council-master.csv", "source-document-register.csv"],
                caveats=["Council identity is canonical/reference lineage, not extracted report truth."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "council_agreements",
                generated_at,
                reasons=["No canonical agreement files were found."],
                next_actions=["Restore or create canonical agreement records."],
                inputs_checked=["canonical/*.yaml"],
            )
        )

    governed_pay_rows = build_governed_pay_rows(records)
    if governed_pay_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "pay_rows",
                governed_pay_rows,
                GOVERNED_PAY_ROW_FIELDS,
                generated_at,
                inputs=["canonical/*.yaml::sections.uplifts.data.periods[].pay_table"],
                caveats=["Unpromoted sections.pay_tables rows are excluded."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "pay_rows",
                generated_at,
                reasons=["No governed pay table rows with pay_table_governed_at were found in sections.uplifts."],
                next_actions=["Promote reviewed pay table periods before building downstream pay marts."],
                inputs_checked=["canonical/*.yaml::sections.uplifts"],
            )
        )

    governed_uplift_rows = build_governed_uplift_rows(records)
    if governed_uplift_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "uplift_rules",
                governed_uplift_rows,
                GOVERNED_UPLIFT_RULE_FIELDS,
                generated_at,
                inputs=["canonical/*.yaml::sections.uplifts.data.periods[].uplift_rule"],
                caveats=["Accepted suggestions are used only for lineage fields once a governed uplift rule exists."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "uplift_rules",
                generated_at,
                reasons=["No governed uplift rules with uplift_rule_governed_at were found in sections.uplifts."],
                next_actions=["Promote reviewed uplift rules before building downstream uplift marts."],
                inputs_checked=["canonical/*.yaml::sections.uplifts"],
            )
        )

    governed_end_of_band_rows = build_governed_end_of_band_dollar_rows(records, root)
    if governed_end_of_band_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "end_of_band_dollars",
                governed_end_of_band_rows,
                GOVERNED_END_OF_BAND_DOLLAR_FIELDS,
                generated_at,
                inputs=[
                    "canonical/*.yaml::sections.uplifts.data.periods[].pay_table",
                    "cache/*/full_text.txt",
                ],
                caveats=[
                    "Dollar rows are derived from cached agreement text and governed band periods; excluded one-off, grandfathered, leave-only, recognition-only, and built-into-scale candidates are not emitted.",
                    "Percentage and midpoint formula amounts are calculated from governed weekly rates or calculated EOB rate-table evidence where possible.",
                ],
                status="partial" if any(row.get("calculation_status") != "explicit_clause_amount" for row in governed_end_of_band_rows) else "built",
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "end_of_band_dollars",
                generated_at,
                reasons=["No in-scope non-grandfathered cash end-of-band rows were derived from governed pay periods and cached agreement text."],
                next_actions=["Confirm full_text.txt exists for governed agreements and review the end-of-band search candidates if this is unexpected."],
                inputs_checked=[
                    "canonical/*.yaml::sections.uplifts.data.periods[].pay_table",
                    "cache/*/full_text.txt",
                ],
            )
        )

    governed_evidence_refs = build_governed_evidence_refs(governed_pay_rows, governed_uplift_rows, source_docs)
    if governed_evidence_refs:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "evidence_refs",
                governed_evidence_refs,
                GOVERNED_EVIDENCE_REF_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/pay_rows", "data/governed_canonical/uplift_rules", "source-document-register.csv"],
                caveats=["Evidence snippets are not synthesized; missing page/clause refs remain lineage gaps."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "evidence_refs",
                generated_at,
                reasons=["No governed pay or uplift rows were available to trace."],
                next_actions=["Populate governed pay_rows or uplift_rules first."],
                inputs_checked=["data/governed_canonical/pay_rows", "data/governed_canonical/uplift_rules"],
            )
        )

    governed_readiness_rows = build_governed_readiness_rows(
        council_agreement_rows,
        governed_pay_rows,
        governed_uplift_rows,
    )
    if governed_readiness_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "readiness_status",
                governed_readiness_rows,
                GOVERNED_READINESS_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/council_agreements", "pay_rows", "uplift_rules"],
                caveats=["Readiness rows are workflow status inputs, not analytical facts."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "readiness_status",
                generated_at,
                reasons=["No council agreement canonical rows were available to assess."],
                next_actions=["Populate council_agreements first."],
                inputs_checked=["data/governed_canonical/council_agreements"],
            )
        )

    governed_cohort_rows = build_governed_cohort_memberships(council_rows, governed_pay_rows, cohort_reference)
    if governed_cohort_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "cohort_memberships",
                governed_cohort_rows,
                GOVERNED_COHORT_MEMBERSHIP_FIELDS,
                generated_at,
                inputs=["data/reference/victorian-council-master.csv", "data/reference/cohorts/cohort-nomenclature.yaml", "data/governed_canonical/pay_rows.csv"],
                caveats=["Reference cohorts are canonical/reference only; benchmark-lane membership is derived from governed pay-row presence."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "cohort_memberships",
                generated_at,
                reasons=["No council reference rows or governed pay-row cohort signals were available."],
                next_actions=["Restore council master data and governed pay_rows."],
                inputs_checked=["data/reference/victorian-council-master.csv", "data/governed_canonical/pay_rows.csv"],
            )
        )

    governed_source_document_rows = build_governed_source_documents(source_register_rows)
    if governed_source_document_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "source_documents",
                governed_source_document_rows,
                GOVERNED_SOURCE_DOCUMENT_FIELDS,
                generated_at,
                inputs=["registers/source-document-register.csv"],
                caveats=["Frozen documents are treated as governed source-evidence references; non-frozen rows remain explicit staged/candidate states."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "source_documents",
                generated_at,
                reasons=["The source document register is missing or empty."],
                next_actions=["Restore or rebuild registers/source-document-register.csv."],
                inputs_checked=["registers/source-document-register.csv"],
            )
        )

    governed_report_input_rows = build_governed_report_inputs(root)
    if governed_report_input_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "report_inputs",
                governed_report_input_rows,
                GOVERNED_REPORT_INPUT_FIELDS,
                generated_at,
                inputs=["data/analysis/distribution-point-analysis.asset.json"],
                caveats=["Draft report assets remain staged and are not promoted to report-ready truth."],
                status="partial" if any(row.get("governed_canonical_status") != "governed" for row in governed_report_input_rows) else "built",
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "report_inputs",
                generated_at,
                reasons=["No report input asset manifests were found."],
                next_actions=["Materialize report asset manifests before building product-input marts."],
                inputs_checked=["data/analysis/*.asset.json"],
            )
        )

    governed_spatial_reference_rows = build_governed_spatial_reference(council_rows)
    if governed_spatial_reference_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "spatial_reference",
                governed_spatial_reference_rows,
                GOVERNED_SPATIAL_REFERENCE_FIELDS,
                generated_at,
                inputs=["data/reference/victorian-council-master.csv"],
                caveats=["Spatial fields are controlled reference data, not EBA facts."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "spatial_reference",
                generated_at,
                reasons=["Council master reference file is missing or empty."],
                next_actions=["Rebuild or restore data/reference/victorian-council-master.csv."],
                inputs_checked=["data/reference/victorian-council-master.csv"],
            )
        )

    governed_entitlement_item_rows = build_governed_entitlement_items(root)
    if governed_entitlement_item_rows:
        entitlement_item_inputs = ["wiki/artifacts/downstream-analysis-exemplars/ballarat-entitlement-benchmark-exemplar.json"]
        if (root / ENTITLEMENT_DEFINITION_OVERRIDES_PATH).exists():
            entitlement_item_inputs.append(ENTITLEMENT_DEFINITION_OVERRIDES_PATH.as_posix())
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "entitlement_items",
                governed_entitlement_item_rows,
                GOVERNED_ENTITLEMENT_ITEM_FIELDS,
                generated_at,
                inputs=entitlement_item_inputs,
                caveats=[
                    "Entitlement items are staged taxonomy/prototype rows, not reviewed entitlement facts.",
                    "Definitions may use curated taxonomy wording layered over the source exemplar.",
                ],
                status="partial",
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "entitlement_items",
                generated_at,
                reasons=["No reviewed/governed entitlement item source was found."],
                next_actions=["Promote reviewed entitlement evidence before populating entitlement_items as governed facts."],
                inputs_checked=["canonical/*.yaml::sections.clauses", "wiki/artifacts/downstream-analysis-exemplars"],
            )
        )

    governed_rate_cap_reference_rows = build_governed_rate_cap_reference(root, council_rows)
    if governed_rate_cap_reference_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "rate_cap_reference",
                governed_rate_cap_reference_rows,
                GOVERNED_RATE_CAP_REFERENCE_FIELDS,
                generated_at,
                inputs=["src/benchmarking_data_factory/uplift_rules/external/rate-cap/*.csv"],
                caveats=["External rate-cap references are public/reference context, not governed EBA terms."],
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "rate_cap_reference",
                generated_at,
                reasons=["No local rate-cap reference rows were available."],
                next_actions=["Restore the rate-cap external reference CSVs or capture a fresh public source with provenance."],
                inputs_checked=["src/benchmarking_data_factory/uplift_rules/external/rate-cap/*.csv"],
            )
        )

    governed_benchmark_question_rows = build_governed_benchmark_questions(root)
    if governed_benchmark_question_rows:
        governed_statuses.append(
            write_governed_rows(
                governed_output_dir,
                "benchmark_questions",
                governed_benchmark_question_rows,
                GOVERNED_BENCHMARK_QUESTION_FIELDS,
                generated_at,
                inputs=["wiki/questions/*.json"],
                caveats=["Questions are staged strategy inputs and require review/binding before report use."],
                status="partial",
            )
        )
    else:
        governed_statuses.append(
            write_governed_blocked(
                governed_output_dir,
                "benchmark_questions",
                generated_at,
                reasons=["No benchmark question artifacts were found."],
                next_actions=["Create reviewed benchmark questions or bind wiki questions into a governed question set."],
                inputs_checked=["wiki/questions/*.json"],
            )
        )

    write_governed_summary(governed_output_dir, governed_statuses, generated_at)

    council_profile_rows = build_council_profile_rows(council_rows, council_agreement_rows, candidate_counts)
    if council_profile_rows:
        statuses.append(
            write_rows(
                output_dir,
                "council_profile_mart",
                council_profile_rows,
                COUNCIL_PROFILE_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/council_agreements.csv", "data/reference/victorian-council-master.csv"],
                caveats=["Source lineage status is current-workspace coverage, not reviewed absence."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "council_profile_mart",
                generated_at,
                reasons=["Council master reference file is missing or empty."],
                next_actions=["Rebuild or restore data/reference/victorian-council-master.csv."],
                inputs_checked=["data/reference/victorian-council-master.csv"],
            )
        )

    pay_rows = build_pay_position_rows(governed_pay_rows)
    if pay_rows:
        statuses.append(
            write_rows(
                output_dir,
                "pay_position_mart",
                pay_rows,
                PAY_POSITION_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/pay_rows.csv"],
                caveats=["Rows without governed rate values carry blocked value_status; no conversion is performed here."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "pay_position_mart",
                generated_at,
                reasons=["No governed pay table rows with pay_table_governed_at were found in sections.uplifts."],
                next_actions=["Promote reviewed pay tables into governed uplift periods before building this mart."],
                inputs_checked=["canonical/*.yaml::sections.uplifts"],
            )
        )

    uplift_rows = build_uplift_timing_rows(governed_uplift_rows)
    if uplift_rows:
        statuses.append(
            write_rows(
                output_dir,
                "uplift_timing_mart",
                uplift_rows,
                UPLIFT_TIMING_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/uplift_rules.csv"],
                caveats=["Accepted uplift suggestions are used only for lineage fields when the governed rule exists."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "uplift_timing_mart",
                generated_at,
                reasons=["No governed uplift rules with uplift_rule_governed_at were found in sections.uplifts."],
                next_actions=["Promote reviewed uplift rules into governed uplift periods before building this mart."],
                inputs_checked=["canonical/*.yaml::sections.uplifts"],
            )
        )

    cohort_rows = build_cohort_comparison_rows(governed_cohort_rows)
    if cohort_rows:
        statuses.append(
            write_rows(
                output_dir,
                "cohort_comparison_mart",
                cohort_rows,
                COHORT_COMPARISON_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/cohort_memberships.csv"],
                caveats=["Blank cohort fields are omitted as unknown, not treated as exclusion."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "cohort_comparison_mart",
                generated_at,
                reasons=["No council reference cohort fields or governed pay cohort memberships were available."],
                next_actions=["Restore council master reference data and governed pay rows."],
                inputs_checked=["data/reference/victorian-council-master.csv", "pay_position_mart"],
            )
        )

    report_rows = build_report_readiness_rows(governed_readiness_rows)
    if report_rows:
        statuses.append(
            write_rows(
                output_dir,
                "report_readiness_mart",
                report_rows,
                REPORT_READINESS_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/readiness_status.csv"],
                caveats=["Readiness statuses are workflow controls, not analytical facts."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "report_readiness_mart",
                generated_at,
                reasons=["No canonical agreements were found to assess."],
                next_actions=["Restore or create canonical agreement records."],
                inputs_checked=["canonical/*.yaml"],
            )
        )

    evidence_rows = build_evidence_trace_rows(governed_evidence_refs)
    if evidence_rows:
        statuses.append(
            write_rows(
                output_dir,
                "evidence_trace_mart",
                evidence_rows,
                EVIDENCE_TRACE_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/evidence_refs.csv"],
                caveats=["Evidence snippets are not materialized by this builder."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "evidence_trace_mart",
                generated_at,
                reasons=["No governed pay or uplift rows were available to trace."],
                next_actions=["Populate governed pay or uplift marts first."],
                inputs_checked=["pay_position_mart", "uplift_timing_mart"],
            )
        )

    pay_rate_point_rows = build_pay_rate_point_rows(governed_pay_rows)
    if pay_rate_point_rows:
        statuses.append(
            write_rows(
                output_dir,
                "pay_rate_point_mart",
                pay_rate_point_rows,
                PAY_RATE_POINT_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/pay_rows.csv"],
                caveats=["Range roles are resolved from governed pay points; ambiguous groupings remain blocked."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "pay_rate_point_mart",
                generated_at,
                reasons=["No governed pay rows were available for pay point role assignment."],
                next_actions=["Populate governed pay_rows first."],
                inputs_checked=["data/governed_canonical/pay_rows.csv"],
            )
        )

    pay_range_summary_rows = build_pay_range_summary_rows(pay_rate_point_rows)
    if pay_range_summary_rows:
        statuses.append(
            write_rows(
                output_dir,
                "pay_range_summary_mart",
                pay_range_summary_rows,
                PAY_RANGE_SUMMARY_FIELDS,
                generated_at,
                inputs=["data/datamarts/pay_rate_point_mart.csv"],
                caveats=["Midpoint is explicitly range_midpoint_rate and is not the step mean."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "pay_range_summary_mart",
                generated_at,
                reasons=["No pay_rate_point_mart rows were available."],
                next_actions=["Build pay_rate_point_mart first."],
                inputs_checked=["data/datamarts/pay_rate_point_mart.csv"],
            )
        )

    pay_progression_rows = build_pay_progression_service_year_rows(pay_range_summary_rows, pay_rate_point_rows)
    if pay_progression_rows:
        statuses.append(
            write_rows(
                output_dir,
                "pay_progression_service_year_mart",
                pay_progression_rows,
                PAY_PROGRESSION_SERVICE_YEAR_FIELDS,
                generated_at,
                inputs=["data/datamarts/pay_range_summary_mart.csv", "data/datamarts/pay_rate_point_mart.csv"],
                caveats=["Service-horizon rows use governed rules when present; otherwise level-order horizon estimates are caveated and not report-ready by default."],
                status="partial" if any(row.get("calculation_status") == "calculated_from_level_ordinal_estimate" for row in pay_progression_rows) else "built",
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "pay_progression_service_year_mart",
                generated_at,
                reasons=["No pay ranges were available for service-horizon modelling."],
                next_actions=["Build pay_range_summary_mart first."],
                inputs_checked=["data/datamarts/pay_range_summary_mart.csv"],
            )
        )

    pay_distribution_rows = build_pay_distribution_point_rows(
        pay_range_summary_rows,
        pay_progression_rows,
        governed_cohort_rows,
    )
    if pay_distribution_rows:
        statuses.append(
            write_rows(
                output_dir,
                "pay_distribution_point_mart",
                pay_distribution_rows,
                PAY_DISTRIBUTION_POINT_FIELDS,
                generated_at,
                inputs=[
                    "data/datamarts/pay_range_summary_mart.csv",
                    "data/datamarts/pay_progression_service_year_mart.csv",
                    "data/governed_canonical/cohort_memberships.csv",
                ],
                caveats=[
                    "Every row declares comparison_metric; estimated service-horizon rows carry caveated report readiness.",
                    "Rows are emitted for all_governed and for each governed/reference cohort membership attached to the council.",
                ],
                status="partial" if any(row.get("report_ready_status") != "ready" for row in pay_distribution_rows) else "built",
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "pay_distribution_point_mart",
                generated_at,
                reasons=["No pay range or service-horizon rows were available for metric-aware distribution points."],
                next_actions=["Build pay_range_summary_mart and pay_progression_service_year_mart first."],
                inputs_checked=["data/datamarts/pay_range_summary_mart.csv", "data/datamarts/pay_progression_service_year_mart.csv"],
            )
        )

    pay_curve_rows = build_pay_service_horizon_curve_view_rows(pay_distribution_rows)
    if pay_curve_rows:
        pay_curve_sqlite = write_curve_view_sqlite(output_dir, pay_curve_rows, generated_at)
        statuses.append(
            write_rows(
                output_dir,
                "pay_service_horizon_curve_view",
                pay_curve_rows,
                PAY_SERVICE_HORIZON_CURVE_VIEW_FIELDS,
                generated_at,
                inputs=["data/datamarts/pay_distribution_point_mart.csv"],
                caveats=[
                    "Curve/envelope rows pool observations only from the selected service_horizon_window.",
                    "weighting_method=observation_weighted in this first visual-serving implementation.",
                    "pay_service_horizon_curve_view.sqlite is the indexed operational read path for dynamic curve cohort selection.",
                ],
                status="partial" if any(row.get("report_ready_status") != "ready" for row in pay_curve_rows) else "built",
                extra_output_files=[pay_curve_sqlite.name],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "pay_service_horizon_curve_view",
                generated_at,
                reasons=["No pay_distribution_point_mart rows were available for service-horizon curve windows."],
                next_actions=["Build pay_distribution_point_mart first."],
                inputs_checked=["data/datamarts/pay_distribution_point_mart.csv"],
            )
        )

    entitlement_rows = build_entitlement_summary_rows(governed_entitlement_item_rows)
    if entitlement_rows:
        statuses.append(
            write_rows(
                output_dir,
                "entitlement_summary_mart",
                entitlement_rows,
                ENTITLEMENT_SUMMARY_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/entitlement_items.csv"],
                caveats=["Rows are prototype/staged taxonomy only and must not be interpreted as governed entitlement presence or absence."],
                status="partial",
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "entitlement_summary_mart",
                generated_at,
                reasons=[
                    "No reviewed/governed entitlement fact model is present in canonical records.",
                    "Current wiki artifacts are learning/proposed evidence, not governed entitlement truth.",
                ],
                next_actions=[
                    "Define a governed entitlement fact schema with explicit presence/absence review state.",
                    "Promote reviewed entitlement evidence before populating this mart.",
                ],
                inputs_checked=["canonical/*.yaml::sections.clauses", "wiki/**"],
            )
        )

    spatial_rows = build_spatial_context_rows(governed_spatial_reference_rows)
    if spatial_rows:
        statuses.append(
            write_rows(
                output_dir,
                "spatial_context_mart",
                spatial_rows,
                SPATIAL_CONTEXT_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/spatial_reference.csv"],
                caveats=["Rows with missing spatial reference fields carry blocked row-level status."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "spatial_context_mart",
                generated_at,
                reasons=["Council master reference file is missing or empty."],
                next_actions=["Rebuild or restore council master reference data."],
                inputs_checked=["data/reference/victorian-council-master.csv"],
            )
        )

    rate_cap_rows = build_rate_cap_context_rows(governed_rate_cap_reference_rows)
    if rate_cap_rows:
        statuses.append(
            write_rows(
                output_dir,
                "rate_cap_context_mart",
                rate_cap_rows,
                RATE_CAP_CONTEXT_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/rate_cap_reference.csv"],
                caveats=["Rate-cap context is external/public reference context and is not an EBA uplift term."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "rate_cap_context_mart",
                generated_at,
                reasons=["No rate-cap reference rows were available."],
                next_actions=["Restore or refresh rate-cap reference data with provenance."],
                inputs_checked=["data/governed_canonical/rate_cap_reference.csv"],
            )
        )

    agreement_lineage_rows = build_agreement_lineage_rows(council_agreement_rows)
    if agreement_lineage_rows:
        statuses.append(
            write_rows(
                output_dir,
                "agreement_lineage_mart",
                agreement_lineage_rows,
                AGREEMENT_LINEAGE_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/council_agreements.csv"],
                caveats=["Lineage fields expose candidate and canonical status; they do not resolve unknown evidence absence."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "agreement_lineage_mart",
                generated_at,
                reasons=["No council_agreements canonical rows were available."],
                next_actions=["Populate council_agreements first."],
                inputs_checked=["data/governed_canonical/council_agreements.csv"],
            )
        )

    temporal_pay_rows = build_temporal_pay_movement_rows(pay_distribution_rows)
    if temporal_pay_rows:
        statuses.append(
            write_rows(
                output_dir,
                "temporal_pay_movement_mart",
                temporal_pay_rows,
                TEMPORAL_PAY_MOVEMENT_FIELDS,
                generated_at,
                inputs=["data/datamarts/pay_distribution_point_mart.csv"],
                caveats=["Movements declare comparison_metric and are calculated only across metric-aware comparable rows."],
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "temporal_pay_movement_mart",
                generated_at,
                reasons=["No comparable sequential governed pay rows with numeric values and effective dates were available."],
                next_actions=["Build metric-aware pay_distribution_point_mart rows across multiple effective periods."],
                inputs_checked=["data/datamarts/pay_distribution_point_mart.csv"],
            )
        )

    benchmark_question_rows = build_benchmark_question_rows(governed_benchmark_question_rows)
    if benchmark_question_rows:
        statuses.append(
            write_rows(
                output_dir,
                "benchmark_question_mart",
                benchmark_question_rows,
                BENCHMARK_QUESTION_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/benchmark_questions.csv"],
                caveats=["Questions are staged strategy inputs; downstream products must bind them to governed datasets before use."],
                status="partial",
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "benchmark_question_mart",
                generated_at,
                reasons=["No benchmark question canonical rows were available."],
                next_actions=["Create or promote benchmark question artifacts."],
                inputs_checked=["data/governed_canonical/benchmark_questions.csv"],
            )
        )

    report_product_input_rows = build_report_product_input_rows(governed_report_input_rows)
    if report_product_input_rows:
        statuses.append(
            write_rows(
                output_dir,
                "report_product_input_mart",
                report_product_input_rows,
                REPORT_PRODUCT_INPUT_FIELDS,
                generated_at,
                inputs=["data/governed_canonical/report_inputs.csv"],
                caveats=["Draft assets remain visible with draft_not_report_ready status."],
                status="partial" if any(row.get("report_input_status") != "report_ready" for row in report_product_input_rows) else "built",
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "report_product_input_mart",
                generated_at,
                reasons=["No report_inputs canonical rows were available."],
                next_actions=["Materialize report input asset manifests."],
                inputs_checked=["data/governed_canonical/report_inputs.csv"],
            )
        )

    data_quality_issue_rows = build_data_quality_issue_rows(
        governed_readiness_rows,
        governed_pay_rows,
        governed_evidence_refs,
        governed_report_input_rows,
        governed_spatial_reference_rows,
        governed_entitlement_item_rows,
        pay_rate_point_rows,
        pay_progression_rows,
        pay_distribution_rows,
    )
    if data_quality_issue_rows:
        statuses.append(
            write_rows(
                output_dir,
                "data_quality_issue_mart",
                data_quality_issue_rows,
                DATA_QUALITY_ISSUE_FIELDS,
                generated_at,
                inputs=[
                    "data/governed_canonical/readiness_status.csv",
                    "data/governed_canonical/pay_rows.csv",
                    "data/governed_canonical/evidence_refs.csv",
                    "data/governed_canonical/report_inputs.csv",
                    "data/governed_canonical/spatial_reference.csv",
                    "data/governed_canonical/entitlement_items.csv",
                    "data/datamarts/pay_rate_point_mart.csv",
                    "data/datamarts/pay_progression_service_year_mart.csv",
                    "data/datamarts/pay_distribution_point_mart.csv",
                ],
                caveats=["Issues are generated as review work queues and should not be treated as source facts."],
                status="partial",
            )
        )
    else:
        statuses.append(
            write_blocked(
                output_dir,
                "data_quality_issue_mart",
                generated_at,
                reasons=["No data-quality issues were generated from current canonical inputs."],
                next_actions=["Review status coverage if this seems unexpected; empty issues may mean no blockers or missing inputs."],
                inputs_checked=["data/governed_canonical/*.csv"],
            )
        )

    write_summary(output_dir, statuses, generated_at)
    return governed_statuses + statuses


def main() -> None:
    parser = argparse.ArgumentParser(description="Build initial governed datamart suite.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--governed-output-dir", type=Path, default=None)
    args = parser.parse_args()
    statuses = build_datamarts(args.root, args.output_dir, governed_output_dir=args.governed_output_dir)
    for status in statuses:
        print(f"{status.mart_id}: {status.status} ({status.row_count} rows)")


if __name__ == "__main__":
    main()
