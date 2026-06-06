# `agreement_lineage_mart` Contract

Purpose: expose canonical agreement lineage, candidate metadata, and source-evidence status.

Inputs:
- `data/governed_canonical/council_agreements.csv`

Grain: one canonical agreement record.

Core fields:
- `agreement_id`
- `base_agreement_id`
- `council_key`
- `matter_number`
- `print_id`
- `version`
- `pipeline_status`
- `superseded_by_ae_id`
- `lineage_key`
- `source_evidence_status`
- `governed_canonical_status`

Safety Rules:
- Candidate lineage fields are metadata, not governed agreement facts.
- Superseded/current status must be carried explicitly.
- Missing source evidence is a blocker or unknown state, not absence.
