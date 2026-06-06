# Product Architecture

Status: working product direction as of 2026-05-03.

This document turns the project conversation into a stable architecture note for the EBA Workbench. It should be updated as the product moves from local governed workbench to a more complete Municipal Benchmark reporting platform.

## North Star

The EBA Workbench is a governed, human-in-the-loop analysis tool for Victorian local government enterprise agreements.

Its job is to help an analyst move from public source material to trusted benchmark data:

1. Find and freeze the right agreement source.
2. Confirm council scope and agreement lineage.
3. Review the source PDF with extraction support.
4. Accept, correct, or reject extracted entities.
5. Validate rules and projected tables.
6. Promote reviewed outputs into governed data sets.
7. Use those governed data sets for comparison, charts, audit, and reporting.

The product principle is:

> Replicate capability, not clutter.

OpenClaw and the earlier workbench are reference material. They define useful workflows, edge cases, data shapes, and lessons learned. This project should not preserve old structure for its own sake. The target is a clean Codex-native Municipal Benchmark workbench with portable, well-named module contracts.

## Product Intent

The intent is not just to extract data from enterprise agreements. The intent is to produce defensible benchmark evidence that an analyst can trust, explain, correct, and reuse.

The workbench itself is not a client-facing product. It is the operator interface for human-in-the-loop governance, machine improvement, chart development, and production of assets that can later be consumed in customer-facing reports.

This matters because EBAs are not clean databases. They are legal and operational documents with inconsistent language, historical council changes, embedded tables, superseded records, and local exceptions. The product should therefore support judgement rather than pretend everything can be fully automated.

The intent has several layers:

- Analyst intent: reduce manual burden while keeping the analyst in control.
- Governance intent: preserve why a value was accepted, rejected, promoted, or unwound.
- Evidence intent: keep every important value connected to source material.
- Data intent: turn messy agreement documents into comparable governed entities.
- Improvement intent: capture extraction failures, edge cases, and corrections so the machine workflow improves over time.
- Exploration intent: provide a place to test chart ideas, compare cohorts, and shape the story before anything becomes a report asset.
- Design intent: make the operator experience feel calm, professional, and decision-ready, at a business standard suitable for serious analytical work.
- Product intent: grow from a local Codex workbench into the production engine behind reusable Municipal Benchmark outputs.

The system should be opinionated about process, but humble about uncertainty. When the source is unclear, the product should expose that uncertainty and ask for a decision. When the source is clear, the product should make the correct action easy.

The problem being solved up front is not presentation alone. It is the disciplined conversion of messy public agreements into governed, reusable benchmark evidence, with enough design quality that the operator can work confidently and produce report-ready material without rework.

## Product Posture

This is currently a local-first governed workbench.

That means:

- The trusted boundary is the local project folder and the person operating Codex Desktop.
- Heavy enterprise permissions are not required for the current stage.
- Governance is still required, even in local mode.
- Failed extraction must never look like a valid empty result.
- Analyst decisions must be visible, reversible where practical, and traceable to source evidence.
- The app should bind to localhost for normal use.
- Authentication can be added later if the product becomes a shared web application.

The product should feel like a premium civic intelligence workbench, not a prototype admin panel. It does not need to explain itself like a public website, but it should hold a business-grade design standard because the operator is making high-value judgement calls and preparing assets that may flow into customer-facing material. The current Municipal Benchmark visual system should remain restrained, data-heavy, professional, and evidence-first.

## Current User Surfaces

The frontend is a plain static application served by FastAPI:

- `static/index.html` provides the page structure.
- `static/app.js` owns rendering, view state, and button behaviour.
- `static/api-client.js` owns shared frontend API request and error handling.
- `static/report-export-state.js` owns the report-export catalog/cache/lifecycle state helper.
- `static/style.css` and `static/shell/*.css` own the Municipal Benchmark visual system.
- There is no React, Vue, Svelte, Tailwind, or frontend build step.

The current product surfaces are:

