# uplift_timing_mart Contract

Status: initial contract.

## Intent

One row per governed uplift rule period, preserving timing, quantum, normalized components, recurrence hints, and source evidence references.

## Grain

`agreement_id + period_index`

## Allowed Inputs

- `data/governed_canonical/uplift_rules.csv`

## Key Fields

- `uplift_rule_id`
- `agreement_id`
- `agreement_name`
- `council_key`
- `council_name`
- `period_index`
- `effective_date`
- `timing_clause`
- `timing_pattern`
- `recurrence`
- `quantum`
- `quantum_type`
- `pct_component`
- `dollar_component`
- `dollar_basis`
- `resolved_pct`
- `resolved_basis`
- `fallback_status`
- `date_snap_status`
- `source_rule_id`
- `source_page`
- `source_clause`
- `governed_at`
- `review_governance_status`

## Safety Rules

- Do not promote an accepted suggestion into this mart unless it appears in `data/governed_canonical/uplift_rules`.
- Missing source pages are lineage gaps, not proof that no evidence exists.
- Rate-cap and fallback fields are carried as governed/normalized metadata, not recalculated here.
