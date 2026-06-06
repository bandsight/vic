# Current State and Next Actions

Scan date: 2026-05-06.

This file records the real project state observed from the local workspace, in-process API checks, tests, and current file structure.

## Current State

The active application root is:

`C:\Users\Johns\Documents\Codex\eba-workbench\eba-workbench`

The repository now also has adjacent project material one level above the app:

- `brand-guide`: Municipal Benchmark visual identity boards and asset register.
- `codex-desktop-topics`: extracted Codex project conversation topics.
- `scripts`: currently empty at the top level.

## Runtime Health

The app is expected to run locally on:

`http://127.0.0.1:8765`

Observed runtime status from an in-process FastAPI check:

- FastAPI app bootstraps successfully.
- Agent and analysis endpoints are reachable through `TestClient`.
- Provider: `anthropic`.
- Model: `claude-sonnet-4-20250514`.
- Text and vision capability are both ready.

## Backend Shape

The backend has moved well beyond the older single-file shape.

`main.py` is now a bootstrap and compatibility layer. Most workbench logic has been moved into focused modules under:

`src/benchmarking_data_factory/workbench`

The first explicit application-core layer now exists at:

`src/benchmarking_data_factory/workbench/application_core.py`

It currently owns shared path cataloging, packaging profile and package-plan discovery, report asset contract metadata, report export generation, agent discovery payloads, wiki-layer cataloging, analysis asset orchestration, intake/reference workflow adapters, agreement workspace actions, and governance event workflows. Operator command discovery has been split into `src/benchmarking_data_factory/workbench/operator_commands.py`. The app factory composes these services through `build_workbench_services(...)` and attaches them to `app.state.workbench_services`, so routes and future agents have a common service surface instead of each route rediscovering paths or rebuilding status payloads.

Notable current workbench modules include:

- app bootstrap and app factory
- intake workflow and intake state
- source document intake
- document routes and page workflow
- council read model and council action routes
- analysis workspace and spatial analysis routes
- pay table workflow and agreement extraction
- uplift rules workflow
- scenario governance and scenario routes
- wiki layer and wiki routes
- audit report, audit lineage, audit identity, audit QA summary, governed evidence
- review advice and review learning
- application core services for path discovery, packaging, report assets, report exports, agent discovery, wiki-layer cataloging, analysis assets, intake/reference workflows, agreement workspace actions, and governance event workflows
- operator command catalog service
- compatibility wrappers and exports

The app currently exposes `88` routes, including:

- source intake and decisions
- LLM connection/status
- council workspaces
- PDF/page text/page image access
- overview generation
- pay-table find/extract/save/validate/construct
- uplift-rule suggest/accept/scenario/override flows
- governed-set promote/unwind
- analysis data sets
- distribution-point analysis
- distribution-point report export catalog, materialization, and file download
- distribution-point report asset lifecycle status update
- council audit
- rate-cap status and confirmation
- reference and spatial council data
- agent discovery routes

Agent discovery is now available through:

- `/api/agent/status`
- `/api/agent/catalog`
- `/api/agent/actions`
- `/api/agent/io`

The agent catalog now exposes `11` data sets, including the report asset companion manifest for distribution point analysis, council master reference data, and council geography.

Agent status, catalog, actions, and I/O now include package-profile summary data, a resolved packaging plan, report asset contract status, report export targets/actions, and an operator command catalog. That gives Codex, OpenClaw, or another runner a lightweight way to tell whether the current checkout is only runtime code, includes governed data, includes source evidence, has contract-valid report asset manifests, has concrete report output formats, and which setup/run/test/smoke/package/handoff commands are safe to use.

## Data State

Observed local data volume:

- Canonical agreement YAML files: `111`
- Immutable source PDFs: `108`
- Reference PDFs: `4`
- Scenario override JSON files: `22`
- Analysis asset: `data/analysis/distribution-point-analysis.json`
- Distribution asset size: about `28.6 MB`
- Distribution asset contract companion: `data/analysis/distribution-point-analysis.asset.json`
- Distribution report exports: `exports/report-assets/distribution_point_analysis_default`
- Report asset contract: `REPORT_ASSET_CONTRACT.md`
- Cohort reference scaffold: `data/reference/cohorts/cohort-nomenclature.yaml`
- Wiki layer files: `3` document maps, `5` reference inputs, `5` runs, `5` question files, `5` learning-backlog files, `1` language map, and `8` artifacts.

