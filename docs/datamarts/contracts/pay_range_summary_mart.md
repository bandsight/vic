# `pay_range_summary_mart` Contract

Purpose: one row per agreement/classification range/effective period with explicit pay metrics.

Inputs:
- `data/datamarts/pay_rate_point_mart.csv`

Grain: one pay range group.

Core fields:
- `pay_range_id`
- `range_group_id`
- `entry_weekly_rate`
- `capacity_weekly_rate`
- `range_midpoint_weekly_rate`
- `step_mean_weekly_rate`
- `progression_spread_abs`
- `progression_spread_pct`
- `has_incremental_structure`
- `has_singleton_rate`
- `calculation_status`
- `blocker_reason`

Safety Rules:
- `range_midpoint_weekly_rate = (entry + capacity) / 2`.
- `step_mean_weekly_rate` is the mean of governed points and must not be labelled midpoint.
- Singleton ranges may set entry, capacity, and midpoint to the same rate.
- Blocked ranges remain in output with blocker reason.
