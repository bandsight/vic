# `benchmark_questions` Governed Canonical Contract

Purpose: staged strategic questions that can later be bound to governed analytical products.

Inputs:
- `wiki/questions/*.json`

Grain: one benchmark question.

Required lineage/status fields:
- `benchmark_question_id`
- `question_code`
- `question_text`
- `agreement_id`
- `artifact_id`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Wiki questions are `staged_not_governed` until reviewed.
- Questions must not be treated as facts or report-ready requirements until bound to governed inputs.
- Missing agreement linkage is unresolved scope, not reviewed irrelevance.
