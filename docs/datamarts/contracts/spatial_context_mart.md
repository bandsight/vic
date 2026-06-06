# spatial_context_mart Contract

Status: initial contract.

## Intent

Reusable spatial and geographic context for council comparison and reporting.

## Grain

`council_key`

## Allowed Inputs

- `data/reference/victorian-council-master.csv`
- existing controlled geography fields already present in the council master

## Key Fields

- `council_key`
- `council_name`
- `spatial_key`
- `map_join_key`
- `lga_code`
- `abs_lga_code_2025`
- `abs_lga_name_2025`
- `abs_area_albers_sqkm`
- `office_township`
- `office_lat`
- `office_lon`
- `vif_metropolitan_region`
- `vif_regional_partnership`
- `vgccc_region`
- `has_abs_asgs`
- `spatial_context_status`
- `blocked_reason`

## Safety Rules

- Geography fields are controlled reference context, not EBA-derived facts.
- Missing geography fields produce row-level blocked status, not negative conclusions.
- Do not add calculated spatial products until the reference layer is versioned for that use.
