# Pay Structure Semantics v1 Audit

Status: audit note from the implementation pass.

## Findings

- `src/benchmarking_data_factory/workbench/analysis_distribution_points.py` calculates midpoint internally as `(min_rate + max_rate) / 2`, writes it to `midpoint_weekly_rate`, and also writes the generic `weekly_rate` as the midpoint. This is the main silent midpoint default.
- `src/benchmarking_data_factory/workbench/report_assets.py` described the distribution asset as weekly pay points with minimum, maximum, midpoint, and max-level values, but did not require a `comparison_metric`.
- `data/analysis/distribution-point-analysis.asset.json` was a draft chart manifest over `pay_tables`; it did not declare a pay metric set or metric-specific chart configuration.
- `pay_position_mart` exposed governed pay points but its name could be read as a comparison position without stating the metric. It is now preserved as a legacy/backwards-compatible raw governed point surface.
- `temporal_pay_movement_mart` previously moved raw governed row values by band/level. It now uses metric-aware distribution rows and declares `comparison_metric`.
- `report_product_input_mart` did not expose `pay_metric_set`, `default_pay_metric`, `available_pay_metrics`, `blocked_pay_metrics`, or `metric_caveats`.

## Backwards Compatibility

- Existing midpoint fields remain in legacy distribution assets.
- `pay_position_mart` still builds, but now marks itself as a legacy raw pay-point surface and points consumers to `pay_distribution_point_mart`.
- Midpoint remains as `range_midpoint_rate`; it is not deleted.

## Remaining Midpoint Assumption

The legacy API payload in `analysis_distribution_points.py` still materialises `weekly_rate` as midpoint for compatibility. The report manifest now labels this as `range_midpoint_rate`, and the governed datamart suite exposes metric-aware replacement outputs.
