# `report_inputs` Governed Canonical Contract

Purpose: stable manifest rows for report/product input assets.

Inputs:
- `data/analysis/*.asset.json`

Grain: one report asset manifest.

Required lineage/status fields:
- `report_input_id`
- `asset_id`
- `asset_type`
- `source_dataset`
- `source_dataset_version`
- `input_mart_version`
- `asset_status`
- `pay_metric_set`
- `default_pay_metric`
- `available_pay_metrics`
- `blocked_pay_metrics`
- `metric_caveats`
- `service_horizon_window_id`
- `service_horizon_window_label`
- `included_metric_points`
- `weighting_method`
- `curve_source`
- `selected_council_points_source`
- `quality_flags`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Draft assets remain `staged_not_governed`.
- Only explicitly report-ready or reviewed assets may be promoted beyond staged status.
- Quality flags must remain visible for downstream filtering.
