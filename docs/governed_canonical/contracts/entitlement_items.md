# `entitlement_items` Governed Canonical Contract

Purpose: entitlement taxonomy/items upstream of entitlement marts.

Inputs:
- Reviewed entitlement fact sources when they exist.
- Staged wiki exemplars only with explicit provisional status.
- Curated definition overrides in `data/review/entitlement_definition_overrides.json`, used only to tighten taxonomy wording and not to promote entitlement facts.

Grain: one entitlement item or taxonomy row.

Required lineage/status fields:
- `entitlement_item_id`
- `entitlement_id`
- `entitlement_label`
- `category`
- `scope`
- `source_artifact_id`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Staged taxonomy rows are not entitlement presence/absence facts.
- Missing entitlement evidence is `not_reviewed` unless a reviewed absence state exists.
- Do not infer entitlement absence from missing clause extraction.
- Definition overrides set matching boundaries only; they do not establish source-clause presence, absence, or value.
