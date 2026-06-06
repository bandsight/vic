# How do small councils compare to the state?

Standalone scrollytelling prototype for the EBA Workbench downstream reporting layer.

This is an executive-facing digital briefing, not a dashboard. It demonstrates how the workbench can turn governed labour-intelligence architecture into a premium web-native report: distribution context, cohort logic, band-level pay comparison, uplift timing, entitlement framing, evidence lineage, caveats, and executive synthesis.

The current default view uses a real local workspace snapshot from datamart outputs. It is still a draft product asset: pay values are drawn from local workbench marts, cohort geography is driven by `council_profile_mart`, while entitlement content remains staged taxonomy rather than governed council-level entitlement evidence.

## Open

Run the workbench server, then open:

`http://127.0.0.1:8765/apps/small-council-state-scroll-report/`

Use the server port currently running for the workbench if it is not `8765`.
If an older local browser tab has cached a prior prototype, use `?distribution=v1` once to force a fresh static load.

The existing FastAPI bootstrap already mounts `apps/` at `/apps`, so no route or static mount changes were required.

## Files

- `index.html`: static shell for the report.
- `styles.css`: premium dark editorial styling, responsive layout, sticky scrollytelling, and reduced-motion handling.
- `app.js`: loads JSON, renders sections, and wires IntersectionObserver scroll states.
- `visuals.js`: custom SVG/DOM visual renderers for the distribution view, pay comparison, uplift, evidence, cohort map, classification, and entitlements.
- `data-adapter.js`: data loading, validation, normalisation, escaping, and formatting helpers.
- `data/sample-small-council-state.json`: mock report payload.
- `data/workspace-small-council-state.json`: generated real local workspace snapshot used by the page.
- `data/report-manifest.json`: prototype report asset manifest.
- `data/data-contract.md`: replacement contract for future governed data.
- `build-workspace-snapshot.py`: rebuilds the workspace snapshot from local datamarts and adds the Small shire map contract.
- `validate-data.mjs`: lightweight Node validation script for the active payload.

## Mock Data Structure

The sample JSON is split into:

- `metadata`
- `reportManifest`
- `cohort`
- `heroMetrics`
- `payPointGalaxy`
- `evidenceChain`
- `payByBand`
- `distribution`
- `classificationContext`
- `upliftTimeline`
- `entitlements`
- `executiveTakeaways`
- `narrativeSteps`

The original sample payload remains available as an illustrative placeholder. The default payload is `workspace-small-council-state.json`, generated from local datamarts with `metadata.dataStatus = workspace_snapshot_mixed_governance`.

The default `cohort.map` object contains controlled Small shire members, spatial keys, active pay coverage flags, and a pointer to the existing shared boundary asset at `/static/data/victoria-lga-boundaries.geojson`.

The default `distribution` object now includes all council-category cohorts for the active Band 5 distribution, plus descriptive shape diagnostics. In the current workspace snapshot it should be read as a multi-cluster distribution, not a normal curve.
The distribution asset includes only councils with an eligible Band 5 pay row as at the report snapshot date, and it labels Ballarat as a named statewide anchor. A pay row is eligible only when the report date falls between `effective_from` and `effective_to`; if `effective_to` is blank, the row is treated as operative for one calendar year from `effective_from`.

Rebuild the workspace snapshot:

```powershell
.venv-win\Scripts\python.exe apps\small-council-state-scroll-report\build-workspace-snapshot.py
```

Validate the active payload:

```powershell
node apps\small-council-state-scroll-report\validate-data.mjs
```

## Governed Replacement Path

A future report builder can replace `data/sample-small-council-state.json` with generated JSON assembled from:

- `council_profile_mart`
- `static/data/victoria-lga-boundaries.geojson`
- `cohort_comparison_mart`
- `pay_range_summary_mart`
- `pay_distribution_point_mart`
- `pay_range_summary_mart`
- `uplift_timing_mart`
- `temporal_pay_movement_mart`
- `entitlement_summary_mart`
- `evidence_trace_mart`
- `agreement_lineage_mart`
- `report_product_input_mart`

The visual layer expects explicit metrics, cohort definitions, caveats, and visual states. Production data should keep the `metadata` and `reportManifest` status fields conservative until the report is reviewed.

## Known Limitations

- The default values are real local workspace values, but the report is still draft and mixed-governance.
- The page reads a generated JSON snapshot, not live APIs.
- The cohort map uses controlled profile metadata and local boundary geometry, but production reporting should add governance status and coverage warnings per report asset.
- Current pay snapshots use an operative-window rule over `effective_from`/`effective_to`, with a one-year fallback for blank `effective_to` rows. Production should confirm this fallback against the governed pay-period model before publication.
- The retained pay point galaxy payload is an unweighted mart-row aggregation over all effective dates; production should decide whether to keep, redesign, or remove that experimental view.
- The distribution-shape reading is descriptive and bin-sensitive. It is useful for report interpretation, but it is not a formal statistical test of modality.
- Entitlement comparison uses staged taxonomy context only, not council-level entitlement scoring.
- Evidence lineage is a compact product frame, not source-level references.
- The pay chart uses the explicit `range_midpoint_rate` metric from active pay range summaries.

## Next Steps

- Build a server-side report payload generator from governed datamarts.
- Add report asset lifecycle metadata and evidence references per `REPORT_ASSET_CONTRACT.md`.
- Add source drill-through affordances for governed evidence references.
- Add export or snapshot generation if this becomes a retained report asset.
- Add a Playwright/browser smoke test once the project has a stable frontend test path for standalone apps.
