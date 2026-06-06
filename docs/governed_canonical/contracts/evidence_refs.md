# evidence_refs Contract

Status: initial governed canonical contract.

## Intent

Evidence reference rows for governed pay and uplift canonical records.

## Grain

`governed_record_id + governed_record_type`

## Allowed Inputs

- `data/governed_canonical/pay_rows`
- `data/governed_canonical/uplift_rules`
- `registers/source-document-register.csv`

## Key Fields

- `evidence_ref_id`
- `governed_record_id`
- `governed_record_type`
- `agreement_id`
- `source_document_id`
- `source_document_file`
- `source_page_ref`
- `source_clause_ref`
- `source_table_ref`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

## Safety Rules

- Evidence snippets are not synthesized here.
- Missing page/clause/table fields are lineage gaps unless explicit reviewed absence exists.
- This dataset is a reference map, not legal interpretation.
