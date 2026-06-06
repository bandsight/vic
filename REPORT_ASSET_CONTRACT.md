# Report Asset Contract

Status: initial contract for chart and report-ready assets as of 2026-05-02.

The EBA Workbench is not client-facing, but it produces assets that may flow into customer-facing reports. This contract defines the minimum metadata needed before a chart, table, audit extract, or written observation should be treated as report-ready.

## Intent

Report assets should be reusable evidence objects, not loose screenshots or one-off chart experiments.

Each asset should explain:

- what governed data it came from,
- what filters or cohorts shaped it,
- what calculation or visual encoding it uses,
- what quality caveats apply,
- what export formats exist,
- and what story the operator intended it to support.

## Asset Types

Current target asset types:

- chart: visual comparison, distribution, timeline, ranking, or cohort view.
- table: curated governed data extract for report use.
- audit_extract: council-specific evidence or lineage section.
- observation: written analytical note backed by governed data.
- image_export: rendered visual asset ready to place into a report.

## Required Fields

Every report asset should carry:

- `asset_id`: stable identifier.
- `asset_type`: `chart`, `table`, `audit_extract`, `observation`, or `image_export`.
- `title`: operator-facing title.
- `report_title_candidate`: customer-facing title candidate.
- `report_subtitle_candidate`: customer-facing subtitle candidate.
- `source_dataset`: governed data set or reference asset used.
- `source_dataset_version`: version, timestamp, or asset hash where available.
- `pay_metric_set`: pay metric vocabulary, when the asset is pay-related.
- `default_pay_metric`: selected pay metric for the default chart/report view.
- `available_pay_metrics`: metric values the asset can safely expose.
- `blocked_pay_metrics`: metric values requested but blocked or caveated.
- `metric_caveats`: pay metric-specific caveats and readiness warnings.
- `generated_at`: ISO timestamp.
- `generated_by`: operator, script, or agent.
- `filters`: cohort, date, council, classification, band, or status filters.
- `metric_definition`: plain-language calculation definition.
- `visual_encoding`: chart type, axes, colours, and scale choices where relevant.
- `quality_flags`: warnings, exclusions, uncertainty, and validation caveats.
- `provenance`: source endpoints, files, or governed records.
- `operator_note`: why the asset exists or what decision it supports.
- `export_targets`: intended formats such as PNG, SVG, CSV, XLSX, PPTX, DOCX, or PDF.
- `status`: `draft`, `reviewed`, `report_ready`, `superseded`, or `rejected`.

## Optional Fields

Useful optional fields:

- `customer_context`: council, cohort, report, or presentation this asset may support.
- `comparison_basis`: statewide, regional, metro, rural, council type, peer group, or custom cohort.
- `period_basis`: effective date, agreement period, financial year, calendar year, or quarter.
- `accessibility_note`: colour, contrast, labeling, or screen-reader consideration.
- `brand_profile`: visual system or report style profile.
- `linked_assets`: related chart/table/audit assets.
- `supersedes`: older asset IDs replaced by this asset.
- `reviewed_by`: human reviewer.
- `reviewed_at`: ISO timestamp.
- `status_updated_by`: operator or agent identity that last changed lifecycle status.
- `status_updated_at`: ISO timestamp for the latest lifecycle status change.

## Distribution Point Analysis

`data/analysis/distribution-point-analysis.json` is currently the first large analysis asset and should become the proving ground for this contract.

Minimum additions for that asset family:

- identify the governed pay-table build it was derived from,
- record the distribution metric and point calculation,
- record cohort filters and comparison basis,
- preserve quality flags for missing, projected, overridden, or non-standard rows,
- record chart-ready colour roles rather than hard-coding chart colours only in the UI,
- include report title/subtitle candidates for promising chart states.

Pay Structure Semantics v1.1 rule: distribution assets should be backed by `pay_distribution_point_mart` for metric-aware analytical truth and by `pay_service_horizon_curve_view` for interactive curve/envelope charts. They must declare `comparison_metric` or `service_horizon_window_id`, `service_horizon_window_label`, `included_metric_points`, `weighting_method`, `resolved_value_mode`, `input_mart_version`, and caveats for estimated Y1-Y6 service-horizon values. `range_midpoint_rate` is allowed only as an explicit metric, not as a hidden default for generic pay position.

Implemented first-pass outputs:

- companion manifest: `data/analysis/distribution-point-analysis.asset.json`
- export endpoint: `/api/analysis/distribution-point-analysis/exports`
- lifecycle endpoint: `/api/analysis/distribution-point-analysis/report-asset/status`
- download endpoint: `/api/analysis/distribution-point-analysis/exports/{format_name}`
- export folder: `exports/report-assets/distribution_point_analysis_default`
- export manifest: `distribution_point_analysis_default.exports.json`
- formats: CSV, SVG, PNG preview, XLSX, DOCX, PPTX

Exports should be generated only from a valid companion manifest. The export files are production-consumption assets, but the asset remains `draft`, `reviewed`, or `report_ready` according to operator governance rather than file existence alone. The Charts export panel exposes these everyday lifecycle states; `superseded` and `rejected` remain backend-valid statuses for future governance workflows.

## Governance Rules

Report assets must not hide uncertainty.

The asset can be polished, but the underlying record should preserve:

- excluded records,
- projected values,
- scenario overrides,
- missing source fields,
- rate basis conversions,
- confidence or validation flags,
- and operator notes.

An asset becomes `report_ready` only when the operator is satisfied that the source data, cohort selection, metric definition, and visual framing are defensible.

## Example Shape

```json
{
  "asset_id": "chart_pay_distribution_band_5_regional_2026_q2",
  "asset_type": "chart",
  "title": "Band 5 Weekly Rate Distribution - Regional Councils",
  "report_title_candidate": "Regional Council Band 5 Weekly Rates",
  "report_subtitle_candidate": "Governed EBA rates, current Q2 2026 benchmark set",
  "source_dataset": "pay_distribution_point_mart",
  "source_dataset_version": "2026-05-02T06:23:19Z",
  "pay_metric_set": "pay_structure_semantics_v1",
  "default_pay_metric": "range_midpoint_rate",
  "available_pay_metrics": ["entry_rate", "capacity_rate", "range_midpoint_rate", "service_year_3_rate"],
  "blocked_pay_metrics": [],
  "metric_caveats": ["All narrative must state the comparison metric."],
  "generated_at": "2026-05-02T06:30:00Z",
  "generated_by": "operator",
  "filters": {
    "council_category": "Regional",
    "classification_key": "band_05_level_A",
    "period_basis": "current_effective_rate"
  },
  "metric_definition": "Weekly base rate for the selected standard band/level.",
  "visual_encoding": {
    "chart_type": "distribution_point_plot",
    "x_axis": "weekly_rate",
    "point_colour": "cohort_highlight",
    "statewide_context": "grey"
  },
  "quality_flags": [],
  "provenance": {
    "endpoint": "/api/analysis/distribution-point-analysis",
    "asset_file": "data/analysis/distribution-point-analysis.json"
  },
  "operator_note": "Use to test whether regional peers cluster tightly around the statewide median.",
  "export_targets": ["png", "svg"],
  "status": "draft"
}
```
