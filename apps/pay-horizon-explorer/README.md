# Governed Midpoint Distribution

This app is now a V1-style midpoint distribution replica backed by governed datamart outputs.

It intentionally shows one metric universe only:

- `service_horizon_window_id = range_midpoint_only`
- `comparison_metric = range_midpoint_rate`
- source: `pay_service_horizon_curve_view` and the indexed `pay_service_horizon_curve_view.sqlite` companion

The service-horizon/Y1-Y6 work remains in the datamarts and API for later, but is hidden from this working chart.

## Controls

- Council
- Year
- Quarter
- Band
- Curve cohort, including human-friendly governed cohorts plus V1-style peer lenses such as Local 5, Local 12, LGV category, Regional Victoria, LGPRF group, and SEIFA peer band
- Comparator, using the same cohort menu and plotted with member dots, average, and low/high markers
- Basis: selected period, 4-period average, date-smoothed
- Range overlay: none, IQR, 1 SD

## Open

Run the workbench server, then open:

`http://127.0.0.1:8769/apps/pay-horizon-explorer/`

Use the server port currently running for the workbench if it is not `8769`.
