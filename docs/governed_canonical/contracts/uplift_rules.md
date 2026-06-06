# uplift_rules Contract

Status: initial governed canonical contract.

## Intent

One row per governed uplift rule promoted into `sections.uplifts.data.periods[].uplift_rule`.

## Grain

`agreement_id + period_index`

## Allowed Inputs

- `canonical/*.yaml::sections.uplifts.data.periods[].uplift_rule`
- Only records with `uplift_rule_governed_at`
- Accepted uplift suggestions only for lineage fields once a governed uplift rule exists

## Key Fields

- `uplift_rule_id`
- `agreement_id`
- `council_key`
- `effective_date`
- `quantum`
- `quantum_type`
- normalized components
- `source_rule_id`
- `source_page`
- `source_clause`
- `source_file_path`
- `source_section_path`
- `governed_timestamp`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

## Safety Rules

- Accepted suggestions alone are not governed canonical uplift rows.
- Missing source evidence references are lineage gaps, not absence.
- Rate-cap/fallback metadata is carried from governed records rather than recalculated for this layer.
