# Governed Canonical Layer

Status: initial contract as of 2026-05-07.

## Purpose

`data/governed_canonical/` is the stable raw governed data layer between reviewed project structures and analytical datamarts.

The project flow is now:

```text
Source evidence
-> machine extraction
-> review/governance
-> governed canonical datasets
-> analytical datamarts
-> report assets/products
```

Governed canonical datasets are not raw extraction outputs and they are not report-ready analytical products. They are normalized, lineage-preserving tables derived from records that are either explicitly governed/reviewed/promoted or clearly canonical/reference records.

## Initial Datasets

- `council_agreements`
- `pay_rows`
- `uplift_rules`
- `end_of_band_dollars`
- `evidence_refs`
- `cohort_memberships`
- `readiness_status`
- `source_documents`
- `report_inputs`
- `spatial_reference`
- `entitlement_items`
- `rate_cap_reference`
- `benchmark_questions`

Each dataset writes CSV, JSON, and a status JSON file under:

```text
data/governed_canonical/
```

## Allowed Inputs

- `canonical/*.yaml`, but governed facts must come from promoted/governed project structures.
- `registers/source-document-register.csv`
- `registers/intake-decisions.json`
- `registers/multi-council-decisions.csv`
- `data/reference/victorian-council-master.csv`
- `data/bronze/phase1_source_build/candidate_agreements/candidate_agreements.json`
- controlled reference files such as `data/reference/cohorts/cohort-nomenclature.yaml`
- curated review-layer taxonomy definition overrides such as `data/review/entitlement_definition_overrides.json`
- local public/external reference captures under `src/benchmarking_data_factory/uplift_rules/external/rate-cap/`
- staged wiki strategy artifacts, only with `staged_not_governed` status

## Current Coverage

The current builder pushes useful canonical substrate as far as safe:

- Governed facts: pay rows and uplift rules from governed `sections.uplifts` periods.
- Canonical/reference rows: council identity, cohorts, spatial metadata, source documents, and rate-cap references.
- Staged rows: report inputs, entitlement taxonomy items, and benchmark questions.
- Blocked rows/statuses: missing governance, unclear sources, draft report assets, and non-governed entitlement/question material.

## Required Lineage Fields

Every governed canonical fact row should carry, where applicable:

- source file path
- source agreement ID
- source section/path
- governed timestamp
- review/governance status
- source layer status
- value status for missing, unclear, blocked, staged, or not-applicable values

## Status Vocabulary

Use these statuses rather than silently upgrading uncertainty:

- `governed`
- `canonical_reference_only`
- `staged_not_governed`
- `candidate_not_governed`
- `blocked_missing_governance`
- `blocked_missing_governed_rate_value`
- `not_reviewed`
- `source_unclear`
- `not_applicable`
- `reviewed_not_found`

## Safety Rules

- Do not silently upgrade ungoverned extraction into governed canonical data.
- Do not treat blanks as absence.
- If a useful source object is not fully governed, include it only with an explicit provisional or blocked status.
- Preserve enough source lineage for a downstream reviewer to locate the original project object.
- Analytical datamarts should prefer this layer over direct reads from `canonical/*.yaml`.

## Current Builder

The first builder is:

```powershell
.\.venv-win\Scripts\python.exe scripts\build_datamarts.py
```

It builds governed canonical datasets first, then builds datamarts from those datasets in memory.
