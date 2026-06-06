# Small Council State Scroll Report Data Contract

Status: prototype contract for a standalone downstream reporting layer.

This contract describes the JSON shape consumed by `app.js`. The default file is now `workspace-small-council-state.json`, generated from local datamarts by `build-workspace-snapshot.py`. The original `sample-small-council-state.json` remains as a pure placeholder example.

## Safety

- `metadata.dataStatus` must clearly mark whether data is `illustrative_placeholder`, `workspace_snapshot_mixed_governance`, `draft_governed`, or `report_ready`.
- `metadata.decisionUse` must be `not_for_decision_making` unless the payload has passed product governance.
- Entitlement scores must remain caveated unless they are produced by governed entitlement summaries.
- Pay metrics must state the comparison metric, not rely on an implicit midpoint.
- Active/current pay rows must be date-bound: the report date must fall between `effective_from` and `effective_to`. If `effective_to` is blank, use `effective_from + 1 calendar year` as the operative end unless a governed pay-period model provides a better end date.

## Required Objects

- `metadata`: report title, status, caveats, prototype label, generated date, and replacement guidance.
- `reportManifest`: report asset metadata aligned to `REPORT_ASSET_CONTRACT.md`.
- `cohort`: cohort definition, comparison universe, production caveat, optional map contract, and example members.
- `heroMetrics`: opening report metrics.
- `payPointGalaxy`: temporal scatter payload for cohort x date x band x level average values.
- `evidenceChain`: source-to-report lineage stages.
- `payByBand`: standard band pay comparison data and visual state copy.
- `distribution`: percentile/range ribbons for selected bands.
- `classificationContext`: band ladder and workforce-shape notes.
- `upliftTimeline`: current, scheduled uplift, and horizon values.
- `entitlements`: placeholder employment-value matrix.
- `executiveTakeaways`: final synthesis cards.
- `narrativeSteps`: scroll steps that drive the sticky pay visual.

## Governed Replacement Mapping

The production payload should be assembled from governed outputs along these lines:

- `cohort` from `council_profile_mart` and `cohort_comparison_mart`.
- `cohort.map` from controlled council profile metadata plus a boundary asset such as `static/data/victoria-lga-boundaries.geojson`.
- `payPointGalaxy` from `pay_range_summary_mart`, grouped by cohort, effective date, standard band, and classification level label.
- `payByBand` from `pay_range_summary_mart` or `pay_distribution_point_mart`, with an explicit `comparison_metric`.
- `distribution` from active `pay_range_summary_mart` observations, `pay_distribution_point_mart`, or `pay_service_horizon_curve_view`.
- `upliftTimeline` from `uplift_timing_mart` and `temporal_pay_movement_mart`.
- `entitlements` from `entitlement_summary_mart`.
- `evidenceChain` and source references from `evidence_trace_mart` and `agreement_lineage_mart`.
- `reportManifest` from `report_product_input_mart` or the report asset builder.

## Visual State Contract

Every `narrativeSteps[].visualState` must match a key under `payByBand.states`.

Current supported states:

- `state_only`
- `small_vs_state`
- `gap_highlight`
- `band_focus`
- `timing_sensitive`
- `takeaway`

The pay visual can accept additional states later, provided `visuals.js` is extended with an explicit rendering rule and the data includes explanatory copy.

## Cohort Map Contract

If supplied, `cohort.map` should include:

- `boundaryGeojsonUrl`: static URL for the LGA boundary FeatureCollection.
- `categoryField` and `categoryValue`: the controlled profile field used to define the cohort.
- `smallSpatialKeys`: spatial keys to highlight as controlled cohort members.
- `activePaySpatialKeys`: cohort spatial keys with active pay rows in the report snapshot.
- `labelSpatialKeys`: optional spatial keys to label on the map.
- `allSmallShireCouncils[]`: council name, short name, spatial key, regional partnership, and active pay coverage flag.
- `caveat`: map-specific coverage and governance warning.

The renderer treats multipart boundary features as multiple SVG paths, so feature counts can exceed council counts.

## Pay Point Galaxy Contract

`payPointGalaxy` should include:

- `question`, `title`, `summary`, `metric`, `sourceDataset`, and `caveat`.
- `cohorts[]`: cohort IDs and display labels.
- `summaryMetrics[]`: four concise coverage metrics for the panel.
- `coverage`: source row counts, council counts, date range, value range, and band count.
- `observations[]`: one point per cohort, effective date, band, and level label, with `averageWeekly`, `minWeekly`, `maxWeekly`, `rowCount`, and `councilCount`.

The current workspace builder uses `step_mean_weekly_rate` where available and falls back to `range_midpoint_weekly_rate`. Production should explicitly decide whether this view is all-time, active-only, headcount-weighted, agreement-deduplicated, or governance-filtered.

## Distribution Asset Contract

For the current distribution-first report asset, `distribution.prototypeStyle` may include:

- `observations[]`: individual active observations with council, value, category, agreement, Small shire flag, `effectiveFrom`, `effectiveTo`, and `operativeEnd`.
- `cohortStats[]`: stats by controlled council category, such as Small shire, Large shire, Regional, Interface, and Metropolitan.
- `densityBins[]`: precomputed histogram bins used by the SVG distribution shape.
- `highlightObservation`: optional named council anchor, for example Ballarat.
- `asOfDate`, `inclusionRule`, and optional `snapshotRule`: explicit snapshot date and active-row inclusion logic.

`distribution.shapeDiagnostics` can carry a descriptive reading of the shape, including the binning method, peak ranges, interpretation, and caveat. Treat this as an explanatory report diagnostic, not a formal statistical modality test.

## Uplift Phase Contract

Every `upliftTimeline.phases[].id` can be used as a scroll-triggered phase. The current renderer supports:

- `current`
- `uplifts`
- `horizon`

Each `upliftTimeline.series[]` row should include:

- `name`
- `segment`
- `currentWeekly`
- `horizonWeekly`
- `cycleStatus`
- `uplifts[]` with `date`, `pct`, and `label`

## Validation

Run:

```powershell
node apps\small-council-state-scroll-report\validate-data.mjs
```

This checks the mock payload has the expected top-level objects, pay band coverage, visual states, uplift phases, and explicit placeholder status.

To validate the pure placeholder sample instead:

```powershell
node apps\small-council-state-scroll-report\validate-data.mjs sample-small-council-state.json
```
