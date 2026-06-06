# `end_of_band_dollars`

Band-level cash end-of-band payment rows derived after governed pay scenarios. In the agreement workspace this sits after `scenarios` and before final `uplifts`/Governed Set acceptance.

## Grain

One row per governed agreement, operative period, and band where an in-scope cash end-of-band or top-of-band amount can be resolved.

## Required Source

- `canonical/*.yaml::sections.uplifts.data.periods[].pay_table`
- `cache/<agreement_id>/full_text.txt`

## Key Fields

- `agreement_id`
- `period_index`
- `band`
- `effective_from`
- `to_date`
- `end_of_band_cash_amount`
- `amount_basis`
- `calculation_status`
- `rule_kind`
- `clause_number`
- `source_page`
- `clause_extract`
- `end_of_band_weekly_rate`
- `end_of_band_rate_source_effective_from`

## Governance Rule

Rows are emitted only for current, non-grandfathered cash end-of-band/top-of-band amounts. One-off date-gated bonuses, leave-only benefits, recognition programs, historical absorbed payments, and amounts built into pay scales are excluded.

Formula amounts may be calculated from governed weekly rates when the clause supports it. If a non-standard calculated `E (End of Band)` table column exists, it may be used as source evidence for the EOB dollar premium without promoting `E` into the standard governed pay rows. The `calculation_status` field must disclose whether the value is explicit or computed.

Rare calculated `E` pattern:

- Treat the emitted amount as the annual cash premium above the current band top, not as the target salary level itself.
- Midpoint formulas are based on the gap between adjacent bands, so lower bands may have larger EOB dollar premiums than higher bands when their adjacent-band gap is wider or when the fixed floor applies.
- When the source agreement provides an `E (End of Band)` rate table for the same operative period, calculate the EOB dollar premium as `E - upper ordinary level`, where the upper ordinary level is usually `D` and may be `C` when `D` is not applicable.
- When a later governed period does not have its own `E` table, do not project the prior `E` table. Apply the EA rule to that period's governed standard rows and mark the row as formula-computed.
- Keep calculated `E` values out of governed standard pay rows.

## Safety Rules

- Do not emit one-off, grandfathered, leave-only, recognition-only, absorbed, or built-into-scale candidates as governed cash rows.
- Do not treat missing cached text as absence.
- Do not use band-order monotonicity as a validation rule; validate calculated amounts against the clause formula, table evidence, and adjacent-band rates.
- Preserve clause extract, page, and calculation status for every emitted amount.
