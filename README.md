# EBA Workbench

Human-in-the-loop extraction and governance workbench for Victorian local government enterprise agreements.

This app is an internal operator cockpit, not a client-facing portal. It is where the operator reviews source intake, governs extracted pay tables and uplift rules, explores chart ideas, and prepares report assets for later customer-facing consumption.

## Collaboration

See [GITHUB_COLLABORATION.md](GITHUB_COLLABORATION.md) for the GitHub collaboration plan and [machine-notes](machine-notes/) for Windows/Linux handoffs.

## Quick Run

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\run-windows.ps1
```

Ubuntu:

```bash
bash scripts/setup-ubuntu.sh
bash scripts/run-ubuntu.sh
```

Then open:

```text
http://127.0.0.1:8765
```

## Offline Setup

When the target machine cannot reach or trust PyPI, build and package a wheelhouse first:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-offline-deps.ps1 -PipTrustedHost
powershell -ExecutionPolicy Bypass -File scripts\package-workbench.ps1 -Profile runtime_code -IncludeDependencyBundle
```

Then on the target:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -Offline
```

Ubuntu uses the same `vendor/python-wheels` layout:

```bash
OFFLINE=1 bash scripts/setup-ubuntu.sh
```

## Agent Discovery

The app exposes a read-only discovery layer for Codex, OpenClaw, or another agent runner:

- `/api/agent/status`
- `/api/agent/catalog`
- `/api/agent/actions`
- `/api/agent/io`

The matching manifest is [workbench-agent.json](workbench-agent.json).

## Portable Packaging

The portability manifest is [PORTABLE_MANIFEST.json](PORTABLE_MANIFEST.json).

Default runtime packages include source, tests, scripts, docs, lightweight reference data, and report asset metadata. They exclude secrets, source PDFs, governed YAML, generated registers, bulky analysis JSON, virtual environments, dependency caches, exports, and logs.

## Current Verification

As of 2026-05-02:

- Windows runtime package/unpack/setup/run has been smoke-tested.
- Windows offline Python wheelhouse package/setup/run has been smoke-tested.
- Full test suite passed locally: `428 passed`.
- Frontend lint reports `0` errors and `1` existing unused-function warning.
- Ubuntu setup scripts exist but still need to be proven on a Linux or WSL machine.

## Key Docs

- [PRODUCT_ARCHITECTURE.md](PRODUCT_ARCHITECTURE.md)
- [CURRENT_STATE_AND_NEXT_ACTIONS.md](CURRENT_STATE_AND_NEXT_ACTIONS.md)
- [REPORT_ASSET_CONTRACT.md](REPORT_ASSET_CONTRACT.md)
- [GITHUB_COLLABORATION.md](GITHUB_COLLABORATION.md)
