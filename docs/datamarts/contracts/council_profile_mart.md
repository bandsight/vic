# council_profile_mart Contract

Status: initial contract.

## Intent

One row per council in the controlled council master, with identity, category, geography, and current source-lineage state for downstream reporting.

## Grain

`council_key`

## Allowed Inputs

- `data/governed_canonical/council_agreements.csv`
- `data/reference/victorian-council-master.csv`
- `data/bronze/phase1_source_build/candidate_agreements/candidate_agreements.json` for candidate counts only

## Key Fields

- `council_key`
- `canonical_council_name`
- `short_name`
- `status`
- `is_active`
- `council_category`
- `council_type`
- `official_name`
- `spatial_name`
- `lga_code`
- `abs_lga_code_2025`
- `vif_metropolitan_region`
- `vif_regional_partnership`
- `lgprf_group`
- `canonical_agreement_count`
- `canonical_agreement_ids`
- `candidate_agreement_count`
- `source_lineage_status`
- `source_lineage_notes`

## Safety Rules

- A council with no canonical agreement row is `no_current_working_set_record_not_absence`, not absent from the market.
- Council identity is staged reference truth from the council master, not EBA extraction truth.
- Source lineage counts are current-workspace coverage signals only.
