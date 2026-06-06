from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable

from benchmarking_data_factory.workbench.operator_commands import OPERATOR_COMMAND_SPECS


PORTABLE_VALIDATION_SCHEMA_VERSION = "portable_validation.records.v1"
PORTABLE_VALIDATION_FILE = "portable-validation.json"
PORTABLE_VALIDATION_DIR = "portable-validation"
PORTABLE_VALIDATION_STAGES = (
    "dependency_bundle",
    "package",
    "unpack",
    "setup",
    "run",
    "smoke",
    "test",
)
PORTABLE_VALIDATION_PROFILE_STAGES = (
    "package",
    "unpack",
    "setup",
    "run",
    "smoke",
    "test",
)
PORTABLE_VALIDATION_STATUSES = ("passed", "failed", "blocked", "not_run")
DEFAULT_PORTABLE_PLATFORMS = ("windows", "ubuntu")


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "error": "invalid_json",
            "path": str(path),
        }
    return payload if isinstance(payload, dict) else {"error": "invalid_shape", "path": str(path)}


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


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip("-").lower() or "portable-validation"


@dataclass(frozen=True)
class PortableValidationService:
    """Owns portable package validation evidence and readiness summaries."""

    paths: Any
    now: Callable[[], str] | None = None

    def _now_iso(self) -> str:
        if self.now is not None:
            return self.now()
        return datetime.now(timezone.utc).isoformat()

    def validation_dir(self) -> Path:
        return self.paths.var_dir / PORTABLE_VALIDATION_DIR

    def record_path(self) -> Path:
        return self.validation_dir() / PORTABLE_VALIDATION_FILE

    def portable_manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.paths.root / "PORTABLE_MANIFEST.json")

    def agent_manifest(self) -> dict[str, Any] | None:
        return read_json_file(self.paths.root / "workbench-agent.json")

    def available_profiles(self) -> list[str]:
        profiles = (self.portable_manifest() or {}).get("profiles")
        return sorted(profiles.keys()) if isinstance(profiles, dict) else []

    def supported_platforms(self) -> list[str]:
        manifest_platforms = ((self.agent_manifest() or {}).get("platforms") or {}).get("supported")
        platforms = [item for item in manifest_platforms or [] if isinstance(item, str)]
        return sorted(platforms) if platforms else list(DEFAULT_PORTABLE_PLATFORMS)

    def _read_payload(self) -> dict[str, Any]:
        payload = read_json_file(self.record_path())
        if payload is None:
            return {
                "schema_version": PORTABLE_VALIDATION_SCHEMA_VERSION,
                "records": [],
            }
        if payload.get("error"):
            return {
                "schema_version": PORTABLE_VALIDATION_SCHEMA_VERSION,
                "records": [],
                "storage_error": payload,
            }
        records = payload.get("records")
        if not isinstance(records, list):
            return {
                "schema_version": PORTABLE_VALIDATION_SCHEMA_VERSION,
                "records": [],
                "storage_error": {
                    "error": "invalid_records",
                    "path": str(self.record_path()),
                },
            }
        return {
            "schema_version": payload.get("schema_version") or PORTABLE_VALIDATION_SCHEMA_VERSION,
            "records": [record for record in records if isinstance(record, dict)],
        }

    def records(self) -> list[dict[str, Any]]:
        return list(self._read_payload()["records"])

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.validation_dir().mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": PORTABLE_VALIDATION_SCHEMA_VERSION,
            "updated_at": self._now_iso(),
            "records": records,
        }
        self.record_path().write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _record_id(
        self,
        recorded_at: str,
        platform_name: str,
        profile: str | None,
        stage: str,
        existing_ids: set[str],
    ) -> str:
        base = _slug(f"{recorded_at}-{platform_name}-{profile or 'project'}-{stage}")
        candidate = base
        suffix = 2
        while candidate in existing_ids:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def command_bindings(self) -> list[dict[str, Any]]:
        bindings: list[dict[str, Any]] = []
        for spec in OPERATOR_COMMAND_SPECS:
            command_id = str(spec["id"])
            platform_name = str(spec.get("platform") or "")
            if platform_name == "cross_platform":
                continue
            stage = str(spec.get("category") or "")
            if command_id.startswith("build_offline_deps_"):
                stage = "dependency_bundle"
            elif command_id.startswith("package_"):
                stage = "package"
            elif command_id.startswith("unpack_"):
                stage = "unpack"
            if stage not in PORTABLE_VALIDATION_STAGES:
                continue
            bindings.append(
                {
                    "command_id": command_id,
                    "label": spec.get("label"),
                    "stage": stage,
                    "platform": platform_name,
                    "governance": spec.get("governance"),
                    "safe_to_run_by_agent": bool(spec.get("safe_to_run_by_agent")),
                }
            )
        return sorted(bindings, key=lambda item: (item["platform"], item["stage"], item["command_id"]))

    def command_ids_for(self, platform_name: str, stage: str) -> list[str]:
        return [
            str(binding["command_id"])
            for binding in self.command_bindings()
            if binding["platform"] == platform_name and binding["stage"] == stage
        ]

    def validation_matrix(self) -> list[dict[str, Any]]:
        profiles = self.available_profiles()
        rows: list[dict[str, Any]] = []
        for platform_name in self.supported_platforms():
            rows.append(
                {
                    "platform": platform_name,
                    "profile": None,
                    "stage": "dependency_bundle",
                    "command_ids": self.command_ids_for(platform_name, "dependency_bundle"),
                }
            )
            for profile in profiles:
                for stage in PORTABLE_VALIDATION_PROFILE_STAGES:
                    rows.append(
                        {
                            "platform": platform_name,
                            "profile": profile,
                            "stage": stage,
                            "command_ids": self.command_ids_for(platform_name, stage),
                        }
                    )
        return rows

    def latest_by_key(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for record in sorted(self.records(), key=lambda item: str(item.get("recorded_at") or "")):
            key = self.record_key(record.get("platform"), record.get("profile"), record.get("stage"))
            if key:
                latest[key] = record
        return latest

    def record_key(self, platform_name: Any, profile: Any, stage: Any) -> str | None:
        if not isinstance(platform_name, str) or not isinstance(stage, str):
            return None
        profile_part = profile if isinstance(profile, str) and profile else "project"
        return f"{platform_name}:{profile_part}:{stage}"

    def matrix_status(self) -> dict[str, Any]:
        latest = self.latest_by_key()
        entries: list[dict[str, Any]] = []
        counts: Counter[str] = Counter()
        for row in self.validation_matrix():
            key = self.record_key(row["platform"], row["profile"], row["stage"])
            latest_record = latest.get(key or "")
            status = str(latest_record.get("status")) if latest_record else "not_run"
            if status not in PORTABLE_VALIDATION_STATUSES:
                status = "blocked"
            counts[status] += 1
            entries.append(
                {
                    **row,
                    "status": status,
                    "latest_record_id": latest_record.get("id") if latest_record else None,
                    "recorded_at": latest_record.get("recorded_at") if latest_record else None,
                    "summary": latest_record.get("summary") if latest_record else None,
                }
            )
        total = len(entries)
        return {
            "entries": entries,
            "counts": {status: counts.get(status, 0) for status in PORTABLE_VALIDATION_STATUSES},
            "total": total,
            "passed": counts.get("passed", 0),
            "ready": bool(total) and counts.get("passed", 0) == total,
        }

    def record_result(
        self,
        *,
        platform: str,
        stage: str,
        status: str,
        profile: str | None = None,
        command_id: str | None = None,
        summary: str | None = None,
        evidence: dict[str, Any] | None = None,
        package_path: str | None = None,
        target_path: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        supported_platforms = self.supported_platforms()
        if platform not in supported_platforms:
            raise ValueError(f"Unsupported portable validation platform: {platform}")
        if stage not in PORTABLE_VALIDATION_STAGES:
            raise ValueError(f"Unsupported portable validation stage: {stage}")
        if status not in PORTABLE_VALIDATION_STATUSES:
            raise ValueError(f"Unsupported portable validation status: {status}")
        available_profiles = self.available_profiles()
        if profile is not None and available_profiles and profile not in available_profiles:
            raise ValueError(f"Unsupported portable validation profile: {profile}")
        if stage in PORTABLE_VALIDATION_PROFILE_STAGES and not profile:
            raise ValueError(f"Portable validation stage requires a profile: {stage}")
        if stage == "dependency_bundle" and profile:
            raise ValueError("Dependency bundle validation is platform-level and should not carry a profile")

        records = self.records()
        recorded_at = self._now_iso()
        existing_ids = {str(record.get("id")) for record in records if record.get("id")}
        next_record_id = record_id or self._record_id(recorded_at, platform, profile, stage, existing_ids)
        if next_record_id in existing_ids:
            raise ValueError(f"Portable validation record already exists: {next_record_id}")
        record = {
            "id": next_record_id,
            "schema_version": PORTABLE_VALIDATION_SCHEMA_VERSION,
            "recorded_at": recorded_at,
            "platform": platform,
            "profile": profile,
            "stage": stage,
            "status": status,
            "command_id": command_id,
            "summary": summary,
            "evidence": evidence or {},
            "package_path": package_path,
            "target_path": target_path,
        }
        records.append(record)
        self._write_records(records)
        return record

    def status(self) -> dict[str, Any]:
        payload = self._read_payload()
        matrix = self.matrix_status()
        latest_records = sorted(self.records(), key=lambda item: str(item.get("recorded_at") or ""), reverse=True)[:10]
        return {
            "record_file": file_info(self.record_path()),
            "storage_error": payload.get("storage_error"),
            "record_count": len(self.records()),
            "platforms": self.supported_platforms(),
            "profiles": self.available_profiles(),
            "stages": list(PORTABLE_VALIDATION_STAGES),
            "statuses": list(PORTABLE_VALIDATION_STATUSES),
            "matrix": matrix,
            "ready": matrix["ready"],
            "latest_records": latest_records,
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "schema_version": PORTABLE_VALIDATION_SCHEMA_VERSION,
            "validation_dir": str(self.validation_dir()),
            "record_file": file_info(self.record_path()),
            "platforms": self.supported_platforms(),
            "profiles": self.available_profiles(),
            "stages": list(PORTABLE_VALIDATION_STAGES),
            "statuses": list(PORTABLE_VALIDATION_STATUSES),
            "command_bindings": self.command_bindings(),
            "matrix": self.validation_matrix(),
        }

    def actions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "read_portable_validation_status",
                "label": "Read portable validation status",
                "kind": "agent_status",
                "method": "GET",
                "endpoint": "/api/agent/status",
                "governance": "safe_verification",
            },
            {
                "id": "record_portable_validation_result",
                "label": "Record portable validation result",
                "kind": "service_write",
                "endpoint": None,
                "governance": "operator_evidence_required",
                "writes": [str(self.record_path())],
            },
        ]

    def io(self) -> dict[str, Any]:
        return {
            "execution_policy": "PortableValidationService records evidence and readiness; it does not execute package, setup, run, smoke, or test commands.",
            "validation_dir": str(self.validation_dir()),
            "record_file": file_info(self.record_path()),
            "write_boundary": str(self.paths.root),
            "records_are_generated": True,
            "stages": list(PORTABLE_VALIDATION_STAGES),
            "statuses": list(PORTABLE_VALIDATION_STATUSES),
            "command_bindings": self.command_bindings(),
            "matrix": self.validation_matrix(),
        }
