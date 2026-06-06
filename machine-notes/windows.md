# Windows Machine Notes

## 2026-05-02 - Windows - local workspace

Goal:

Prove the app can package, unpack, set up, and run outside its original directory, then add an offline Python dependency path.

Commands run:

- `powershell -ExecutionPolicy Bypass -File scripts\package-workbench.ps1 -Profile runtime_code`
- `powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -PipTrustedHost`
- `powershell -ExecutionPolicy Bypass -File scripts\build-offline-deps.ps1 -PipTrustedHost`
- `powershell -ExecutionPolicy Bypass -File scripts\package-workbench.ps1 -Profile runtime_code -IncludeDependencyBundle`
- `powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1 -Offline`
- `.\.venv-win\Scripts\python.exe -m pytest`
- `npm run lint`

Result:

- Lightweight Windows runtime package, unpack, setup, and run were smoke-tested.
- Offline dependency-bundled package installed from `vendor\python-wheels` and booted successfully.
- Full test suite passed: `428 passed`.
- Frontend lint has `0` errors and `1` existing unused-function warning.
- The live local app on port `8765` reports `68` routes and ready LLM status.

Blockers:

- `git` and `gh` are not available on PATH in this shell.
- WSL command exists, but no Linux distro is installed on this host.
- npm registry TLS is not trusted by this local Node/npm setup, so optional Node tooling cache is scripted but not smoke-tested.

Next suggested action:

Use the `bandsight/vic` repurpose branch as the shared GitHub coordination point, then run the Ubuntu setup proof from a Linux or WSL machine.
