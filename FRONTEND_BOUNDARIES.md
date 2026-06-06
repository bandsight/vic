# Frontend Boundaries

Status: working boundary note as of 2026-05-06.

The EBA Workbench frontend is a governance, QA, and analysis-studio interface. It is allowed to be exploratory while the machine workflow is still learning, especially for chart and report-asset discovery.

The important boundary is not "small frontend versus large frontend". The important boundary is whether durable truth and learning signals are captured through governed services rather than trapped in transient UI state.

## Frontend Can Own

- view layout, navigation, pane state, filters, sorting, and display grouping;
- temporary chart sketches and studio controls;
- operator affordances for correction, review, promotion, unwind, and notes;
- comparison views that align machine output, source evidence, and human expectation;
- local convenience state that can be safely recreated.

## Services Must Own

- accepted governed truth;
- correction and human-QA records;
- source references and provenance;
- promotion, unwind, and lifecycle semantics;
- repeatable extraction, scoring, validation, and scenario logic;
- report asset manifests once a chart candidate is kept;
- datamart generation logic and product-facing release contracts.

## API Boundary

All workbench API traffic from the frontend should go through `static/api-client.js` unless there is a clear reason not to.

Raw `fetch(...)` in `static/app.js` should be limited to static assets such as local GeoJSON or browser-native resources. JSON API calls should use the shared client so error handling and request defaults stay consistent.

Stable domain state can move into small helper modules without freezing the creative UI. `static/report-export-state.js` is the first example: it owns report-export catalog loading, cache reset, download-link construction, and lifecycle status updates while `static/app.js` keeps rendering the panel.

## Chart Graduation Path

Chart work can begin as creative exploration, but useful chart candidates should graduate through a lightweight contract:

1. sketch: a temporary visual idea in the workbench;
2. candidate: a kept idea with title, grain, metric, filters, and caveats;
3. report asset: a governed manifest-backed output with export targets;
4. datamart candidate: a repeatable data shape with dimensions, metrics, and aggregation rules;
5. product model input: a stable release-ready data asset for downstream product ingestion.

This keeps the workbench freeform while making successful experiments portable into the product layer.