- Source Intake: registry candidates, PDF fetch state, scope gates, intake quality, and accept/reject/review decisions.
- Review Board: agreement review matrix and section status across the working set.
- Agreement Workspace: source PDF, section playbooks, extraction, editing, validation, uplift rules, scenarios, and governed promotion.
- Data Sets: governed entity views for uplift rules, pay tables, charts, and council reference data.
- Council Audit: single-council lineage, source, review, and governed data document.
- Settings: LLM provider status, rate-cap controls, and controlled reference maintenance.

The interface can support report production without becoming the report itself. The operator view can contain controls, diagnostics, provenance, and experimental chart states that would not belong in a customer-facing report.

## Architecture Shape

The current implementation has a large FastAPI app in `main.py` plus focused domain modules under `src/benchmarking_data_factory`.

The desired architecture is:

- FastAPI remains the local application host and API boundary.
- Static HTML/CSS/JS remains the frontend until there is a clear reason to introduce a framework.
- Domain logic should live in `src/benchmarking_data_factory`, not in UI rendering code.
- `main.py` can orchestrate routes, but reusable logic should continue moving into project modules.
- Data decisions should be stored as structured files, not only in browser state.
- Reference data should have one canonical loading surface rather than duplicated parsing.
- Runtime paths should derive from the installed project root, not from a hard-coded developer machine path.

Current backend module areas:

- `phase1`: Fair Work discovery, registry fetch, candidate construction, PDF freezing.
- `workbench`: canonical agreement helpers, intake candidates, source documents, LLM boundary, review sections, report values.
- `reference`: canonical council and council master datasets.
- `spatial`: council geography and boundary lookup.
- `uplift_rules`: rule extraction, schema, suggestions, accepted rules, rate-cap support, gold output.
- `scenario_testing`: rule normalisation, projection, scenario validation, projected table construction.
- `governed_set`: promotion, classification, and unwind of governed outputs.
- `conditions`: conditions extraction schema and section support.

## Application Core

The workbench now has an explicit application-core layer:

`src/benchmarking_data_factory/workbench/application_core.py`

This layer is the stable place for shared workbench services that routes, agent endpoints, packaging scripts, and future automation can call without duplicating path logic or bypassing governance.

Current application-core services:

- `WorkbenchPathService`: owns canonical project paths, directory cataloging, and data-set discovery.
- `PackagingService`: owns portable package manifests, package-profile resolution, script/command discovery, package plans, and data-presence detection for `runtime_code`, `with_governed_data`, and `with_source_evidence`.
- `PackageProfileService`: backwards-compatible alias for older package-profile callers.
- `AgentDiscoveryService`: backs `/api/agent/status`, `/api/agent/catalog`, `/api/agent/actions`, and `/api/agent/io`.
- `AnalysisAssetService`: centralises analysis asset reads, rebuilds, and derived distribution-point asset refreshes.
- `ReportAssetService`: owns the report asset contract surface, validates report-ready companion manifests, emits the distribution-point analysis `.asset.json` manifest whenever the raw analysis asset is materialised, and updates governed lifecycle status.
- `ReportExportService`: turns contract-valid distribution-point report assets into concrete CSV, SVG, PNG, XLSX, DOCX, PPTX, and export-manifest files under `exports/report-assets`.
- `OperatorCommandService`: publishes stable setup, run, test, smoke, package, unpack, dependency-bundle, and handoff commands with readiness, platform, governance, and agent-safety metadata. It does not execute commands directly.
- `IntakeService`: centralises canonical council reference reads, intake quality, candidate lists, registry fetches, candidate decisions, and source freezing.
- `AgreementWorkspaceService`: centralises council workspace reads, split/single-council actions, section status changes, source PDF/page evidence, overview generation, uplift-rule actions, and pay-table extraction/save/validation helpers.
- `GovernanceEventService`: centralises scenario runs, scenario overrides and notes, constructed pay tables, governed-set promote/unwind/read actions, and rate-cap confirmations.
- `WorkbenchServices`: composes the service layer and is attached to `app.state.workbench_services` during app bootstrap.

Route modules should stay thin. Their job is to parse HTTP inputs, call the relevant application service, and return the response. Shared behaviour should move into service classes instead of growing inside route handlers, static frontend code, or one-off scripts.

Dependency context used by analysis, audit, and scenario-governance internals must be request-local. The app uses context-local dependency scopes for these modules so concurrent report, chart, and audit requests cannot clear or overwrite each other's active dependency state.