## Intake State

Current intake quality endpoint reports:

- Candidate records: `319`
- Unique agreement IDs: `316`
- Active candidate records: `246`
- Superseded by newer: `70`
- Superseded in lineage: `3`
- Matched candidates: `149`
- Active matched: `78`
- Active unmatched: `168`
- Visible working set: `110`
- Visible active: `79`
- Visible superseded: `31`
- Registry rows in working set: `107`
- Frozen PDFs in working set: `108`
- Councils with runner-up review available: `57`

Current intake flags:

- `168` active registry rows did not map to a Victorian LGA.
- `31` visible working-set rows are marked as superseded.
- Runner-up review is available for `57` councils.

## Governed Data Sets

Pay tables:

- Agreements scanned: `110`
- Agreements with governed pay tables: `100`
- Governed periods: `286`
- Tables: `285`
- Weekly rows: `8,506`
- Weekly rate basis counts: `6,558` direct weekly rows, `1,328` annual-rate conversions, `417` scenario-override computed rows, and `203` fortnightly-rate conversions.
- Earliest effective date: `2017-07-01`
- Latest effective date: `2028-07-01`

Uplift rules:

- Agreements scanned: `110`
- Agreements with governed periods: `100`
- Agreements with uplift rules: `99`
- Governed periods: `286`
- Governed uplift rules: `273`
- Periods without rule: `13`
- Rate-cap rules: `43`
- Floor rules: `202`
- Earliest effective date: `2017-07-01`
- Latest effective date: `2028-07-01`

The pay-table entity set is now large enough to support real chart and distribution work. Distribution-point analysis is now the first report asset family with automatic companion manifest emission through `ReportAssetService` and concrete CSV/SVG/PNG/XLSX/DOCX/PPTX output through `ReportExportService`.

## Frontend State

The frontend remains plain static HTML/CSS/JS:

- `static/index.html`
- `static/app.js`
- `static/api-client.js`
- `static/report-export-state.js`
- `static/display-values.js`
- `static/pdf-viewer.js`
- `static/style.css`
- `static/shell/*.css`

The shell now supports:

- Source Intake
- Review Board
- Council Audit
- Data Sets: Uplift Rules, Pay Tables, Charts, Councils
- Settings
- Agreement Workspace with PDF and review panes

The Charts data-set view now includes a report export panel for `distribution_point_analysis_default`. It displays CSV/SVG/PNG/XLSX/DOCX/PPTX readiness, export manifest state, lifecycle status, row-limited or full export generation, refresh, governed `draft` / `reviewed` / `report_ready` status controls, and direct download links for generated files.

The frontend boundary note now lives in `FRONTEND_BOUNDARIES.md`. API request/error handling has been extracted to `static/api-client.js`, and report-export loading/cache/lifecycle state has been extracted to `static/report-export-state.js`; `static/app.js` keeps raw `fetch(...)` only for the static LGA GeoJSON layer.

The external `brand-guide` folder contains `9` PNG boards plus an asset register. These are candidate Municipal Benchmark identity assets and should now be treated as design source material.

## Verification

Commands run during the 2026-05-06 scan:

