# pay_position_mart Contract

Status: initial contract.

## Intent

One row per governed pay table classification row, preserving council, agreement, band, level, value, period, and source-governed record lineage.

## Grain

`agreement_id + period_index + pay_row_index`

## Allowed Inputs

- `data/governed_canonical/pay_rows.csv`

## Key Fields

- `pay_position_id`
- `council_key`
- `council_name`
- `agreement_id`
- `agreement_name`
- `band`
- `level`
- `classification_key`
- `classification_label`
- `governed_rate_value`
- `governed_rate_unit`
- `weekly_rate`
- `annual_rate`
- `fortnightly_rate`
- `hourly_rate`
- `effective_from`
- `to_date`
- `period_basis`
- `source_table_title`
- `source_clause`
- `source_pages`
- `governed_at`
- `review_governance_status`
- `source_governed_record_reference`
- `value_status`

## Safety Rules

- Do not read upstream `sections.pay_tables` as report-ready truth unless it has first been promoted into `data/governed_canonical/pay_rows`.
- Do not convert annual, fortnightly, or hourly rates in this mart unless a governed upstream value already did so.
- Missing rate values are `blocked_missing_governed_rate_value`, not zero and not reviewed absence.
