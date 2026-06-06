# `spatial_reference` Governed Canonical Contract

Purpose: stable council spatial/geographic reference substrate.

Inputs:
- `data/reference/victorian-council-master.csv`

Grain: one council reference row.

Required lineage/status fields:
- `council_key`
- `spatial_key`
- `map_join_key`
- `lga_code`
- `abs_lga_code_2025`
- `has_abs_asgs`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Spatial rows are `canonical_reference_only`, not EBA facts.
- Missing map or ABS identifiers are `source_unclear`, not reviewed absence.
- External or ABS fields must retain reference provenance.
