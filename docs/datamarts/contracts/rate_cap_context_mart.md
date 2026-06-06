# `rate_cap_context_mart` Contract

Purpose: report-facing rate-cap context by financial year and council exception.

Inputs:
- `data/governed_canonical/rate_cap_reference.csv`

Grain: one statewide cap or council exception context row.

Core fields:
- `rate_cap_context_id`
- `financial_year`
- `standard_rate_cap_pct`
- `council_key`
- `approved_cap_pct`
- `effective_cap_pct`
- `rate_cap_context_status`
- `source_url`
- `governed_canonical_status`

Safety Rules:
- Rate-cap context is external/public reference material, not an EBA uplift rule.
- Do not use this mart to infer an agreement uplift unless linked to a governed uplift record.
- Preserve source URL and external-reference status.
