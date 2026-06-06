# `report_product_input_mart` Contract

Purpose: expose report asset manifests and readiness for downstream product assembly.

Inputs:
- `data/governed_canonical/report_inputs.csv`

Grain: one report/product input asset.

Core fields:
- `report_product_input_id`
- `asset_id`
- `asset_type`
- `title`
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
- `report_input_status`
- `quality_flags`
- `recommended_next_action`
- `governed_canonical_status`

Safety Rules:
- Draft assets must remain visible as `draft_not_report_ready`.
- Quality flags must not be dropped by the mart.
- Report-ready status requires explicit promotion, not mere materialization.