- `.\.venv-win\Scripts\python.exe -m pytest`: `490 passed`.
- `npm run lint`: passed with no warnings; it now covers `static/app.js`, `static/api-client.js`, `static/report-export-state.js`, and `static/display-values.js`.
- `node node_modules/eslint/bin/eslint.js static/*.js`: passed.
- `.\.venv-win\Scripts\python.exe -m py_compile smoke_test.py main.py`: passed.
- `.\.venv-win\Scripts\python.exe smoke_test.py`: passed.
- `workbench-agent.json` command `smoke_windows` (`.\.venv-win\Scripts\python.exe smoke_test.py`): passed.
- `.\.venv-win\Scripts\python.exe -m pytest tests\test_agent_routes.py tests\test_application_core.py`: `22 passed`.
- `workbench-agent.json` and `PORTABLE_MANIFEST.json`: valid JSON.
- In-process `/api/agent/status`: reports `ok: true`, `88` routes, `package_profile.inferred_profile` as `with_source_evidence`, LLM text/vision ready, and the distribution-point report asset as a valid `draft`.
- In-process `/api/agent/catalog`: reports `11` data sets and `88` routes.
- In-process `/api/agent/actions`: exposes `9` base workflow actions, `5` package actions, `1` report-export action, `4` wiki actions, and `17` operator command actions.
- In-process `/api/agent/io`: reports package profile data presence, a valid `runtime_code` packaging plan, report asset contract/catalog status, and the writable governance directories.
- In-process `/api/wiki/status`: reports `3` document maps, `5` reference inputs, `5` runs, `5` question files, `5` learning-backlog files, `1` language map, and `8` artifacts.
- In-process `/api/intake/quality`: reports `319` candidate records, `168` active unmatched, and `110` visible working-set rows.
- In-process `/api/councils`: reports `110` rows.
- In-process `/api/analysis/pay-tables`: reports `285` tables and `8,506` flattened weekly pay rows.
- In-process `/api/analysis/uplift-rules`: reports `273` governed uplift rules and `43` rate-cap rules.
- In-process `/api/analysis/distribution-point-analysis/exports`: reports `6` implemented export targets, a valid `draft` report asset, and existing CSV/SVG/PNG/XLSX/DOCX/PPTX export files.
- Source/static path scan did not find hard-coded developer-machine paths in `src`, `static`, `scripts`, or `tests`.

Earlier Windows portability proof still stands unless retested otherwise:

- Windows `runtime_code` package script produced a portable zip with no excluded secret/runtime directories.
- Windows unpack script successfully unpacked a runtime package into a throwaway target and created `.env`, runtime folders, manifests, and `var/portable-install.json`.
- Windows setup script fails honestly on native command failures.
- Windows clean-target setup passed from `exports\portable\unpack-smoke-setup3` using `-PipTrustedHost`.
- Windows clean-target run booted on `http://127.0.0.1:8876`; `/` returned `200`, `/api/agent/status` returned `ok: true`, and `/api/agent/catalog` exposed the asset manifest while correctly omitting the raw distribution JSON from the runtime package.
- Windows offline dependency bundle created `39` wheels under `vendor\python-wheels`, about `26.8 MB`.
- Windows dependency-bundled runtime package `exports\portable\eba-workbench-runtime_code-20260502-172351.zip` included `39` wheel files and `vendor\dependency-bundle.json`.
- Windows offline setup/run booted on `http://127.0.0.1:8877`; `/` returned `200` and `/api/agent/status` returned `ok: true`.
- Windows package script unknown-profile guard rejected `bogus` before copying or zipping.

Known frontend warning:

- None observed in the latest `npm run lint`.

Tooling notes:

- `git` is not available on this shell PATH, so git status was not inspected.
- `rg` is present but blocked by Windows with `Access is denied`; native PowerShell enumeration was used instead.
- `npm run lint` is now the stable frontend lint command.
- `smoke_test.py` now self-adds `src` to `sys.path` and uses ASCII output, so the published `smoke_windows` command works from a plain shell.
- `tests/smoke.py` is a separate optional browser smoke check and requires Playwright dependencies if run directly.
- WSL is present as a Windows command, but no Linux distro is installed. Ubuntu script execution and syntax checks were not available on this host.
- Local Python and npm package installs hit certificate-chain issues. Python setup is supported with `-PipTrustedHost`; Node tooling is now opt-in and has `-NpmUseSystemCa` / `-NpmStrictSslFalse` switches for controlled environments.

## Portability State

Current app source path handling is mostly good:

- Source code and static assets did not show hard-coded developer-machine paths.
- `main.py` derives key runtime paths from `ROOT = Path(__file__).parent`.

Current portability scaffolding now exists:

- `workbench-agent.json`
- `PORTABLE_MANIFEST.json`
- `scripts/setup-windows.ps1`
- `scripts/setup-ubuntu.sh`
- `scripts/build-offline-deps.ps1`
- `scripts/build-offline-deps.sh`
- `scripts/run-windows.ps1`
- `scripts/run-ubuntu.sh`
- `scripts/package-workbench.ps1`
- `scripts/package-workbench.sh`
- `scripts/unpack-workbench.ps1`
- `scripts/unpack-workbench.sh`

Remaining portability gaps:

