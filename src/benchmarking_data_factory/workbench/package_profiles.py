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


def file_count(path: Path, pattern: str = "*") -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob(pattern) if item.is_file())


@dataclass(frozen=True)
class PackagingService:
    paths: Any

    def manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.paths.root / "PORTABLE_MANIFEST.json")

    def agent_manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.paths.root / "workbench-agent.json")

    def profiles(self) -> dict[str, Any]:
        profiles = (self.manifest() or {}).get("profiles")
        return profiles if isinstance(profiles, dict) else {}

    def commands(self) -> dict[str, str]:
        commands = (self.agent_manifest() or {}).get("commands")
        if not isinstance(commands, dict):
            return {}
        return {key: value for key, value in commands.items() if isinstance(value, str)}

    def data_presence(self) -> dict[str, Any]:
        immutable_pdf_count = file_count(self.paths.immutable_dir, "*.pdf")
        reference_documents_dir = self.paths.reference_documents_dir or (self.paths.root / "documents" / "reference")
        reference_pdf_count = file_count(reference_documents_dir, "*.pdf")
        canonical_yaml_count = file_count(self.paths.canonical_dir, "*.yaml")
        scenario_override_count = file_count(self.paths.scenario_overrides_dir, "*.json")
        register_count = file_count(self.paths.registers_dir, "*")
        raw_analysis_exists = self.paths.distribution_point_analysis_json.exists()
        candidate_json_exists = self.paths.candidate_agreements_json.exists()
        return {
            "canonical_yaml_files": canonical_yaml_count,
            "immutable_pdf_files": immutable_pdf_count,
            "reference_pdf_files": reference_pdf_count,
            "scenario_override_files": scenario_override_count,
            "register_files": register_count,
            "raw_distribution_analysis_exists": raw_analysis_exists,
            "candidate_agreements_exists": candidate_json_exists,
            "has_governed_data": bool(
                canonical_yaml_count
                or scenario_override_count
                or raw_analysis_exists
                or candidate_json_exists
            ),
            "has_source_evidence": bool(immutable_pdf_count or reference_pdf_count),
        }

    def default_profile(self) -> str:
        manifest = self.manifest() or {}
        default_profile = manifest.get("default_profile")
        return default_profile if isinstance(default_profile, str) else "runtime_code"

    def available_profiles(self) -> list[str]:
        return sorted(self.profiles().keys())

    def profile_chain(self, profile: str | None = None) -> list[str]:
        selected = profile or self.default_profile()
        profiles = self.profiles()
        if selected not in profiles:
            return []
        chain: list[str] = []
        seen: set[str] = set()
        current: str | None = selected
        while current and current in profiles and current not in seen:
            seen.add(current)
            chain.append(current)
            spec = profiles.get(current) or {}
            extends = spec.get("extends") if isinstance(spec, dict) else None
            current = extends if isinstance(extends, str) else None
        return list(reversed(chain))

    def resolved_profile(self, profile: str | None = None) -> dict[str, Any]:
        selected = profile or self.default_profile()
        profiles = self.profiles()
        if selected not in profiles:
            return {
                "profile": selected,
                "valid": False,
                "error": f"Unknown package profile: {selected}",
                "chain": [],
                "description": None,
                "include": [],
                "exclude": [],
            }
        chain = self.profile_chain(selected)
        include: list[str] = []
        exclude: list[str] = []
        for profile_name in chain:
            spec = profiles.get(profile_name) or {}
            if not isinstance(spec, dict):
                continue
            include.extend(item for item in spec.get("include", []) if isinstance(item, str))
            exclude.extend(item for item in spec.get("exclude", []) if isinstance(item, str))
        selected_spec = profiles.get(selected) or {}
        description = selected_spec.get("description") if isinstance(selected_spec, dict) else None
        return {
            "profile": selected,
            "valid": True,
            "error": None,
            "chain": chain,
            "description": description,
            "include": include,
            "exclude": exclude,
        }

    def inferred_profile(self) -> str:
        presence = self.data_presence()
        if presence["has_source_evidence"]:
            return "with_source_evidence"
        if presence["has_governed_data"]:
            return "with_governed_data"
        return "runtime_code"

    def script_catalog(self) -> dict[str, dict[str, Any]]:
        commands = self.commands()
        script_specs = [
            ("run_windows", "windows", "run", "scripts/run-windows.ps1"),
            ("run_ubuntu", "ubuntu", "run", "scripts/run-ubuntu.sh"),
            ("setup_windows", "windows", "setup", "scripts/setup-windows.ps1"),
            ("setup_ubuntu", "ubuntu", "setup", "scripts/setup-ubuntu.sh"),
            ("package_windows", "windows", "package", "scripts/package-workbench.ps1"),
            ("package_ubuntu", "ubuntu", "package", "scripts/package-workbench.sh"),
            ("build_offline_deps_windows", "windows", "build_offline_deps", "scripts/build-offline-deps.ps1"),
            ("build_offline_deps_ubuntu", "ubuntu", "build_offline_deps", "scripts/build-offline-deps.sh"),
            ("unpack_windows", "windows", "unpack", "scripts/unpack-workbench.ps1"),
            ("unpack_ubuntu", "ubuntu", "unpack", "scripts/unpack-workbench.sh"),
        ]
        catalog: dict[str, dict[str, Any]] = {}
        for key, platform_name, purpose, relative_path in script_specs:
            path = self.paths.root / relative_path
            entry = file_info(path)
            entry.update(
                {
                    "key": key,
                    "platform": platform_name,
                    "purpose": purpose,
                    "relative_path": relative_path,
                    "command": commands.get(key),
                }
            )
            catalog[key] = entry
        return catalog

    def actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for profile in self.available_profiles():
            actions.append(
                {
                    "id": f"package_{profile}",
                    "label": f"Package {profile.replace('_', ' ')}",
                    "kind": "script_command",
                    "profile": profile,
                    "windows_command_key": "package_windows",
                    "ubuntu_command_key": "package_ubuntu",
                    "include_dependency_bundle_supported": True,
                    "governance": "operator_intent_required",
                }
            )
        actions.extend(
            [
                {
                    "id": "build_offline_dependency_bundle",
                    "label": "Build offline dependency bundle",
                    "kind": "script_command",
                    "windows_command_key": "build_offline_deps_windows",
                    "ubuntu_command_key": "build_offline_deps_ubuntu",
                    "governance": "operator_intent_required",
                },
                {
                    "id": "unpack_portable_package",
                    "label": "Unpack portable package",
                    "kind": "script_command",
                    "windows_command_key": "unpack_windows",
                    "ubuntu_command_key": "unpack_ubuntu",
                    "governance": "operator_target_directory_required",
                },
            ]
        )
        return actions

    def package_plan(
        self,
        profile: str | None = None,
        *,
        include_dependency_bundle: bool = False,
    ) -> dict[str, Any]:
        manifest = self.manifest() or {}
        resolved = self.resolved_profile(profile)
        setup_policy = manifest.get("setup_policy") if isinstance(manifest.get("setup_policy"), dict) else {}
        path_policy = manifest.get("path_policy") if isinstance(manifest.get("path_policy"), dict) else {}
        secret_policy = manifest.get("secret_policy") if isinstance(manifest.get("secret_policy"), dict) else {}
        commands = self.commands()
        scripts = self.script_catalog()
        command_keys = [
            "package_windows",
            "package_windows_with_deps",
            "package_ubuntu",
            "package_ubuntu_with_deps",
            "unpack_windows",
            "unpack_ubuntu",
            "setup_windows",
            "setup_ubuntu",
            "build_offline_deps_windows",
            "build_offline_deps_ubuntu",
        ]
        script_keys = [
            "package_windows",
            "package_ubuntu",
            "unpack_windows",
            "unpack_ubuntu",
            "setup_windows",
            "setup_ubuntu",
            "build_offline_deps_windows",
            "build_offline_deps_ubuntu",
        ]
        return {
            "profile": resolved["profile"],
            "valid": resolved["valid"],
            "error": resolved["error"],
            "default_profile": self.default_profile(),
            "inferred_profile": self.inferred_profile(),
            "chain": resolved["chain"],
            "description": resolved["description"],
            "include": resolved["include"],
            "exclude": resolved["exclude"],
            "include_dependency_bundle": include_dependency_bundle,
            "dependency_bundle": setup_policy.get("offline_dependency_bundle"),
            "commands": {key: commands.get(key) for key in command_keys if commands.get(key)},
            "scripts": {key: scripts[key] for key in script_keys if key in scripts},
            "path_policy": {
                "source_rewrite_expected": path_policy.get("source_rewrite_expected"),
                "local_config": path_policy.get("local_config"),
                "unpack_script_windows": path_policy.get("unpack_script_windows"),
                "unpack_script_ubuntu": path_policy.get("unpack_script_ubuntu"),
                "repair_script_windows": path_policy.get("repair_script_windows"),
                "repair_script_ubuntu": path_policy.get("repair_script_ubuntu"),
            },
            "safety": {
                "secret_template": secret_policy.get("template"),
                "excluded_by_default": secret_policy.get("excluded_by_default", []),
                "operator_must_recreate": secret_policy.get("operator_must_recreate", []),
                "governed_data_included": "with_governed_data" in resolved["chain"],
                "source_evidence_included": "with_source_evidence" in resolved["chain"],
                "operator_intent_required": True,
            },
        }

    def status(self) -> dict[str, Any]:
        manifest = self.manifest() or {}
        scripts = self.script_catalog()
        required_scripts = [
            "package_windows",
            "package_ubuntu",
            "unpack_windows",
            "unpack_ubuntu",
            "setup_windows",
            "setup_ubuntu",
        ]
        return {
            "manifest_exists": bool(manifest),
            "default_profile": self.default_profile(),
            "inferred_profile": self.inferred_profile(),
            "available_profiles": self.available_profiles(),
            "default_profile_chain": self.profile_chain(),
            "data_presence": self.data_presence(),
            "scripts_ready": all(scripts[key]["exists"] for key in required_scripts),
            "commands_available": sorted(self.commands().keys()),
        }


@dataclass(frozen=True)
class PackageProfileService(PackagingService):
    """Backward-compatible name for older callers."""
