# Initial Datamart Suite

Status: initial governed datamart design as of 2026-05-07.

## Purpose

The datamart layer turns governed or explicitly staged workbench truth into reusable analytical structures for downstream reports and products.

The doctrine is:

```text
source evidence
-> machine extraction
-> review/governance
-> governed canonical datasets
-> analytical datamarts
-> report assets/products
```

Datamarts are not raw extraction outputs. They are report-facing analytical structures with explicit lineage, readiness state, and blocker reporting. Missing input data must remain unknown unless a governed review state says absence has been reviewed.

The immediate upstream layer is now:

```text
data/governed_canonical/
```

That layer contains normalized raw governed/canonical datasets. Datamarts should prefer it over direct reads from `canonical/*.yaml`.

## Initial Suite

The first suite now defines nineteen marts/views:

- `council_profile_mart`
- `pay_position_mart`
- `uplift_timing_mart`
- `cohort_comparison_mart`
- `report_readiness_mart`
- `evidence_trace_mart`
- `pay_rate_point_mart`
- `pay_range_summary_mart`
- `pay_progression_service_year_mart`
- `pay_distribution_point_mart`
- `pay_service_horizon_curve_view`
- `entitlement_summary_mart`
- `spatial_context_mart`
- `rate_cap_context_mart`
- `agreement_lineage_mart`
- `temporal_pay_movement_mart`
- `benchmark_question_mart`
- `report_product_input_mart`
- `data_quality_issue_mart`

The first six are core report/product pathways. `entitlement_summary_mart` is populated only as a staged/prototype taxonomy mart until governed entitlement facts exist. `spatial_context_mart` is populated from controlled council reference fields and carries a row-level readiness status. The additional marts expose rate-cap context, lineage, temporal pay movement, report-product inputs, staged benchmark questions, and data-quality work queues.

Pay Structure Semantics v1.1 adds a metric-aware pay curve layer. It deliberately increases the analytical rowset: each comparable range can produce entry, midpoint, capacity, spread, step mean, and Y0-Y6 service-horizon rows. This is expected; downstream charts should filter by `comparison_metric` rather than assuming one generic pay value.

Service-horizon values exist to compare councils at common employment-value moments even when their internal pay ladders have different lengths. Actual pay-table step count remains structural truth. A service horizon is a normalised comparison lens, not proof that a council has that many increments. When a horizon exceeds the actual ladder, the mart carries forward capacity with explicit `resolved_value_mode`, `capacity_carry_forward`, `actual_step_count`, and `resolved_level_label` fields. Governed progression rules outrank level-order horizon estimates.

The service-horizon curve view adds chart-specific window semantics. Dots and comparator curves must come from the same `service_horizon_window`. For example, an `entry_to_y3` chart pools entry, Y1, Y2, and Y3 observations for the comparator envelope and uses the same points for the selected council overlay. It must not put service-horizon dots on a stale midpoint curve.

V2 also materialises dynamic cohort rows from governed/reference `cohort_memberships`. The explorer can therefore rebuild the curve for `all_governed`, council type, region, LGPRF group, VIF grouping, VGCCC grouping, or benchmark-lane cohorts. A selected council may be shown against a comparator cohort even where it is not a member of that cohort, but the row must expose `selected_council_included_in_curve_sample` and the UI must label the comparator cohort by name.

## Source Policy

Preferred inputs for this first suite:

- `data/governed_canonical/council_agreements.csv`
- `data/governed_canonical/pay_rows.csv`
- `data/governed_canonical/uplift_rules.csv`
- `data/governed_canonical/evidence_refs.csv`
- `data/governed_canonical/readiness_status.csv`
- `data/governed_canonical/cohort_memberships.csv`
- `data/governed_canonical/source_documents.csv`
- `data/governed_canonical/report_inputs.csv`
- `data/governed_canonical/spatial_reference.csv`
- `data/governed_canonical/entitlement_items.csv`
- `data/governed_canonical/rate_cap_reference.csv`
- `data/governed_canonical/benchmark_questions.csv`

Safe lower-level inputs used to build governed canonical datasets:

- `data/reference/victorian-council-master.csv`
- `data/reference/cohorts/cohort-nomenclature.yaml`
- `canonical/*.yaml`, but only governed `sections.uplifts.data.periods` records for pay and uplift facts
- `registers/source-document-register.csv`
- `registers/intake-decisions.json`
- `registers/multi-council-decisions.csv`
- `data/bronze/phase1_source_build/candidate_agreements/candidate_agreements.json`

Unsafe as direct datamart truth:

- raw LLM suggestions without an accepted or governed state
- upstream extraction sections without promotion into `sections.uplifts`
- wiki artifacts that are proposed, mapped, or learning-state only
- blank fields unless a review state explicitly says the value is absent

