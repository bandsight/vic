# `pay_distribution_point_mart` Contract

Purpose: metric-aware distribution points for charts and reports.

Inputs:
- `data/datamarts/pay_range_summary_mart.csv`
- `data/datamarts/pay_progression_service_year_mart.csv`
- `data/governed_canonical/cohort_memberships.csv`

Grain: one selected comparison metric per pay range, with the full pay metric bundle also attached.

Each metric row is emitted for `all_governed` and for each governed/reference cohort membership attached to that council. Cohort-specific rows let the V2 explorer rebuild the distribution curve for council type, region, reference group, or benchmark-lane cohorts without deriving semantics in the frontend.

Core fields:
- `distribution_point_id`
- `range_group_id`
- `comparison_metric`
- `comparison_metric_label`
- `weekly_rate`
- `entry_weekly_rate`
- `range_midpoint_weekly_rate`
- `capacity_weekly_rate`
- `service_year_1_weekly_rate` through `service_year_6_weekly_rate`
- `service_horizon_year`
- `resolved_value_mode`
- `resolved_level_label`
- `actual_step_count`
- `capacity_carry_forward`
- `service_horizon_label`
- `metric_caveat`
- `metric_bundle_status`
- `metric_bundle_caveats`
- `cohort_id`
- `cohort_name`
- `cohort_median`
- `report_ready_status`
- `calculation_status`

Service-horizon semantics:
- Entry, midpoint, and capacity rows remain first-class non-horizon metrics.
- Service-horizon rows must expose whether the value is an exact actual level point or capacity carried forward.
- Labels must say service-horizon, tenure-normalised, or capacity carry-forward. They must not say Level 6 unless the resolved actual level is Level 6 and `actual_step_count >= 6`.
- `service_horizon_label` should distinguish examples such as "Year 6 service-horizon rate, capacity carried forward from Level C" and "Year 6 service-horizon rate, exact Level F point".

Safety Rules:
- Every row must declare `comparison_metric`.
- No generic pay `weekly_rate` is meaningful without `comparison_metric`.
- Estimated Y1-Y6 service-horizon values must retain caveats and report readiness status.
- Blocked metric rows remain visible or are counted in status JSON.
