# `data_quality_issue_mart` Contract

Purpose: convert blockers, gaps, and provisional states into a review work queue.

Inputs:
- `data/governed_canonical/readiness_status.csv`
- `data/governed_canonical/pay_rows.csv`
- `data/governed_canonical/evidence_refs.csv`
- `data/governed_canonical/report_inputs.csv`
- `data/governed_canonical/spatial_reference.csv`
- `data/governed_canonical/entitlement_items.csv`

Grain: one generated data-quality issue.

Core fields:
- `data_quality_issue_id`
- `issue_type`
- `severity`
- `agreement_id`
- `council_key`
- `source_dataset`
- `source_record_id`
- `issue_status`
- `issue_detail`
- `recommended_next_action`
- `governed_canonical_status`

Safety Rules:
- Issues are operational review metadata, not source facts.
- Missing data must stay unresolved unless a reviewed absence state exists.
- Generated issues should point back to canonical source records wherever practical.
