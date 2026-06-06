# `cohort_memberships` Governed Canonical Contract

Purpose: stable council cohort memberships for downstream comparison marts.

Inputs:
- `data/reference/victorian-council-master.csv`
- `data/reference/cohorts/cohort-nomenclature.yaml`
- `data/governed_canonical/pay_rows.csv`

Grain: one council/cohort membership.

Required lineage/status fields:
- `cohort_membership_id`
- `council_key`
- `cohort_type`
- `cohort_member`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Reference cohort memberships are `canonical_reference_only`.
- Benchmark-lane memberships may be `governed` only when derived from governed pay-row presence.
- Blank cohort reference fields are unknown and must not be emitted as reviewed exclusions.