The next service candidates are:

- `IntakeQualityService`: make the expensive intake-quality summary cacheable and agent-friendly.
- `ReportPresentationService`: connect generated report exports to an operator-facing report/export surface.
- `PortableValidationService`: capture Windows and Ubuntu package/setup/run smoke results as structured service data.

## Report Assets

The workbench can be exploratory without letting report material become loose. Chart and report outputs should move through a report asset contract before they are treated as reusable customer-facing evidence.

The first implemented asset family is distribution-point analysis:

- raw analysis: `data/analysis/distribution-point-analysis.json`
- companion manifest: `data/analysis/distribution-point-analysis.asset.json`
- contract: `REPORT_ASSET_CONTRACT.md`

`ReportAssetService` now generates and validates the companion manifest when distribution-point analysis is materialised. The manifest records title candidates, source dataset version, filters, metric definition, visual encoding, quality flags, provenance, operator note, export targets, and lifecycle status. This keeps chart ideas connected to governed evidence while still letting the operator experiment before declaring an asset `report_ready`.

`ReportExportService` now uses that contract-valid manifest as the gate for actual file output. The first distribution-point export family is available through:

- export endpoint: `/api/analysis/distribution-point-analysis/exports`
- lifecycle endpoint: `/api/analysis/distribution-point-analysis/report-asset/status`
- download endpoint: `/api/analysis/distribution-point-analysis/exports/{format_name}`
- export folder: `exports/report-assets/distribution_point_analysis_default`
- concrete formats: CSV, SVG, PNG preview, XLSX, DOCX, PPTX
- export manifest: `distribution_point_analysis_default.exports.json`

The Charts data-set view now includes an operator-facing export panel for the generated files and the lifecycle controls for moving the asset through `draft`, `reviewed`, and `report_ready`. This is intentionally an operator asset-production surface, not a client-facing report. The generated files are consumption assets that can be reviewed, styled further, or placed into downstream customer-facing material once the operator is satisfied with the data and framing.

## Portability and Distribution

The workbench needs to become portable. At some point it should be able to package itself as a zip, move to another machine or workspace, unzip, run a setup script, and repair or rewrite any directory-specific configuration.

This is not just convenience. Portability protects the project from becoming trapped inside one local folder, one Codex Desktop setup, or one operating system.

Portability requirements:

- No source code should depend on absolute local paths such as one user's home directory.
- Project paths should resolve from the repo root or an explicit workspace root.
- Local secrets must stay outside packaged artifacts unless the operator explicitly exports them.
- Runtime caches and generated artifacts should be optional in a package.
- Source evidence and governed data should be packageable with a manifest when needed.
- The package should include a version stamp, environment summary, and integrity manifest.
- Unpack scripts should repair local path references and create any missing runtime folders.
- The app should support both Windows and Ubuntu setup paths.

The likely distribution shape is:

- `scripts/package-workbench.*`: create a portable zip from the current project.
- `scripts/unpack-workbench.*`: unpack and rewrite local configuration for the target directory.
- `scripts/setup-windows.ps1`: create a Windows virtual environment and install dependencies.
- `scripts/setup-ubuntu.sh`: create an Ubuntu virtual environment and install dependencies.
- `scripts/build-offline-deps.*`: prepare a local dependency bundle under `vendor`.
- `scripts/run-windows.ps1`: start the local FastAPI app on Windows.
- `scripts/run-ubuntu.sh`: start the local FastAPI app on Ubuntu.
- `PORTABLE_MANIFEST.json`: record included data sets, excluded secrets, app version, and path rewrite rules.

Path rewrite should be config-driven. The preferred pattern is to avoid rewriting source code at all by moving path assumptions into a small local config file that can be regenerated after unpacking.

Offline setup is now part of the portability shape. The runtime package should normally stay lean, but the operator can deliberately include `vendor/python-wheels` and optional `vendor/npm-cache` when the target environment cannot reach or trust PyPI/npm. Python wheels are the first-class offline runtime path; Node tooling remains optional because it supports lint/developer checks rather than app startup.

