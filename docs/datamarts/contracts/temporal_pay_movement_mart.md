# `temporal_pay_movement_mart` Contract

Purpose: derive pay movements across comparable governed pay rows.

Inputs:
- `data/governed_canonical/pay_rows.csv`

Grain: one adjacent movement between comparable governed pay rows.

Core fields:
- `pay_movement_id`
- `agreement_id`
- `council_key`
- `band`
- `level`
- `from_effective_date`
- `to_effective_date`
- `from_rate`
- `to_rate`
- `delta_value`
- `delta_pct`
- `governed_canonical_status`

Safety Rules:
- Movements may be calculated only from governed numeric pay values.
- Rows with missing rates, units, or effective dates are excluded and should surface through quality issues.
- Do not interpolate or invent missing periods.
