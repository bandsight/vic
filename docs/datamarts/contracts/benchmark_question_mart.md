# `benchmark_question_mart` Contract

Purpose: make staged benchmark questions visible as product-planning inputs.

Inputs:
- `data/governed_canonical/benchmark_questions.csv`

Grain: one benchmark question.

Core fields:
- `benchmark_question_id`
- `question_code`
- `question_text`
- `agreement_id`
- `artifact_id`
- `question_status`
- `recommended_next_action`
- `governed_canonical_status`

Safety Rules:
- Staged questions are not report-ready facts or requirements.
- Questions must be reviewed and bound to governed datasets before publication.
- Missing agreement scope is unresolved, not irrelevant or absent.
