# entitlement_summary_mart Contract

Status: blocked initial contract.

## Intent

Summarize reviewed entitlement facts by council/agreement and entitlement family once governed entitlement data exists.

## Grain

`agreement_id + entitlement_family + cohort_scope`

## Allowed Inputs

- future governed entitlement fact records
- reviewed source-linked semantic wiki facts, once promoted to governed truth

## Current Blocker

The current wiki and clause artifacts are semantic learning and proposed evidence artifacts. They are not yet governed entitlement truth. The mart must remain blocked until reviewed entitlement facts exist.

## Key Fields

- `entitlement_summary_id`
- `agreement_id`
- `council_key`
- `entitlement_family`
- `cohort_scope`
- `value`
- `unit`
- `presence_state`
- `absence_review_state`
- `source_reference`
- `review_status`

## Safety Rules

- Do not infer entitlement absence from missing wiki data.
- Do not convert proposed clause maps into governed facts.
- Every absence must have an explicit reviewed absence state.
