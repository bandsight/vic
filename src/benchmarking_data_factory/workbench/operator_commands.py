from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "error": "invalid_json",
            "path": path.name,
        }


def file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
        }
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": stat.st_size,
        "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


OPERATOR_COMMAND_SPECS = [
    {
        "id": "setup_windows",
        "label": "Setup Windows runtime",
        "category": "setup",
        "platform": "windows",
        "relative_path": "scripts/setup-windows.ps1",
        "governance": "operator_intent_required",
        "writes": [".venv-win", "vendor"],
    },
    {
        "id": "setup_ubuntu",
        "label": "Setup Ubuntu runtime",
        "category": "setup",
        "platform": "ubuntu",
        "relative_path": "scripts/setup-ubuntu.sh",
        "governance": "operator_intent_required",
        "writes": [".venv", "vendor"],
    },
    {
        "id": "run_windows",
        "label": "Run Windows app server",
        "category": "run",
        "platform": "windows",
        "relative_path": "scripts/run-windows.ps1",
        "governance": "operator_intent_required",
        "long_running": True,
    },
    {
        "id": "run_ubuntu",
        "label": "Run Ubuntu app server",
        "category": "run",
        "platform": "ubuntu",
        "relative_path": "scripts/run-ubuntu.sh",
        "governance": "operator_intent_required",
        "long_running": True,
    },
    {
        "id": "test_windows",
        "label": "Run Python test suite on Windows",
        "category": "test",
        "platform": "windows",
        "governance": "safe_verification",
        "safe_to_run_by_agent": True,
    },
    {
        "id": "test_ubuntu",
        "label": "Run Python test suite on Ubuntu",
        "category": "test",
        "platform": "ubuntu",
        "governance": "safe_verification",
        "safe_to_run_by_agent": True,
    },
    {
        "id": "lint_frontend",
        "label": "Lint frontend assets",
        "category": "test",
        "platform": "cross_platform",
        "governance": "safe_verification",
        "safe_to_run_by_agent": True,
    },
    {
        "id": "smoke_windows",
        "label": "Run Windows smoke test",
        "category": "smoke",
        "platform": "windows",
        "relative_path": "smoke_test.py",
        "fallback_command": ".\\.venv-win\\Scripts\\python.exe smoke_test.py",
        "governance": "safe_verification",
        "safe_to_run_by_agent": True,
    },
    {
        "id": "smoke_ubuntu",
        "label": "Run Ubuntu smoke test",
        "category": "smoke",
        "platform": "ubuntu",
        "relative_path": "smoke_test.py",
        "fallback_command": ".venv/bin/python smoke_test.py",
        "governance": "safe_verification",
        "safe_to_run_by_agent": True,
    },
    {
        "id": "package_windows",
        "label": "Package Windows portable bundle",
        "category": "package",
        "platform": "windows",
        "relative_path": "scripts/package-workbench.ps1",
        "governance": "operator_intent_required",
        "writes": ["exports"],
    },
    {
        "id": "package_windows_with_deps",
        "label": "Package Windows portable bundle with dependencies",
        "category": "package",
        "platform": "windows",
        "relative_path": "scripts/package-workbench.ps1",
        "governance": "operator_intent_required",
        "writes": ["exports"],
    },
    {
        "id": "package_ubuntu",
        "label": "Package Ubuntu portable bundle",
        "category": "package",
        "platform": "ubuntu",
        "relative_path": "scripts/package-workbench.sh",
        "governance": "operator_intent_required",
        "writes": ["exports"],
    },
    {
        "id": "package_ubuntu_with_deps",
        "label": "Package Ubuntu portable bundle with dependencies",
        "category": "package",
        "platform": "ubuntu",
        "relative_path": "scripts/package-workbench.sh",
        "governance": "operator_intent_required",
        "writes": ["exports"],
    },
    {
        "id": "build_offline_deps_windows",
        "label": "Build Windows offline dependency bundle",
        "category": "package",
        "platform": "windows",
        "relative_path": "scripts/build-offline-deps.ps1",
        "governance": "operator_intent_required",
        "writes": ["vendor"],
    },
    {
        "id": "build_offline_deps_ubuntu",
        "label": "Build Ubuntu offline dependency bundle",
        "category": "package",
        "platform": "ubuntu",
        "relative_path": "scripts/build-offline-deps.sh",
        "governance": "operator_intent_required",
        "writes": ["vendor"],
    },
    {
        "id": "unpack_windows",
        "label": "Unpack portable bundle on Windows",
        "category": "handoff",
        "platform": "windows",
        "relative_path": "scripts/unpack-workbench.ps1",
        "governance": "operator_target_directory_required",
        "writes": ["target_directory"],
    },
    {
        "id": "unpack_ubuntu",
        "label": "Unpack portable bundle on Ubuntu",
        "category": "handoff",
        "platform": "ubuntu",
        "relative_path": "scripts/unpack-workbench.sh",
        "governance": "operator_target_directory_required",
        "writes": ["target_directory"],
    },
]

