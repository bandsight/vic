# `pay_progression_service_year_mart` Contract

Purpose: Y0-Y6 service-horizon / tenure-normalised comparison values, either governed deterministic values or caveated level-order horizon estimates.

Inputs:
- `data/datamarts/pay_range_summary_mart.csv`
- `data/datamarts/pay_rate_point_mart.csv`

Grain: one service-horizon scenario per pay range.

Core fields:
- `progression_value_id`
- `range_group_id`
- `service_year_index`
- `service_month_index`
- `service_horizon_year`
- `service_horizon_month`
- `assumed_start_point_id`
- `resolved_pay_rate_point_id`
- `ordinal_position_resolved`
- `resolved_level_label`
- `weekly_rate_at_service_year`
- `resolved_value_mode`
- `capacity_reached`
- `capacity_reached_at_service_horizon_year`
- `capacity_carry_forward`
- `actual_step_count`
- `comparison_horizon_note`
- `progression_basis`
- `progression_rule_status`
- `calculation_method`
- `calculation_status`
- `blocker_reason`

Convention:
- `service_year_0` is entry/commencement.
- `service_year_1` maps to the first ordered governed point, commonly A, under the caveated service-horizon convention.
- `service_year_2` maps to the second ordered governed point, commonly B, when that actual point exists.
- Values carry forward from the capacity point after the final available governed level through year 6 unless governed progression logic says otherwise.

Service-horizon doctrine:
- `ordinal_position_resolved` is actual structure and must not exceed `actual_step_count`.
- `service_horizon_year` is a normalised comparison horizon and may exceed `actual_step_count`.
- A year-6 horizon for a three-step ladder resolves to the third actual point with `resolved_value_mode = capacity_carry_forward`.
- `resolved_level_label` must name the actual level used; it must not invent a Level 6.
- Governed progression rules outrank the level-order horizon estimate.

Safety Rules:
- Governed progression rules take precedence.
- Level-order service-horizon values are `calculated_from_level_ordinal_estimate` and are not silently governed truth.
- Competency, performance, appointment, reclassification, mixed, or unclear progression blocks deterministic service-horizon values unless reviewed logic exists.
- Capacity carry-forward must stay visible with `resolved_value_mode`, `capacity_carry_forward`, `actual_step_count`, and `comparison_horizon_note`.