`PackagingService` is the application-core owner for this portability contract. It does not run shell scripts directly; it makes package profiles, resolved include/exclude rules, unpack/setup script locations, command keys, dependency-bundle options, and safety flags visible to the app and to agent discovery endpoints. Script execution should remain an operator-intent action.

## Agent I/O Boundary

The workbench should expose a discoverable I/O layer so an agent can understand how to interact with it, whether that agent is Codex, OpenClaw, or another automation runner.

The agent I/O boundary should make the app self-describing:

- where the project root is,
- what data sets exist,
- what actions are available,
- what status each workflow is in,
- what files are safe to read or write,
- what endpoints are available,
- what commands start, test, package, and repair the app.

The likely shape is a small machine-readable manifest plus stable API endpoints.

Possible manifest:

- `workbench-agent.json`: project identity, version, supported platforms, commands, key directories, API routes, data contracts, and safety rules.

Possible endpoints:

- `/api/agent/status`: app health, provider readiness, active workspace, and version.
- `/api/agent/catalog`: discoverable data sets and governed entity types.
- `/api/agent/actions`: supported actions such as fetch, freeze, extract, validate, promote, unwind, export, package.
- `/api/agent/io`: readable and writable file surfaces, with safety boundaries.

The agent layer should not bypass governance. It should call the same application services as the UI, record the same audit events, and respect the same source, review, promotion, and unwind rules.

`OperatorCommandService` makes the non-API operational surface discoverable through agent endpoints. It groups commands into setup, run, test, smoke, package, and handoff categories, separates agent-safe verification commands from operator-intent commands, and advertises key handoff documents for another machine or agent. This gives Codex, OpenClaw, and future Ubuntu machines one stable command map without granting automatic execution of risky or long-running operations.

`ReportExportService` adds a governed output surface to that same agent layer. Agent status, catalog, actions, and I/O can now tell another machine which report formats are implemented, where the exported files live, and which action materializes the distribution-point report asset.

## Wiki Layer

The workbench should grow a governed wiki layer from extracted EBA text. The wiki goal is captured in:

- `WIKI_LAYER_GOAL.md`

The clause-backed entitlement method is now named the `Clause Evidence Graph`. Its hard boundary is:

- Source Document.
- Document Spine.
- Clause Evidence Graph: clause containers, feature cards, reference edges, evidence spans, and review/governance state.
- Entitlement Engine: governed-feature queries, entitlement definitions, value/unit/scope normalisation, and benchmark measures.
- Benchmark, report, and wiki views.

The Clause Evidence Graph owns source-backed structure and evidence. The Entitlement Engine owns benchmark interpretation. The Reporting Layer owns presentation. Governance decides what is safe to promote.

The entitlement engine sits above the Clause Evidence Graph. It does not own source truth. It queries clause containers, feature cards, evidence spans, and reference edges, then converts governed feature cards into normalised benchmark measures. Where governance is absent or incomplete, it emits explicit uncertainty states rather than pretending a benchmark fact exists.

The preferred document strategy is whole-document clause carding with tiered depth. Every detected clause or subclause can become a lightweight source container with heading path, page range, raw text, probable family tags, cross-references, and review state. Feature cards should be reserved for specific benchmarkable spans or rules. This creates a complete document spine for search, absence review, and cross-reference analysis without forcing every clause into premature entitlement interpretation.

The next technical layers should be added as adapters and evaluation lanes, not as ungoverned judgement. The priority order is parser diversity, evidence coordinates and text hashes, strict clause/feature/reference schemas, schema-constrained LLM candidate extraction, reference-edge extraction, truth-set regression tests, table-specific extraction, graph retrieval over the Clause Evidence Graph, human-in-the-loop scope review, and read-only or proposal-only agent access. LLM output that fails schema validation is a failed extraction attempt, not data.

The QA pack makes locator outputs reviewable. It does not make them true. Truth enters the system only through explicit review decisions and governance promotion. The gold review layer must keep clause found, feature found, entitlement presence, quantified value found, reviewed absence, and governed benchmark measure as separate states. Gold seed rows are review targets, not gold answers. Machine hints may assist review but cannot populate review decisions without human confirmation.