## Populated Versus Blocked

Every mart build produces either:

- row outputs: CSV and JSON, plus a status JSON file; or
- a blocked status JSON file with reasons and next actions.

Rows can also carry row-level blocker flags. For example, a governed pay row with a missing rate value is kept as a governed row, but the `value_status` is `blocked_missing_governed_rate_value`; it is not converted to zero and not treated as absence.

## Current Build Command

```powershell
.\.venv-win\Scripts\python.exe scripts\build_datamarts.py
```

Outputs are written to:

```text
data/datamarts/
```

The generated run summary is:

```text
data/datamarts/datamart_build_summary.md
```

## Current Mart Readiness Rules

`council_profile_mart` is reference/staged. It uses council master reference data plus `data/governed_canonical/council_agreements`.

`pay_position_mart` is governed. It uses `data/governed_canonical/pay_rows`, which itself is built only from `sections.uplifts.data.periods[].pay_table` records with `pay_table_governed_at`.

`uplift_timing_mart` is governed. It uses `data/governed_canonical/uplift_rules`, which itself is built only from `sections.uplifts.data.periods[].uplift_rule` records with `uplift_rule_governed_at`.

`cohort_comparison_mart` is staged reference plus governed pay presence. It uses council master cohort fields and adds `standard_band_core` only when a council has governed pay rows.

`report_readiness_mart` is derived readiness metadata. It uses `data/governed_canonical/readiness_status`; it does not create analytical facts.

`evidence_trace_mart` is lineage metadata derived from `data/governed_canonical/evidence_refs`. Evidence snippets are not synthesized; rows say when snippets are not materialized.

`pay_rate_point_mart` assigns each governed pay point a range role: entry, internal step, capacity, singleton, unknown, or blocked.

`pay_range_summary_mart` derives entry, capacity, range midpoint, step mean, and progression spread. Midpoint is explicit as `range_midpoint_rate`; it is not the generic pay position.

`pay_progression_service_year_mart` emits Y0-Y6 service-horizon values. Governed progression logic is used when present. Otherwise level-order horizon estimates are emitted with `calculated_from_level_ordinal_estimate`, with explicit capacity carry-forward after the actual ladder is exhausted.

`pay_distribution_point_mart` is the metric-aware backing mart for distribution charts and report assets. Every row declares `comparison_metric` and also carries the full metric bundle for the range. Rows are emitted for `all_governed` and for governed/reference dynamic cohorts so comparator curves can be rebuilt without frontend semantic inference.

`pay_service_horizon_curve_view` is the visual-serving curve/envelope layer above `pay_distribution_point_mart`. It materializes `entry_only`, `range_midpoint_only`, `y3_only`, `capacity_only`, `entry_to_y3`, `y3_to_y6`, `entry_to_y6`, and `entry_to_capacity_profile` windows with `weighting_method = observation_weighted`. Its rows support both the primary curve cohort and a separately selected comparator background when the chart needs additional cohort context. The build also publishes `pay_service_horizon_curve_view.sqlite` as a read-optimised companion store for dynamic cohort selection; CSV/JSON remain the auditable mart outputs. The default V2 selector filters to cohorts with materialised comparator `n > 15`; smaller cohorts stay indexed but hidden from normal chart selection.

`entitlement_summary_mart` is partial/staged until reviewed/governed entitlement records exist. Current wiki artifacts are learning and semantic mapping inputs, not governed entitlement truth, so rows are not presence/absence facts.

`spatial_context_mart` is staged reference. It uses existing council master geographic fields and marks rows blocked where spatial reference fields are not populated.

`rate_cap_context_mart` is external/public reference context. It is useful for uplift and council-year strategy, but it is not an EBA uplift term.

`agreement_lineage_mart` exposes candidate, canonical, and source evidence lineage so downstream users can see what agreement records are current, superseded, or only candidate/staged.

`temporal_pay_movement_mart` calculates movements only across comparable governed numeric pay rows with effective dates.

`benchmark_question_mart` carries staged strategic questions from wiki artifacts. It is not report-ready until questions are reviewed and bound to governed inputs.

`report_product_input_mart` surfaces report asset manifests and their readiness state.

`data_quality_issue_mart` turns blockers and provisional statuses into a review work queue.

## Next Actions

- Decide whether datamarts should become an application-core service or remain script-built until the contracts stabilize.
- Add versioned datamart manifests once downstream consumers depend on these outputs.
- Promote evidence snippet materialization only when source page text extraction is stable enough to avoid false precision.
- Define the reviewed entitlement fact model before unblocking `entitlement_summary_mart`.
- Decide whether report-ready marts should be exposed through `/api/agent/catalog` and the operator UI.
- Bind benchmark questions and draft report assets to governed datamart contracts before publication.
