# evidence_trace_mart Contract

Status: initial contract.

## Intent

Trace report-facing governed records back to source documents, pages, clauses, tables, and review status where available.

## Grain

`governed_record_id + evidence_trace_type`

## Allowed Inputs

- `data/governed_canonical/evidence_refs.csv`

## Key Fields

- `evidence_trace_id`
- `governed_record_id`
- `governed_record_type`
- `agreement_id`
- `council_key`
- `source_document_id`
- `source_document_file`
- `source_page_ref`
- `source_clause_ref`
- `source_table_ref`
- `evidence_snippet`
- `confidence`
- `review_status`
- `absence_review_state`
- `source_layer`

## Safety Rules

- Evidence snippets are blank until explicitly materialized from source page text.
- Missing source page or clause references are lineage gaps, not proof of absence.
- This mart traces governed records; it does not validate legal interpretation by itself.
