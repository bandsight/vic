# pay_rows Contract

Status: initial governed canonical contract.

## Intent

One row per governed pay row promoted into `sections.uplifts.data.periods[].pay_table`.

## Grain

`agreement_id + period_index + pay_row_index`

## Allowed Inputs

- `canonical/*.yaml::sections.uplifts.data.periods[].pay_table`
- Only records with `pay_table_governed_at`

## Key Fields

- `pay_row_id`
- `agreement_id`
- `council_key`
- `band`
- `level`
- `classification_key`
- `rate values`
- `effective_from`
- `to_date`
- `source_table_title`
- `source_clause`
- `source_pages`
- `source_file_path`
- `source_section_path`
- `governed_timestamp`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

## Safety Rules

- Do not read unpromoted `sections.pay_tables` rows into this dataset.
- Missing governed rate values are blocked, not zero and not absence.
- Do not convert annual/fortnightly/hourly values here unless conversion already exists in the governed source row.