The review lifecycle is `not_reviewed` to a reviewed semantic decision, then `eligible_for_governance`, then `governed_for_scope`. `governed_for_scope` must never be reachable directly from machine output or seeded gold rows. It requires an explicit review decision, reviewer metadata, a review scope, and a source evidence span or corrected evidence span.

Codex may suggest. Human decides. Governance promotes. Codex simulation suggestions must live in a sidecar file, reference gold review IDs, require human confirmation, and never populate review metadata, eligibility, or governance fields.

Human adjudication should happen through generated worksheets, not direct hand-editing of gold seed JSONL. The worksheet joins gold targets, QA evidence, and Codex advisory suggestions while leaving human review columns blank. Completed worksheets should be applied through a validator that writes reviewed gold records only after transition rules pass.

The wiki should become the long-term knowledge layer for individual agreements and for set-level learning across agreements. Its first scope is `entitlements_conditions_benefits`: clause and context mapping for entitlement, condition, benefit, obligation, exclusion, and local-language patterns. Pay tables, uplift rules, and standard Band/Level benchmarking remain in their existing governed lanes.

The first practical wiki step should be document mapping. Each EBA should get a source-linked map of headings, clause functions, page ranges, clause/context relevance, specialist/excluded context signals, unusual language, and ambiguous structure. Those maps can then support wiki pages, language maps, cross-agreement patterns, issue records, and report or briefing artifacts.

The next layer above document mapping is the semantic entitlement layer. This layer organises knowledge under a human-friendly entitlement taxonomy, then requires supportable facts underneath each concept: source references, presence/absence state, quantified value and unit where measurable, comparator basis, target-council posture, and review state. This is the bridge from tagged text to usable downstream analysis such as entitlement benchmark reports.

The first semantic entitlement pilot is a comparator seed based on the user-supplied Ballarat entitlement benchmark report. The wiki should use the report's comparator councils and taxonomy as a thought starter, then attempt to recreate the output from source EBA evidence for standard employees only. The target quality bar is about 95% row-semantic agreement, with evidence-backed disagreements and specialist-cohort exclusions surfaced for operator review. The report chooses the starting councils and shape; the latest known source EBA for each council remains authoritative.

The first clause-backed entitlement method is profiled evidence search. For a selected entitlement such as `Additional Annual Leave`, the builder defines inclusion terms, exclusion terms, standard-employee scope, expected value units, and source-search absence rules. It then searches cached agreement text, extracts page and clause evidence, separates out-of-scope annual leave language, and feeds the source-backed finding, values, and page reference into the wiki display while retaining the original report finding as comparator context.

The profile must also explain how it found its hits. The evidence artifact records the exact page-level method, search terms, candidate and positive patterns, scope-control signals, scoring rule, accepted clauses, rejected lookalikes, A/B cohort measurement, and refinement levers. This lets the workbench improve the machine across agreements rather than merely generate a static page.

The `Additional Annual Leave` profile now carries the first learning loop: a definition anchored to leave above the NES or ordinary annual leave baseline, accepted subclasses, adjacent/excluded subclasses, validation-batch measurement, candidate subclass counts, and an ad hoc CLI path for processing supplied agreements on demand. This is the shape future entitlement profiles should follow: run the profile, inspect false positives and missed aliases, encode the learning into the profile, and rerun against a fresh validation batch.

For scale checks, entitlement profiles can run across every agreement with cached page text. The all-cached run should preserve the same definition, inclusion/exclusion boundary, subclass rules, and A/B trail, then produce current coverage metrics across the whole local corpus. This keeps the wiki moving toward on-demand agreement processing rather than fixed report recreation.

The next entitlement architecture goal is an exhaustive standard-employee recreation loop over the reference benchmark. The workbench should process each in-scope entitlement row one at a time, using `Additional Annual Leave` as the reusable pattern: define the entitlement, constrain it to `standard_band_core`, resolve each council to its latest known canonical agreement, search source EBAs, extract source-linked values, compare the recreated numbers with the reference, record the reasoning, and either match the reference or leave a clear exhausted-route explanation. A profile is not complete merely because it produced a plausible answer; it should account for aliases, cross-references, lookalikes, specialist exclusions, source gaps, and comparator interpretation differences before moving to the next entitlement.

