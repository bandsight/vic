# `rate_cap_reference` Governed Canonical Contract

Purpose: public/external Victorian rate-cap reference context.

Inputs:
- `src/benchmarking_data_factory/uplift_rules/external/rate-cap/standard-statewide-rate-caps.csv`
- `src/benchmarking_data_factory/uplift_rules/external/rate-cap/rate-cap-year-status.csv`
- `src/benchmarking_data_factory/uplift_rules/external/rate-cap/higher-cap-exceptions.csv`

Grain: one statewide financial-year cap or one council exception.

Required lineage/status fields:
- `rate_cap_reference_id`
- `financial_year`
- `rate_cap_value`
- `approved_cap_pct`
- `source_url`
- `source_file_path`
- `source_section_path`
- `review_governance_status`
- `governed_canonical_status`
- `value_status`

Safety Rules:
- Rows are `external_reference`, not governed EBA terms.
- Council exceptions must preserve source URL/provenance.
- Do not merge rate-cap values into uplift truth without an explicit governed uplift rule.
