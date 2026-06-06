# GitHub Collaboration Plan

Status: initial repo coordination plan as of 2026-05-02.

## Recommendation

Use the existing `bandsight/vic` repository as the shared coordination point:

`https://github.com/bandsight/vic`

The repository is currently public, so treat it as a source-code and coordination repo only. Do not use the GitHub repo as the default storage location for secrets, source PDFs, governed agreement YAML, bulky generated analysis files, virtual environments, dependency caches, or local runtime output.

## Publish Scope

Safe default scope:

- source code under `src`
- static frontend files under `static`
- tests under `tests`
- setup, packaging, and portability scripts under `scripts`
- lightweight reference data under `data/reference`
- report asset metadata such as `data/analysis/*.asset.json`
- architecture and current-state markdown files
- manifests: `PORTABLE_MANIFEST.json` and `workbench-agent.json`

Excluded by default:

- `.env` and all secret-bearing local config
- `.venv`, `.venv-win`, `node_modules`, and `vendor`
- `documents/immutable`
- `canonical/*.yaml`
- generated `registers`
- `scenario-overrides/*.json`
- `data/bronze`
- bulky generated analysis JSON such as `distribution-point-analysis.json`
- `exports`, `artifacts`, `cache`, `var`, logs, and packaged zip files

## Machine Coordination

Use `machine-notes/` as the low-friction conversation layer between machines.

- `machine-notes/windows.md`: Windows machine status, commands run, blockers, package artifacts created.
- `machine-notes/linux.md`: Ubuntu/WSL status, install notes, failed commands, fixes tried.
- `machine-notes/README.md`: coordination rules and handoff format.

Each machine should leave notes in plain markdown after meaningful work. Keep notes factual: date, machine, branch, command, result, next suggested action.

## Branch Pattern

Suggested branches:

- `codex/windows-portability`
- `codex/linux-portability`
- `codex/report-assets`
- `codex/intake-identity`

Use pull requests when a machine finishes a bounded change. If two agents are working at the same time, prefer separate branches and use markdown notes or GitHub issues for coordination.

## Linux Challenge Workflow

1. Create or update the GitHub repo branch.
2. Push the repo-safe source tree.
3. On the Linux/WSL machine, clone the repo.
4. Run `bash scripts/setup-ubuntu.sh`.
5. If network or certificate issues appear, build or bring across `vendor/python-wheels`, then run `OFFLINE=1 bash scripts/setup-ubuntu.sh`.
6. Start the app with `bash scripts/run-ubuntu.sh`.
7. Record the result in `machine-notes/linux.md`.

## GitHub Text-File Conversation Rules

Keep human/operator intent in normal docs:

- `PRODUCT_ARCHITECTURE.md`
- `CURRENT_STATE_AND_NEXT_ACTIONS.md`
- `REPORT_ASSET_CONTRACT.md`

Keep machine-specific observations in `machine-notes/`.

Do not put API keys, full `.env` files, customer-sensitive material, source PDFs, or generated governed data into markdown notes.

## Repo Decision

The operator chose to repurpose `bandsight/vic`. Because it is public, keep governed data and source evidence out of GitHub unless the repo is made private and the publish scope is deliberately expanded.