The wiki should mostly run as a background improvement loop, but it also needs a front-facing operator cockpit. The background loop should pursue standing mission objectives such as mapping unmapped EBAs, strengthening weak maps, proposing language aliases, finding repeated clause patterns, and identifying support artifacts. The cockpit should show run history, open questions, proposed improvements, confidence gaps, and review actions so the operator can steer the system without having to manually drive every step.

The wiki must distinguish raw extracted text, generated suggestions, reviewed wiki knowledge, and governed data sets. It should improve over time through a visible learning backlog of tag proposals, synonym mappings, weak extractions, conflicts, and candidate support artifacts. The system can want to improve by continuously proposing better maps, tags, and artifacts, but accepted knowledge should change through review and supersession rather than silent rewriting.

## Data Stores

The repo should keep the data lifecycle explicit:

- `documents/immutable`: frozen source PDFs.
- `data/bronze`: fetched or discovered source-stage data.
- `registers`: document hashes, source document logs, fetch registers, and other audit registers.
- `canonical`: per-agreement reviewed workspace state.
- `wiki`: document maps, accepted wiki pages, language maps, pattern notes, issue records, learning backlog, and support artifacts.
- `scenario-overrides`: explicit analyst scenario notes and overrides.
- `artifacts`, `exports`, and `var`: generated outputs, exports, and runtime support files.

The important rule is that every promoted value should be explainable from:

- a source agreement or reference record,
- a page, clause, table, or extracted evidence note where available,
- an analyst decision or acceptance event,
- a validation or scenario result,
- and a governed promotion record.

## Cohort And Entitlement Scope

The current pay-table benchmark system is the `standard_band_core`.

This is not just one cohort among many. It is the anchor the existing governed pay-table, scenario-testing, and distribution work is built around. In practical terms, `standard_band_core` means ordinary numeric Band/Level employee matrices, usually Band 1-10 with levels such as A-D or 1-4, where the row can be reduced to a stable benchmark cell such as `band_03_level_B`.

The project should separate cohort categories from award or instrument links:

- Cohort category asks: how should this employee group behave in the EBA workflow?
- Award or instrument link asks: where might the legal or industrial source come from?

A new cohort category should be created only when the agreement evidence shows materially different treatment: a separate pay table, progression, award logic, hourly-only structure, professional schedule, or entitlement regime. If a work area, occupation label, or department name still resolves to the ordinary Band/Level matrix, it remains inside `standard_band_core` as an alias, modifier, or service-area tag.

The controlled reference scaffold for this concept lives at:

- `data/reference/cohorts/README.md`
- `data/reference/cohorts/cohort-nomenclature.yaml`

The intended layers are:

- `standard_band_core`: current benchmark lane and default scope for general employee clauses.
- `standard_band_modifier`: basis or work-pattern tags such as casual, part-time, shiftworker, on-call, higher duties, or redeployment affected.
- `service_area_inside_standard_bands`: work-area tags such as indoor, outdoor, library, local laws, parking, tourism, recreation, waste, community services, or professional/technical where the ordinary matrix still applies.
- `specialist_schedule_inside_eba`: groups that appear inside an EBA but use separate schedules, progressions, or entitlement treatment, such as maternal and child health nurses, immunisation nurses, early childhood teachers, specialist aquatic schedules, home care schedules, or senior officers.
- `external_award_or_excluded_occupation`: groups expressly carved out, externally governed, or outside the current benchmark workflow.

Entitlement extraction should use the same model. Every entitlement family should first identify whether the clause applies to `standard_band_core`, to a modifier/tag inside that core, or to a non-core specialist/excluded cohort. This lets the knowledge base grow without letting every occupation name become a new category.

## Governance Model

The workbench should use governance states rather than heavy user permissions at this stage.

Core states:

- draft: detected or extracted but not relied on.
- needs_review: requires analyst judgement.
- accepted: accepted for the current workspace.
- rejected: explicitly not used.
- promoted: moved into a governed data set.
- unwound: removed from the governed set with a reason or traceable action.

Required governance behaviours:

