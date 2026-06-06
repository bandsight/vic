# `pay_service_horizon_curve_view` Contract

Purpose: visual-serving curve/envelope rows for the interactive distribution chart. This view consumes `pay_distribution_point_mart`; it does not replace the metric-aware analytical mart.

Inputs:
- `data/datamarts/pay_distribution_point_mart.csv`
- Dynamic cohorts materialised into `pay_distribution_point_mart` from `data/governed_canonical/cohort_memberships.csv`

Grain: one service-horizon window per selected pay range, cohort, band, and effective period.

Dynamic cohort behaviour:
- `cohort_id` / `cohort_name` define the comparator curve/envelope cohort for that row.
- The selected council overlay is available for every council with metric-aware pay data for the band/period, even where the selected council is not a member of the chosen comparator cohort.
- `selected_council_included_in_curve_sample` states whether the selected council contributed to the comparator sample.
- The V2 explorer may load a second comparator cohort as a visual background/reference. That second background must be labelled with its own `cohort_name` and must not be described as the primary curve unless it is the selected curve cohort.

Operational companion store:
- `data/datamarts/pay_service_horizon_curve_view.sqlite`
- This SQLite file is generated from the same rows as the CSV/JSON view.
- It indexes `standard_band`, `effective_from`, `cohort_id`, `selected_council_id`, and `service_horizon_window_id` so the V2 explorer can switch curve cohorts and comparator cohorts without scanning the full JSON mart at runtime.
- The CSV/JSON files remain the audit and interchange contract. SQLite is the read-optimised companion, not a separate source of truth.
- The normal V2 cohort selector exposes only cohorts whose materialised comparator curve reaches `curve_council_count > 15` in at least one curve context. Smaller cohorts remain in the indexed store for audit/specialist use, but are not shown in the default curve/comparator dropdowns.

Core fields:
- `curve_id`
- `cohort_id`
- `cohort_name`
- `standard_band`
- `effective_from`
- `effective_to`
- `service_horizon_window_id`
- `service_horizon_window_label`
- `included_metric_points`
- `included_service_horizon_years`
- `curve_sample_count`
- `curve_council_count`
- `weighting_method`
- `curve_min`
- `curve_p25`
- `curve_median`
- `curve_p75`
- `curve_max`
- `density_points_json`
- `comparator_envelope_json`
- `horizon_envelope_json`
- `selected_council_points_json`
- `selected_council_id`
- `selected_council_name`
- `selected_range_group_id`
- `selected_council_included_in_curve_sample`
- `selected_council_min`
- `selected_council_max`
- `selected_council_position_summary`
- `chart_title`
- `caveat_status`
- `metric_caveats`
- `report_ready_status`
- `blocker_reason`

Window semantics:
- `entry_only`: entry only.
- `range_midpoint_only`: range midpoint only, preserving the legacy midpoint distribution as an explicit metric universe.
- `y3_only`: Year 3 service-horizon only.
- `capacity_only`: capacity only.
- `entry_to_y3`: entry plus Y1, Y2, and Y3.
- `y3_to_y6`: Y3, Y4, Y5, and Y6.
- `entry_to_y6`: entry plus Y1 through Y6, excluding capacity.
- `entry_to_capacity_profile`: entry plus Y1 through Y6 plus capacity deliberately.

Safety Rules:
- Dots and curve must come from the same `service_horizon_window`.
- `included_metric_points` is the metric universe for both the selected council overlay and comparator envelope.
- If a separate comparator background is displayed, it must be loaded from the same `service_horizon_window` and clearly labelled with its comparator cohort name.
- Service-window views must use `horizon_envelope_json` for the main visual profile so each selected point is compared with the same horizon point across the cohort. Do not draw a connected Y1-to-Y3 selected path as if it were travelling through one pooled percentile curve.
- `comparator_envelope_json` remains the pooled whole-window context for min/quartile/median/max across all observations in the selected window.
- `selected_council_included_in_curve_sample` states whether the selected council contributed to the comparator sample for the chosen cohort/window.
- First implementation uses `weighting_method = observation_weighted`.
- Capacity carry-forward points must remain labelled in `selected_council_points_json`.
- `entry_to_y6` must not include `capacity_rate`; capacity appears only in `capacity_only` or `entry_to_capacity_profile`.
- Chart titles must state band and `service_horizon_window_label`.