OPERATOR_HANDOFF_DOCS = [
    ("current_state", "CURRENT_STATE_AND_NEXT_ACTIONS.md", "Current state and next actions"),
    ("ubuntu_handoff", "UBUNTU_HANDOFF.md", "Ubuntu setup and handoff notes"),
    ("github_collaboration", "GITHUB_COLLABORATION.md", "GitHub collaboration notes"),
    ("product_architecture", "PRODUCT_ARCHITECTURE.md", "Product architecture"),
    ("report_asset_contract", "REPORT_ASSET_CONTRACT.md", "Report asset contract"),
]


@dataclass(frozen=True)
class OperatorCommandService:
    paths: Any

    def manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.paths.root / "workbench-agent.json")

    def commands(self) -> dict[str, str]:
        commands = (self.manifest() or {}).get("commands")
        if not isinstance(commands, dict):
            return {}
        return {key: value for key, value in commands.items() if isinstance(value, str)}

    def command_catalog(self) -> list[dict[str, Any]]:
        manifest_commands = self.commands()
        entries: list[dict[str, Any]] = []
        for spec in OPERATOR_COMMAND_SPECS:
            command_id = str(spec["id"])
            command = manifest_commands.get(command_id) or spec.get("fallback_command")
            relative_path = spec.get("relative_path")
            path = self.paths.root / str(relative_path) if relative_path else None
            file = file_info(path) if path is not None else None
            command_source = "manifest" if command_id in manifest_commands else "fallback" if command else "missing"
            file_ready = True if file is None else bool(file["exists"])
            entries.append(
                {
                    "id": command_id,
                    "label": spec["label"],
                    "category": spec["category"],
                    "platform": spec["platform"],
                    "command": command,
                    "command_source": command_source,
                    "ready": bool(command) and file_ready,
                    "file": file,
                    "governance": spec.get("governance"),
                    "safe_to_run_by_agent": bool(spec.get("safe_to_run_by_agent")),
                    "long_running": bool(spec.get("long_running")),
                    "writes": spec.get("writes", []),
                }
            )
        return entries

    def handoff_documents(self) -> list[dict[str, Any]]:
        return [
            {
                "id": doc_id,
                "label": label,
                "file": file_info(self.paths.root / relative_path),
                "relative_path": relative_path,
            }
            for doc_id, relative_path, label in OPERATOR_HANDOFF_DOCS
        ]

    def command_groups(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for command in self.command_catalog():
            groups.setdefault(str(command["category"]), []).append(str(command["id"]))
        return {key: sorted(value) for key, value in sorted(groups.items())}

    def status(self) -> dict[str, Any]:
        catalog = self.command_catalog()
        handoff_docs = self.handoff_documents()
        missing = [command["id"] for command in catalog if not command["ready"]]
        return {
            "manifest_exists": self.manifest() is not None,
            "commands_ready": not missing,
            "command_count": len(catalog),
            "categories": sorted({str(command["category"]) for command in catalog}),
            "missing_or_unready": missing,
            "handoff_ready": all(doc["file"]["exists"] for doc in handoff_docs),
            "handoff_documents": handoff_docs,
        }

    def actions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f"operator_command_{command['id']}",
                "label": command["label"],
                "kind": "operator_command",
                "category": command["category"],
                "platform": command["platform"],
                "command_key": command["id"],
                "command": command["command"],
                "ready": command["ready"],
                "governance": command["governance"],
                "safe_to_run_by_agent": command["safe_to_run_by_agent"],
                "long_running": command["long_running"],
                "writes": command["writes"],
            }
            for command in self.command_catalog()
        ]

    def catalog(self) -> dict[str, Any]:
        return {
            "commands": self.command_catalog(),
            "groups": self.command_groups(),
            "handoff_documents": self.handoff_documents(),
        }

    def io(self) -> dict[str, Any]:
        return {
            "execution_policy": "OperatorCommandService publishes stable commands and readiness; it does not execute them.",
            "commands": self.command_catalog(),
            "groups": self.command_groups(),
            "handoff_documents": self.handoff_documents(),
            "safety": {
                "write_boundary": str(self.paths.root),
                "operator_intent_required_for": [
                    command["id"]
                    for command in self.command_catalog()
                    if not command["safe_to_run_by_agent"]
                ],
                "agent_safe_verification_commands": [
                    command["id"]
                    for command in self.command_catalog()
                    if command["safe_to_run_by_agent"]
                ],
            },
        }
