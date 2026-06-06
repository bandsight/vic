# cohort_comparison_mart Contract

Status: initial contract.

## Intent

Reusable council and benchmark cohort memberships for downstream comparison views.

## Grain

`council_key + cohort_type + cohort_member`

## Allowed Inputs

- `data/reference/victorian-council-master.csv`
- `data/reference/cohorts/cohort-nomenclature.yaml`
- governed pay presence from `data/governed_canonical/pay_rows.csv`

## Key Fields

- `cohort_membership_id`
- `council_key`
- `council_name`
- `cohort_type`
- `cohort_member`
- `cohort_definition_version`
- `inclusion_reason`
- `exclusion_unknown_handling`
- `source_reference`

## Safety Rules

- Blank reference fields are not emitted as negative cohort membership.
- `standard_band_core` membership requires at least one governed pay row for that council.
- This mart does not decide specialist cohorts; it only carries controlled reference and governed presence signals.