- Keep source PDF hashes and metadata.
- Preserve AE IDs, agreement names, print IDs, matter IDs, publication year, and source URLs where available.
- Keep council identity resolution visible, especially for renamed councils such as Moreland to Merri-bek.
- Store before/after decisions for material changes.
- Keep warnings visible for source gaps, weak metadata, unmatched councils, superseded agreements, and unresolved scope.
- Allow governed data to be unwound without deleting the evidence trail.
- Make rate-cap assumptions explicit and controlled.

## Module Contracts

These are the durable product concepts that should remain portable even if the code is later split or rebuilt.

### IntakeRecord

Represents a candidate agreement before extraction begins.

Expected payload:

- AE ID and agreement metadata.
- Fair Work registry fields.
- source PDF fetch state.
- PDF hash and file reference when frozen.
- council match and confidence.
- scope decision.
- supersession status.
- intake decision state.

### SourceDocument

Represents frozen evidence.

Expected payload:

- immutable local path.
- source URL.
- content hash.
- file size and health check.
- fetch timestamp.
- fetch register linkage.

### ScopeDecision

Represents whether a source belongs in the benchmark set.

Expected payload:

- canonical council match.
- match basis.
- confidence or match strength.
- unresolved/multi-council flags.
- renamed-council handling.
- analyst decision and note.

### ReviewSection

Represents a workspace section such as Overview, Pay Tables, Uplift Rules, Conditions, or Entitlements.

Expected payload:

- status.
- source evidence references.
- extracted draft values.
- accepted values.
- validation messages.
- analyst notes.

### AuditEvent

Represents a traceable decision or system action.

Expected payload:

- event type.
- timestamp.
- subject agreement/council.
- before and after values where relevant.
- reason or generated diagnostic.
- source route or tool.

### GovernedEntity

Represents a reviewed item promoted for analysis.

Current examples:

- governed pay-table rows.
- governed uplift rules.
- projected scenario tables.
- council reference records.

Expected payload:

- entity type.
- source agreement and period.
- canonical council identity.
- value fields.
- provenance.
- validation status.
- promotion metadata.

### CohortScope

Represents the employee group boundary for pay, entitlement, and condition extraction.

Expected payload:

- cohort identifier, starting with `standard_band_core`.
- layer such as core, modifier, service-area tag, specialist schedule, or external/excluded.
- source labels and aliases found in the agreement.
- award or instrument links, where relevant, as evidence rather than automatic category boundaries.
- inclusion/exclusion rationale.
- whether the item can be benchmarked through the standard Band/Level matrix.
- analyst review state where the scope is uncertain.

## Workflow

The intended workflow is:

1. Source Intake fetches or loads Fair Work candidates.
2. Intake resolves council identity, source health, supersession, and scope gates.
3. Accepted sources appear on the Review Board.
4. The Agreement Workspace opens the source PDF and the relevant section playbook.
5. LLM-assisted or deterministic extraction creates draft section values.
6. The analyst reviews, edits, validates, and accepts values.
7. Scenario testing checks uplift rules and projected pay tables.
8. Valid reviewed entities are promoted into the governed set.
9. Data Sets and Charts read from the governed set, not from raw extraction drafts.
10. Council Audit presents a single-council trace across source, review, and governed outputs.

For pay and entitlement work, the Agreement Workspace should also keep cohort scope visible: ordinary employee clauses default to `standard_band_core`, while specialist schedules and exclusions should be captured without contaminating the core benchmark lane.

## LLM Boundary

The LLM is an extraction assistant, not the system of record.

The app can use a provider such as Anthropic for text and vision extraction, but the architecture should keep provider-specific behaviour behind a boundary.

Provider-dependent features should:

- fail clearly when the provider is not configured,
- avoid returning valid-looking empty data after an LLM failure,
- record model/provider context where useful,
- keep deterministic validation separate from generated extraction,
- allow future provider options without rewriting the workflow.

## Visual System

The visual language should remain Municipal Benchmark:

- consultancy-grade reporting platform,
- executive civic intelligence,
- clean, structured, data-heavy, restrained,
- strong hierarchy without marketing-page decoration,
- source evidence and status always close to the analyst action.

The benchmark line remains the core motif. Use thin rules, measured separators, and structured data panels rather than decorative clutter.

