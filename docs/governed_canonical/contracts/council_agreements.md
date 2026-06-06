# council_agreements Contract

Status: initial governed canonical contract.

## Intent

One row per canonical agreement file, with council identity, source evidence status, and canonical/reference lineage.

## Grain

`agreement_id`

## Allowed Inputs

- `canonical/*.yaml`
- `data/reference/victorian-council-master.csv`
- `data/bronze/phase1_source_build/candidate_agreements/candidate_agreements.json`
- `registers/source-document-register.csv`

## Key Fields

- `agreement_id`
- `base_agreement_id`
- `agreement_name`
- `council_key`
- `council_name`
- `candidate_agreement_status`
- `source_evidence_status`
- `canonical_record_status`
- `source_file_path`
- `source_agreement_id`
- `source_section_path`
- `governed_timestamp`
- `review_governance_status`
- `value_status`

## Safety Rules

- Council master identity is `canonical_reference_only`.
- A canonical agreement file without governed pay/uplift rows is not report-ready absence.
- Candidate registry fields remain candidate/reference lineage unless promoted elsewhere.
