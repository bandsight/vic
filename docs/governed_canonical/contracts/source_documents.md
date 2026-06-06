# `source_documents` Governed Canonical Contract

Purpose: canonical source-document register records for evidence lineage.

Inputs:
- `registers/source-document-register.csv`

Grain: one source document register row.

Required lineage/status fields:
- `source_document_id`
- `agreement_id`
- `frozen_path`
- `content_hash`
- `source_status`
- `serviceability_status`
- `source_file_path`
- `source_agreement_id`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Frozen source documents may be emitted as governed source-evidence references.
- Candidate or staged source documents must retain explicit non-governed status.
- Missing agreement linkage is `source_unclear`, not evidence absence.