Operational screens should favour density, scanability, and confidence. The user should always know:

- what source they are reviewing,
- what stage it is in,
- what evidence supports the value,
- what still needs judgement,
- what will happen if they promote or unwind data.

## Quality Bar

The workbench should be considered healthy when:

- backend imports cleanly,
- scoped tests pass,
- ESLint reports no frontend errors,
- Windows and Ubuntu setup paths are documented or scripted,
- local paths derive from the project root,
- source intake does not silently drop important candidates,
- PDF fetch failures are visible,
- LLM provider readiness is visible,
- governed promotion and unwind are tested,
- scenario projection errors recover cleanly in the UI,
- charts and audit views read from governed data,
- the UI remains usable in the Codex Desktop embedded browser.

Current test coverage already suggests important product seams:

- intake candidate modelling and quality,
- council geography and master references,
- LLM boundary and provider status,
- review sections,
- uplift rules and rate caps,
- scenario projection,
- pay-table save and timeline policy,
- governed-set promotion and unwind,
- QA governance events,
- entitlements API.

## Near-Term Roadmap

The next valuable product work is likely:

1. Keep hardening Source Intake council matching and renamed-council identity resolution.
2. Continue separating route orchestration in `main.py` from reusable domain modules.
3. Make governance events more visible in the UI, especially for accept, promote, and unwind.
4. Improve narrow/embedded browser layout for the workspace PDF and review panes.
5. Strengthen conditions and entitlements until they feel like first-class sections rather than secondary experiments.
6. Add the first wiki-layer contract: document maps, clause/context tags, language maps, and learning-backlog records.
7. Add more analyst-friendly audit summaries from the governed data sets.
8. Keep extending controlled reference data, especially council identity, spatial records, and rate caps.
9. Add portability scripts for packaging, unpacking, Windows setup, and Ubuntu setup.
10. Define the first `workbench-agent.json` manifest so Codex, OpenClaw, or another runner can discover the app safely.

## Questions This Leaves Us With

These are worth answering over time, but they do not block current development:

### Intent Questions

1. How should the operator cockpit balance governance work, machine improvement, and chart/report asset creation?
2. Should the product optimise first for speed of extraction, confidence of governance, or quality of report-ready assets?
3. How much should the workbench guide analyst judgement versus simply record analyst judgement?
4. What decisions must always remain human-owned, even when extraction confidence is high?

### Data Questions

1. Should the governed set have explicit version numbers and release labels?
2. What is the next highest-value entity after pay tables and uplift rules: conditions, allowances, classifications, or entitlements?
3. What is the minimum evidence required before an entity can be promoted?
4. How should uncertainty be represented in analysis views: hidden until needed, shown as confidence, or treated as a first-class filter?
5. What wiki page types should become trusted first: document maps, language maps, clause pages, pattern notes, or issue records?

### Workflow Questions

1. What are the core operator modes: intake/governance, extraction correction, model improvement, chart exploration, and asset production?
2. How formal should analyst notes become: free text, structured reason codes, or both?
3. What should be reversible, and what should require a new correction event instead of direct editing?
4. When does the product need shared-user permissions rather than local-first governance?

### Portability Questions

1. Should portable packages include source PDFs and governed data by default, or should those be optional profiles?
2. Should packaging produce a clean runtime bundle, a full development bundle, or both?
3. What is the minimum Ubuntu target: local Ubuntu desktop, WSL, server VM, or all three?
4. Should the app repair local config on first run automatically, or only through an explicit unpack script?

### Agent I/O Questions

1. Should agent I/O be primarily API-based, file-manifest-based, or both?
2. Which actions should an agent be allowed to perform without an operator confirmation?
3. What safety boundary should prevent an agent from writing outside the workbench project root?
4. How should agent actions be recorded in the same governance trail as UI actions?

### Output Questions

1. Which assets should the workbench produce for customer-facing reports: charts, tables, council audit extracts, written observations, or image exports?
2. Should Council Audit remain an operator view, or also generate a report-ready extract?
3. What story should Charts help the operator explore first: statewide distribution, council cohort comparison, agreement timeline, or risk/quality status?
4. What does "ready for report use" mean for a governed data set or chart asset?
