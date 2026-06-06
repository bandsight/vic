# `pay_rate_point_mart` Contract

Purpose: one governed pay point per row with explicit range role.

Inputs:
- `data/governed_canonical/pay_rows.csv`
- `registers/pay-structure-semantics.yaml`

Grain: one governed pay table point.

Core fields:
- `pay_rate_point_id`
- `source_pay_row_id`
- `agreement_id`
- `classification_family`
- `standard_band`
- `standard_level`
- `step_ordinal`
- `weekly_rate`
- `range_group_id`
- `range_role`
- `calculation_status`
- `blocker_reason`
- `governed_canonical_status`

Safety Rules:
- Do not create rates from missing values.
- Do not infer range roles across unrelated classification families.
- Ambiguous range grouping must remain visible as `blocked_ambiguous_range_grouping`.
- Singleton rows retain `range_role=singleton`.
