# Ubuntu Handoff

Status: prepared for manual zip transfer as of 2026-05-02.

## Which Zip To Move

Use one of these package profiles:

- `runtime_code`: source code, docs, scripts, tests, static UI, lightweight reference data, and report asset metadata. This is enough to test setup and app startup.
- `with_governed_data`: runtime code plus canonical governed workspace data, registers, scenario overrides, candidate agreement metadata, and generated analysis assets. This is the best first bundle for making the Ubuntu box useful.
- `with_source_evidence`: governed-data bundle plus immutable source PDFs. This is the full heavy bundle.

Do not move `.env` through these packages. Create it from `.env.example` on the Ubuntu box and add provider keys there.

## Ubuntu Commands

On the Ubuntu box:

```bash
mkdir -p ~/eba-workbench-handoff
cd ~/eba-workbench-handoff
unzip /path/to/eba-workbench-with_governed_data-YYYYMMDD-HHMMSS.zip -d eba-workbench
cd eba-workbench
bash scripts/setup-ubuntu.sh
bash scripts/run-ubuntu.sh
```

Then open:

```text
http://127.0.0.1:8765
```

Check agent status:

```bash
curl http://127.0.0.1:8765/api/agent/status
```

## If Python Package Install Fails

If the Ubuntu box has PyPI or certificate trouble, build a Linux-native wheelhouse on that Ubuntu box:

```bash
bash scripts/build-offline-deps.sh
OFFLINE=1 bash scripts/setup-ubuntu.sh
```

Do not use the Windows `vendor/python-wheels` bundle for Ubuntu. Some dependencies have platform-specific wheels.

## If Node/npm Fails

Node tooling is optional for runtime. The setup script skips it by default.

Only use Node tooling when you want frontend lint/developer checks:

```bash
WITH_NODE_TOOLS=1 bash scripts/setup-ubuntu.sh
npm run lint
```

## After The First Ubuntu Run

Update:

```text
machine-notes/linux.md
```

Record:

- OS and Python version,
- exact setup command,
- exact run command,
- `/api/agent/status` result,
- first failure excerpt if anything breaks.

Keep `.env`, API keys, source PDFs, governed YAML dumps, and bulky logs out of GitHub issue comments or public notes.
