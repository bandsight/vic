# readiness_status Contract

Status: initial governed canonical contract.

## Intent

One row per canonical agreement recording whether stable canonical inputs exist for downstream marts and reports.

## Grain

`agreement_id`

## Allowed Inputs

- `canonical/*.yaml`
- `data/governed_canonical/pay_rows`
- `data/governed_canonical/uplift_rules`
- `data/governed_canonical/council_agreements`
- `registers/source-document-register.csv`

## Key Fields

- `agreement_id`
- `agreement_name`
- `council_key`
- `pay_canonical_status`
- `uplift_canonical_status`
- `identity_canonical_status`
- `source_evidence_status`
- `unresolved_issue_count`
- `blocked_reason`
- `recommended_next_review_action`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`

## Safety Rules

- Readiness status does not invent analytical facts.
- Missing canonical inputs are blockers or unknowns, not absence.
- Report marts should preserve enough status fields for downstream filtering.