- Windows package, unpack, setup, and run have been smoke-tested for the `runtime_code` profile.
- Windows offline dependency-bundled setup and run have been smoke-tested for the `runtime_code` profile with local Python wheels.
- Windows package script now rejects unknown profile names before creating a package.
- Runtime packages now include `data/analysis/*.asset.json` report asset manifests but exclude bulky generated analysis data.
- Ubuntu scripts are written but have not been run in an Ubuntu environment.
- Optional Node tooling install remains environment-sensitive because the local npm registry TLS chain is not trusted by this Node/npm setup.
- Optional npm cache bundling is scripted but not smoke-tested because local npm registry TLS is not trusted by this Node/npm setup.
- `__pycache__` files embed old paths and should be excluded or cleaned before any portable package is built.

## Risks and Friction

1. Intake identity is still noisy.
   The `168` active unmatched candidates are probably not all in scope, but the number is large enough that unmatched-active handling should be visible and explainable.

2. Superseded records are still present in the visible working set.
   This may be intentional for lineage, but the UI and governed outputs need to make the reason clear.

3. Portability is proven for the lightweight Windows runtime path and the Windows offline Python wheelhouse path, but not yet for Ubuntu.
   Packaging, unpack, setup, run, manifests, and agent discovery now work from a clean Windows `runtime_code` target. Dependency-bundled runtime packages can install Python dependencies offline from `vendor\python-wheels`. Ubuntu, governed-data packages, source-evidence packages, and optional Node tooling still need hardening.

4. Chart/asset production now has a first governed export path.
   `distribution-point-analysis.json` is a large analysis artifact. `REPORT_ASSET_CONTRACT.md` defines the first asset contract, `ReportAssetService` emits/validates `distribution-point-analysis.asset.json`, and `ReportExportService` materializes contract-valid CSV/SVG/PNG/XLSX/DOCX/PPTX outputs plus an export manifest.

5. The application core is useful, but it is now carrying a lot of responsibility.
   Agent discovery, packaging, report assets, report exports, wiki cataloging, analysis assets, intake/reference workflows, agreement workspace actions, and governance event workflows now have a shared service layer. Operator commands have been split into their own module. The next useful service candidates are intake-quality caching and portable-validation state, and `application_core.py` should continue to split as the service surface grows.

6. Intake quality aggregation can be slow on a cold path.
   A direct in-process probe previously took about `108s` before subsequent calls returned quickly. The endpoint is functionally healthy, but it should get caching or a lighter summary path before agents rely on it for frequent polling.

7. Frontend mass is becoming a maintainability risk.
   `static/app.js` and `static/style.css` are both large, and the CSS has accumulated broad override sections. The interface works, but future UI work should split views and style layers before the shell becomes harder to reason about.

8. Report/data endpoints previously had a concurrency-sensitive dependency-context risk.
   Analysis, audit, and scenario-governance dependency scopes are now context-local so concurrent report, chart, and audit requests cannot clear each other's active dependency state. A regression test now covers thread isolation for analysis dependency context.

9. Cohort scope needed an explicit anchor before entitlement work expanded.
   The current pay-table benchmark lane is now documented as `standard_band_core`, with controlled reference notes under `data/reference/cohorts`. This should keep ordinary Band/Level matrices separate from modifiers, service-area tags, specialist schedules, and external/excluded groups as entitlement extraction grows.

## Recommended Next Actions

### 1. Continue The Application Core Migration

The first application-core pass now exists:

- `src/benchmarking_data_factory/workbench/application_core.py`
- `app.state.workbench_services`
- service-backed `/api/agent/status`
- service-backed `/api/agent/catalog`
- service-backed `/api/agent/actions`
- service-backed `/api/agent/io`
- service-backed `/api/wiki/status`
- service-backed `/api/wiki/catalog`
- service-backed wiki run, document-map, reference-input, clause-library, question, learning-backlog, language-map, and artifact discovery
- service-backed analysis asset reads and rebuilds
- service-backed intake/reference/audit route adapters
- service-backed agreement workspace route adapters for councils, source PDF/page evidence, overview generation, uplift-rule actions, and pay-table workflows
- service-backed governance event route adapters for scenarios, overrides, notes, constructed pay tables, governed-set promote/unwind/read actions, and rate-cap confirmations
- service-backed packaging profile and package-plan discovery for agent I/O
- service-backed report asset contract validation and distribution-point companion manifest emission
- service-backed report asset lifecycle status updates
- service-backed report export generation for distribution-point CSV/SVG/PNG/XLSX/DOCX/PPTX outputs
- service-backed operator command discovery for setup, run, test, smoke, package, dependency-bundle, unpack, and handoff commands

