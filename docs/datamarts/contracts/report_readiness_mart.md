# report_readiness_mart Contract

Status: initial contract.

## Intent

One row per canonical agreement showing whether the agreement is ready for downstream report use and what should be reviewed next.

## Grain

`agreement_id`

## Allowed Inputs

- `data/governed_canonical/readiness_status.csv`

## Key Fields

- `agreement_id`
- `agreement_name`
- `council_key`
- `council_name`
- `pay_data_readiness`
- `uplift_readiness`
- `canonical_identity_readiness`
- `source_evidence_readiness`
- `unresolved_issue_count`
- `blocked_reason`
- `recommended_next_review_action`
- `readiness_status`

## Safety Rules

- Readiness is a workflow status from the governed canonical layer, not an analytical fact.
- A blocked agreement remains usable for targeted review but should not flow into report products without filtering.
- Missing pay/uplift/source fields are blockers or unknowns, not absences.
