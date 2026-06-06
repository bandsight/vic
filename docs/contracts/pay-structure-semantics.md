# Pay Structure Semantics v1.1

Status: active model contract.

## Purpose

Pay comparisons must declare the pay metric being compared. Pay is a structured curve, not one silent midpoint:

```text
entry point -> internal progression points -> service-horizon comparison values -> capacity point
```

Midpoint remains available only as `range_midpoint_rate`.

## Service-Horizon Doctrine

Service-horizon values exist to compare councils at common employment-value moments even when their internal pay ladders have different lengths.

The model separates:

- `ordinal_position`: the actual pay-table step or structural level.
- `service_horizon_year`: the normalised comparison horizon.

Actual pay-table step count is structural truth. A service horizon is a comparison lens. A council with three levels can still have a year-6 service-horizon value, but that value must resolve to the top governed level carried forward; it does not prove that the council has a sixth increment or Level 6.

Capacity carry-forward is valid for comparison only when it is labelled with `resolved_value_mode = capacity_carry_forward`, `capacity_carry_forward = true`, and the resolved actual level. Governed progression rules outrank level-order estimates wherever reviewed logic exists.

## Pay Metric Types

- `entry_rate`: lowest governed rate for a valid classification range at an effective date.
- `capacity_rate`: top governed rate for the same valid classification range.
- `range_midpoint_rate`: `(entry_rate + capacity_rate) / 2`.
- `step_mean_rate`: arithmetic mean of all governed points in the range.
- `service_year_0_rate`: commencement or entry service-horizon rate.
- `service_year_1_rate` through `service_year_6_rate`: service-horizon comparison rates. The compact metric names are retained for compatibility; report-facing labels should say service-horizon or tenure-normalised rate.
- `progression_spread_abs`: `capacity_rate - entry_rate`.
- `progression_spread_pct`: `(capacity_rate - entry_rate) / entry_rate`.
- `time_to_capacity`: duration to capacity when determinable.

## Service-Horizon Vocabulary

- `service_horizon_year`: the comparison year being requested, such as 1, 3, or 6.
- `service_horizon_window`: the selected set of metric points used to build a comparator curve/envelope.
- `service_horizon_rate`: the rate resolved for that horizon.
- `tenure_normalised_rate`: synonym for a service-horizon comparison rate.
- `resolved_pay_rate_point`: the actual governed pay point used for the value.
- `ordinal_position_resolved`: the actual structural position resolved, never a fake ordinal beyond `actual_step_count`.
- `resolved_level_label`: the actual level label, such as A, B, or C.
- `actual_step_count`: count of actual governed points in the range.
- `capacity_reached`: true once the horizon is at or beyond the capacity point.
- `capacity_carry_forward`: true when the horizon goes beyond the available ladder and the capacity rate is carried forward.

## Service-Horizon Windows

- `entry_only`: uses `entry_rate` only.
- `range_midpoint_only`: uses `range_midpoint_rate` only. This is the V2-compatible single-point equivalent of the legacy midpoint chart.
- `y3_only`: uses `service_year_3_rate` only.
- `capacity_only`: uses `capacity_rate` only.
- `entry_to_y3`: uses `entry_rate`, `service_year_1_rate`, `service_year_2_rate`, and `service_year_3_rate`.
- `y3_to_y6`: uses `service_year_3_rate`, `service_year_4_rate`, `service_year_5_rate`, and `service_year_6_rate`.
- `entry_to_y6`: uses `entry_rate` plus `service_year_1_rate` through `service_year_6_rate`. It does not include `capacity_rate`.
- `entry_to_capacity_profile`: uses `entry_rate`, selected service-horizon values, and `capacity_rate`. This must be labelled clearly because it includes capacity in addition to carried-forward horizon values.
- `custom_window`: uses user-selected metric points and must declare `included_metric_points`.

Dots and comparator curves must come from the same `service_horizon_window`. Do not overlay service-horizon dots on a stale midpoint distribution curve.

For multi-point service-window visuals, the main profile should be horizon-aligned rather than read as movement through one pooled percentile curve. Y1 selected council points should be compared with cohort Y1 envelope points, Y3 with cohort Y3, and so on. Whole-window pooled min/quartile/median/max can remain useful context, but it must not imply that a council travels from a lower pooled percentile to a higher pooled percentile merely by progressing through service horizons.

The selected council may be included in the cohort envelope when it belongs to the chosen cohort. If included, the visual layer should expose that inclusion explicitly rather than using a hidden leave-one-out comparison.

The chart may also show a separate comparator cohort as a secondary background/reference. That comparator background must be sourced from the same `service_horizon_window`, labelled with the comparator cohort name, and kept visually distinct from the primary curve cohort. It must not be used to relabel the primary curve.

## Range Roles

- `entry`: first/lowest point in a valid range.
- `internal_step`: point between entry and capacity.
- `capacity`: top/highest point in a valid range.
- `singleton`: one governed point; entry, capacity, and midpoint may equal the same rate, but role stays singleton.
- `unknown`: row exists but role is unresolved.
- `blocked`: row cannot be safely assigned.

## Progression Basis

- `annual_service_increment`
- `monthly_service_increment`
- `fixed_period_service_increment`
- `service_horizon_level_order_estimate`
- `competency_based`
- `performance_based`
- `appointment_based`
- `classification_reclassification`
- `mixed`
- `not_specified`
- `not_reviewed`
- `source_unclear`
- `not_applicable`

Only explicitly governed service-increment rules are deterministic. The `service_horizon_level_order_estimate` basis supports caveated Y1-Y6 modelling from ordered governed pay points; it is not a governed progression rule.

## Resolved Value Modes

- `exact_level_point`: the service horizon maps to an actual governed level.
- `capacity_carry_forward`: the service horizon exceeds the actual ladder and the capacity point is carried forward.
- `blocked_missing_progression_rule`
- `blocked_non_deterministic_progression`
- `blocked_ambiguous_range_grouping`
- `not_reviewed`

## Calculation Status

- `calculated_from_governed_points`
- `calculated_from_governed_progression_rule`
- `calculated_from_level_ordinal_estimate`
- `blocked_missing_pay_points`
- `blocked_ambiguous_range_grouping`
- `blocked_missing_progression_rule`
- `blocked_non_deterministic_progression`
- `blocked_source_unclear`
- `staged_not_governed`
- `not_reviewed`

## Narrative Rules

Allowed:

- "Band 5 year-3 service-horizon rate sits above the cohort median among governed comparable rows."
- "At the year-6 service horizon, this council's Band 5 value resolves to Level C capacity, carried forward after the range is exhausted."
- "Capacity rate is higher than the cohort median, while entry rate is below the cohort median."

Blocked:

- "Band 5 sits above market."
- "The council pays above market."
- "Council A has a Level 6 rate." unless the actual structure has at least six governed steps and the claim is metric-labelled.
- "After six years of service the employee will receive X." unless governed progression logic supports the statement.

Every report claim must state the pay metric or be flagged as too vague.

## Safety Rules

- Do not infer deterministic service-horizon outcomes as governed truth without governed progression logic.
- Estimated Y1-Y6 values must carry `calculated_from_level_ordinal_estimate`.
- Do not create fake ordinal positions beyond `actual_step_count`.
- Capacity carry-forward must expose `resolved_value_mode`, `capacity_carry_forward`, and `resolved_level_label`.
- Distribution chart curves must declare `service_horizon_window`, `included_metric_points`, and `weighting_method`.
- Do not confuse `range_midpoint_rate` with `step_mean_rate`.
- Do not group unrelated classification families.
- Missing pay values remain blockers/unknowns, not absence.