Next step: add a lightweight `IntakeQualityService` for cacheable intake QA status, capture Ubuntu package/setup/run proof through a structured portability validation surface, and split `application_core.py` once the next service boundary is clear.

### 2. Prove Portability

The first portability scaffold now exists:

- `PORTABLE_MANIFEST.json`
- `scripts/setup-windows.ps1`
- `scripts/setup-ubuntu.sh`
- `scripts/run-windows.ps1`
- `scripts/run-ubuntu.sh`
- `scripts/package-workbench.ps1`
- `scripts/package-workbench.sh`

Next step: repeat package/setup/run on Ubuntu or WSL, then smoke-test governed-data and source-evidence package profiles against the service-reported package plans.

### 3. Stabilise The Chart Asset Contract

The initial contract now exists:

- `REPORT_ASSET_CONTRACT.md`
- `data/analysis/distribution-point-analysis.asset.json`
- `exports/report-assets/distribution_point_analysis_default`

Next step: apply brand/report styling rules to the generated exports, then add richer operator review metadata such as reviewer identity, review notes, and report-pack grouping.

### 4. Focus The Next QA Pass On Intake Identity

Use Source Intake as the next governance-hardening area:

- unmatched active candidates
- superseded records in working set
- runner-up review
- renamed councils
- multi-council agreements
- source PDF health

The goal is not to make the queue smaller by hiding complexity. The goal is to make each unresolved source state explainable and actionable.

### 5. Treat Brand Guide As Design Input

The new `brand-guide` material should be connected back to the app:

- confirm final visual direction from the candidate boards,
- map brand tokens to `static/shell/brand-tokens.css`,
- define chart colour rules,
- define report-asset export styling,
- keep the operator UI professional without turning it into a client-facing portal.

### 6. Extend Stable Developer Commands

Already added through `OperatorCommandService`:

- backend test commands
- smoke test commands
- run app commands
- `npm run lint`
- package/unpack commands
- dependency-bundle commands
- handoff document discovery

This should reduce reliance on remembered shell incantations and make future agent I/O safer.

### 7. Build Entitlements Around The Cohort Scaffold

The current system should be treated as `standard_band_core`, not as a generic employee bucket. For each entitlement family, first decide whether the clause applies to:

- the standard band core;
- a modifier or service-area tag inside that core;
- a specialist schedule inside the EBA;
- or an external/excluded group outside the current benchmark lane.

Next step: turn the `Additional Annual Leave` success into the repeatable standard-employee entitlement loop. For each reference-exemplar entitlement, define the profile, bind it to `standard_band_core`, search the source EBAs, extract source-linked values, compare the recreated numbers with the reference, encode any learned aliases or exclusions, and move on only after the entitlement is matched or all reasonable reasoning routes are exhausted.

First loop result: `Family and Domestic Violence Leave` now has a source-ref evidence profile at `wiki/artifacts/entitlement-clause-evidence/family-domestic-violence-leave-clause-evidence.json`. The entitlement builders now resolve each comparator council to its latest known canonical agreement before searching cached text. With that correction, Ballarat resolves from `AE507751` to `AE526078` and the 5-day support-leave value is source-backed. The profile finds source-backed clauses for all 10 reference comparator councils, fully recreates 9 reference value rows, and flags Wyndham as source-backed but not quantified because the latest cached EBA says paid leave or flexibility may be considered without stating 20 days. These differences are preserved as source-backed reasoning rather than forced into the reference numbers.

## Suggested Immediate Order

1. Repeat package/unpack/setup/run on Ubuntu or WSL.
2. Smoke-test `with_governed_data` and `with_source_evidence` package profiles.
3. Apply brand/report styling rules to generated distribution-point exports.
4. Run an intake identity QA pass focused on unmatched active and visible superseded records.
5. Continue the exhaustive normal-staff entitlement recreation loop from the Ballarat exemplar, using `Family and Domestic Violence Leave` as the first completed post-annual-leave cycle.
6. Connect the `brand-guide` candidate boards to app/report asset token decisions.
