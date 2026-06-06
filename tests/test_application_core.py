import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarking_data_factory.workbench.application_core import (
    AgentDiscoveryService,
    AgreementWorkspaceService,
    AnalysisAssetService,
    GovernanceEventService,
    IntakeService,
    OperatorCommandService,
    PackagingService,
    PackageProfileService,
    PortableValidationService,
    ReportAssetService,
    ReportExportService,
    WikiLayerService,
    WorkbenchPathService,
)
from benchmarking_data_factory.workbench import review_sections as review_sections_module
from benchmarking_data_factory.workbench import scenario_governance as scenario_governance_module


def test_path_service_catalogs_workspace_files(tmp_path):
    canonical = tmp_path / "canonical"
    immutable = tmp_path / "documents" / "immutable"
    reference_docs = tmp_path / "documents" / "reference"
    analysis = tmp_path / "data" / "analysis"
    governed_canonical = tmp_path / "data" / "governed_canonical"
    datamarts = tmp_path / "data" / "datamarts"
    candidates = tmp_path / "data" / "bronze" / "phase1_source_build" / "candidate_agreements"
    canonical.mkdir()
    immutable.mkdir(parents=True)
    reference_docs.mkdir(parents=True)
    analysis.mkdir(parents=True)
    governed_canonical.mkdir(parents=True)
    datamarts.mkdir(parents=True)
    candidates.mkdir(parents=True)
    (canonical / "ae1.yaml").write_text("agreement_id: ae1\n", encoding="utf-8")
    (immutable / "ae1.pdf").write_bytes(b"%PDF-")
    (reference_docs / "reference.pdf").write_bytes(b"%PDF-")
    candidate_json = candidates / "candidate_agreements.json"
    candidate_json.write_text("[]", encoding="utf-8")
    distribution_json = analysis / "distribution-point-analysis.json"
    (governed_canonical / "pay_rows_status.json").write_text(
        json.dumps(
            {
                "dataset_id": "pay_rows",
                "status": "built",
                "row_count": 3,
                "contract": "docs/governed_canonical/contracts/pay_rows.md",
                "output_files": ["pay_rows.csv", "pay_rows.json"],
            }
        ),
        encoding="utf-8",
    )
    (datamarts / "pay_position_mart_status.json").write_text(
        json.dumps(
            {
                "mart_id": "pay_position_mart",
                "status": "built",
                "row_count": 5,
                "contract": "docs/datamarts/contracts/pay_position_mart.md",
                "output_files": ["pay_position_mart.csv", "pay_position_mart.json"],
            }
        ),
        encoding="utf-8",
    )

    ctx = SimpleNamespace(
        ROOT=tmp_path,
        CANONICAL_DIR=canonical,
        IMMUTABLE_DIR=immutable,
        SCENARIO_OVERRIDES_DIR=tmp_path / "scenario-overrides",
        CACHE_DIR=tmp_path / "cache",
        ANALYSIS_ASSET_DIR=analysis,
        STATIC_DIR=tmp_path / "static",
        CANDIDATE_AGREEMENTS_JSON=candidate_json,
        DISTRIBUTION_POINT_ANALYSIS_JSON=distribution_json,
    )

    service = WorkbenchPathService.from_context(ctx)
    datasets = {item["id"]: item for item in service.datasets()}

    assert datasets["canonical_agreements"]["file_count"] == 1
    assert datasets["source_pdfs"]["file_count"] == 1
    assert datasets["reference_pdfs"]["file_count"] == 1
    assert datasets["intake_candidates"]["file"]["exists"] is True
    assert datasets["wiki_layer"]["document_map_count"] == 0
    assert datasets["governed_canonical:pay_rows"]["row_count"] == 3
    assert datasets["datamart:pay_position_mart"]["row_count"] == 5
    assert datasets["datamart_layer"]["mart_count"] == 1
    assert {item["id"] for item in service.directories()} >= {"canonical", "analysis", "scripts", "documents_reference"}


def test_agent_discovery_service_reports_routes_and_manifests(tmp_path):
    (tmp_path / "workbench-agent.json").write_text('{"schema_version":"1.0","version":"test"}', encoding="utf-8")
    (tmp_path / "PORTABLE_MANIFEST.json").write_text('{"schema_version":"1.0"}', encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
    )
    app = SimpleNamespace(
        routes=[
            SimpleNamespace(path="/api/agent/status", methods={"GET", "HEAD"}, name="agent_status"),
            SimpleNamespace(path="/api/analysis/pay-tables", methods={"GET"}, name="pay_tables"),
        ]
    )
    service = AgentDiscoveryService(
        paths=paths,
        app=app,
        package_profiles=PackageProfileService(paths),
        llm_status=lambda: {
            "provider": "test",
            "model": "model",
            "ready": True,
            "text_capable": True,
            "vision_capable": False,
        },
    )

    status = service.status()
    catalog = service.catalog()

    assert status["manifest"]["version"] == "test"
    assert status["llm"]["ready"] is True
    assert status["package_profile"]["inferred_profile"] == "runtime_code"
    assert status["portable_validation"]["record_count"] == 0
    assert status["routes"]["agent_routes"][0]["path"] == "/api/agent/status"
    assert catalog["portable_validation"]["schema_version"] == "portable_validation.records.v1"
    assert {route["path"] for route in catalog["routes"]} == {"/api/agent/status", "/api/analysis/pay-tables"}


def test_package_profile_service_infers_source_evidence_profile(tmp_path):
    (tmp_path / "PORTABLE_MANIFEST.json").write_text(
        '{"default_profile":"runtime_code","profiles":{"runtime_code":{},"with_governed_data":{},"with_source_evidence":{}}}',
        encoding="utf-8",
    )
    canonical = tmp_path / "canonical"
    immutable = tmp_path / "documents" / "immutable"
    candidates = tmp_path / "data" / "bronze" / "phase1_source_build" / "candidate_agreements"
    analysis = tmp_path / "data" / "analysis"
    canonical.mkdir()
    immutable.mkdir(parents=True)
    candidates.mkdir(parents=True)
    analysis.mkdir(parents=True)
    (canonical / "ae1.yaml").write_text("agreement_id: ae1\n", encoding="utf-8")
    (immutable / "ae1.pdf").write_bytes(b"%PDF-")
    candidate_json = candidates / "candidate_agreements.json"
    candidate_json.write_text("[]", encoding="utf-8")
    distribution_json = analysis / "distribution-point-analysis.json"
    distribution_json.write_text("{}", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=canonical,
        immutable_dir=immutable,
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=analysis,
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=candidate_json,
        distribution_point_analysis_json=distribution_json,
    )

    status = PackageProfileService(paths).status()

    assert status["default_profile"] == "runtime_code"
    assert status["inferred_profile"] == "with_source_evidence"
    assert status["data_presence"]["has_governed_data"] is True
    assert status["data_presence"]["has_source_evidence"] is True


def test_packaging_service_resolves_profile_scripts_and_package_plan(tmp_path):
    (tmp_path / "PORTABLE_MANIFEST.json").write_text(
        """
        {
          "default_profile": "runtime_code",
          "profiles": {
            "runtime_code": {
              "description": "Code only",
              "include": ["src/**"],
              "exclude": [".env", ".git/**", "vendor/**"]
            },
            "with_governed_data": {
              "extends": "runtime_code",
              "description": "Code plus governed data",
              "include": ["canonical/**", "data/analysis/**"]
            },
            "with_source_evidence": {
              "extends": "with_governed_data",
              "description": "Code plus evidence",
              "include": ["documents/immutable/**", "documents/reference/**"]
            }
          },
          "path_policy": {
            "source_rewrite_expected": false,
            "local_config": ".env",
            "unpack_script_windows": "scripts/unpack-workbench.ps1",
            "unpack_script_ubuntu": "scripts/unpack-workbench.sh",
            "repair_script_windows": "scripts/setup-windows.ps1",
            "repair_script_ubuntu": "scripts/setup-ubuntu.sh"
          },
          "setup_policy": {
            "offline_dependency_bundle": {
              "default_included": false,
              "python_wheels": "vendor/python-wheels"
            }
          },
          "secret_policy": {
            "excluded_by_default": [".env", ".git"],
            "operator_must_recreate": ["OPENAI_API_KEY"],
            "template": ".env.example"
          }
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / "workbench-agent.json").write_text(
        """
        {
          "commands": {
            "package_windows": "powershell -File scripts/package-workbench.ps1",
            "package_windows_with_deps": "powershell -File scripts/package-workbench.ps1 -IncludeDependencyBundle",
            "package_ubuntu": "bash scripts/package-workbench.sh",
            "package_ubuntu_with_deps": "INCLUDE_DEPENDENCY_BUNDLE=1 bash scripts/package-workbench.sh",
            "unpack_windows": "powershell -File scripts/unpack-workbench.ps1 -SourceZip <zip> -Destination <folder>",
            "unpack_ubuntu": "bash scripts/unpack-workbench.sh <zip> <folder>",
            "setup_windows": "powershell -File scripts/setup-windows.ps1",
            "setup_ubuntu": "bash scripts/setup-ubuntu.sh",
            "build_offline_deps_windows": "powershell -File scripts/build-offline-deps.ps1",
            "build_offline_deps_ubuntu": "bash scripts/build-offline-deps.sh"
          }
        }
        """,
        encoding="utf-8",
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script_name in [
        "run-windows.ps1",
        "run-ubuntu.sh",
        "setup-windows.ps1",
        "setup-ubuntu.sh",
        "package-workbench.ps1",
        "package-workbench.sh",
        "build-offline-deps.ps1",
        "build-offline-deps.sh",
        "unpack-workbench.ps1",
        "unpack-workbench.sh",
    ]:
        (scripts / script_name).write_text("# test\n", encoding="utf-8")
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "ae1.yaml").write_text("agreement_id: ae1\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=canonical,
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=scripts,
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
    )

    service = PackagingService(paths)
    source_plan = service.package_plan("with_source_evidence", include_dependency_bundle=True)
    governed_plan = service.package_plan("with_governed_data")
    status = service.status()

    assert source_plan["chain"] == ["runtime_code", "with_governed_data", "with_source_evidence"]
    assert source_plan["include_dependency_bundle"] is True
    assert "documents/immutable/**" in source_plan["include"]
    assert "documents/reference/**" in source_plan["include"]
    assert source_plan["safety"]["source_evidence_included"] is True
    assert governed_plan["safety"]["governed_data_included"] is True
    assert governed_plan["safety"]["source_evidence_included"] is False
    assert source_plan["scripts"]["package_windows"]["exists"] is True
    assert "package_ubuntu_with_deps" in source_plan["commands"]
    assert status["scripts_ready"] is True
    assert service.resolved_profile("missing")["valid"] is False


def test_windows_package_script_rejects_unknown_profiles():
    script = Path("scripts/package-workbench.ps1").read_text(encoding="utf-8")

    assert "$AllowedProfiles" in script
    assert "Unknown profile" in script


def test_operator_command_service_catalogs_stable_commands_and_handoff(tmp_path):
    (tmp_path / "workbench-agent.json").write_text(
        """
        {
          "commands": {
            "setup_windows": "powershell -File scripts/setup-windows.ps1",
            "setup_ubuntu": "bash scripts/setup-ubuntu.sh",
            "run_windows": "powershell -File scripts/run-windows.ps1",
            "run_ubuntu": "bash scripts/run-ubuntu.sh",
            "test_windows": ".\\\\.venv-win\\\\Scripts\\\\python.exe -m pytest",
            "test_ubuntu": ".venv/bin/python -m pytest",
            "smoke_windows": ".\\\\.venv-win\\\\Scripts\\\\python.exe smoke_test.py",
            "smoke_ubuntu": ".venv/bin/python smoke_test.py",
            "lint_frontend": "npm run lint",
            "package_windows": "powershell -File scripts/package-workbench.ps1",
            "package_windows_with_deps": "powershell -File scripts/package-workbench.ps1 -IncludeDependencyBundle",
            "package_ubuntu": "bash scripts/package-workbench.sh",
            "package_ubuntu_with_deps": "INCLUDE_DEPENDENCY_BUNDLE=1 bash scripts/package-workbench.sh",
            "build_offline_deps_windows": "powershell -File scripts/build-offline-deps.ps1",
            "build_offline_deps_ubuntu": "bash scripts/build-offline-deps.sh",
            "unpack_windows": "powershell -File scripts/unpack-workbench.ps1 -SourceZip <zip> -Destination <folder>",
            "unpack_ubuntu": "bash scripts/unpack-workbench.sh <zip> <folder>"
          }
        }
        """,
        encoding="utf-8",
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script_name in [
        "setup-windows.ps1",
        "setup-ubuntu.sh",
        "run-windows.ps1",
        "run-ubuntu.sh",
        "package-workbench.ps1",
        "package-workbench.sh",
        "build-offline-deps.ps1",
        "build-offline-deps.sh",
        "unpack-workbench.ps1",
        "unpack-workbench.sh",
    ]:
        (scripts / script_name).write_text("# test\n", encoding="utf-8")
    (tmp_path / "smoke_test.py").write_text("print('ok')\n", encoding="utf-8")
    for doc_name in [
        "CURRENT_STATE_AND_NEXT_ACTIONS.md",
        "UBUNTU_HANDOFF.md",
        "GITHUB_COLLABORATION.md",
        "PRODUCT_ARCHITECTURE.md",
        "REPORT_ASSET_CONTRACT.md",
    ]:
        (tmp_path / doc_name).write_text("# doc\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=scripts,
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
    )

    service = OperatorCommandService(paths)
    catalog = service.catalog()
    status = service.status()
    actions = service.actions()
    io = service.io()

    assert status["commands_ready"] is True
    assert status["handoff_ready"] is True
    assert set(catalog["groups"]) >= {"setup", "run", "test", "smoke", "package", "handoff"}
    assert "smoke_windows" in catalog["groups"]["smoke"]
    assert any(action["id"] == "operator_command_test_windows" for action in actions)
    assert "test_windows" in io["safety"]["agent_safe_verification_commands"]
    assert "package_windows" in io["safety"]["operator_intent_required_for"]


def test_portable_validation_service_records_latest_matrix_status(tmp_path):
    (tmp_path / "PORTABLE_MANIFEST.json").write_text(
        """
        {
          "profiles": {
            "runtime_code": {},
            "with_governed_data": {}
          }
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / "workbench-agent.json").write_text(
        '{"platforms":{"supported":["windows","ubuntu"]}}',
        encoding="utf-8",
    )
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
    )
    service = PortableValidationService(paths, now=lambda: "2026-05-07T00:00:00+00:00")

    record = service.record_result(
        platform="windows",
        profile="runtime_code",
        stage="smoke",
        status="passed",
        command_id="smoke_windows",
        summary="Windows smoke test passed after unpack.",
        evidence={"exit_code": 0},
        package_path="exports/workbench.zip",
        target_path="C:/tmp/workbench",
    )
    status = service.status()
    catalog = service.catalog()
    io = service.io()
    smoke_entry = next(
        item
        for item in status["matrix"]["entries"]
        if item["platform"] == "windows" and item["profile"] == "runtime_code" and item["stage"] == "smoke"
    )

    assert record["id"]
    assert status["record_count"] == 1
    assert status["record_file"]["exists"] is True
    assert status["matrix"]["counts"]["passed"] == 1
    assert status["ready"] is False
    assert smoke_entry["status"] == "passed"
    assert smoke_entry["latest_record_id"] == record["id"]
    assert any(binding["command_id"] == "smoke_windows" for binding in catalog["command_bindings"])
    assert "does not execute" in io["execution_policy"]
    with pytest.raises(ValueError, match="requires a profile"):
        service.record_result(platform="windows", stage="test", status="passed")


def test_wiki_layer_service_reads_runs_maps_questions_and_artifacts(tmp_path):
    wiki = tmp_path / "wiki"
    for folder in [
        "document-maps",
        "language-maps",
        "questions",
        "learning-backlog",
        "runs",
        "artifacts",
    ]:
        (wiki / folder).mkdir(parents=True)
    run_id = "wiki-run-test"
    (wiki / "wiki-manifest.json").write_text(
        json.dumps({
            "schema_version": "wiki.manifest.v1",
            "scope_focus": "entitlements_conditions_benefits",
            "latest_run_id": run_id,
        }),
        encoding="utf-8",
    )
    (wiki / "runs" / f"{run_id}.json").write_text(
        json.dumps({
            "schema_version": "wiki.pilot_run.v1",
            "run_id": run_id,
            "generated_at": "2026-05-05T00:00:00+00:00",
            "summary": {"agreements_mapped": 1},
        }),
        encoding="utf-8",
    )
    (wiki / "document-maps" / "ae-test.json").write_text(
        json.dumps({
            "schema_version": "wiki.document_map.v1",
            "agreement_id": "ae-test",
            "agreement_name": "Test Agreement",
            "summary": {"pages_scanned": 2},
        }),
        encoding="utf-8",
    )
    (wiki / "questions" / f"{run_id}.json").write_text(
        json.dumps({"schema_version": "wiki.questions.v1", "run_id": run_id, "questions": [{"status": "open"}]}),
        encoding="utf-8",
    )
    (wiki / "learning-backlog" / f"{run_id}.json").write_text(
        json.dumps({"schema_version": "wiki.learning_backlog.v1", "run_id": run_id, "items": [{"status": "observed"}]}),
        encoding="utf-8",
    )
    (wiki / "language-maps" / "clause-context-terms.json").write_text(
        json.dumps({"schema_version": "wiki.language_map.v1", "terms": [{"canonical_term": "ordinary_hours"}]}),
        encoding="utf-8",
    )
    (wiki / "artifacts" / "note.md").write_text("# Note\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
        wiki_dir=wiki,
    )

    service = WikiLayerService(paths)

    assert service.status()["latest_run_id"] == run_id
    assert service.runs()["runs"][0]["summary"]["agreements_mapped"] == 1
    assert service.latest_run()["run_id"] == run_id
    assert service.document_maps()["document_maps"][0]["agreement_id"] == "ae-test"
    assert service.document_map("ae-test")["agreement_name"] == "Test Agreement"
    assert service.questions()["questions"][0]["status"] == "open"
    assert service.learning_backlog()["items"][0]["status"] == "observed"
    assert service.language_map()["terms"][0]["canonical_term"] == "ordinary_hours"
    assert service.artifacts()["artifacts"][0]["relative_path"] == "artifacts/note.md"
    try:
        service.run("../bad")
    except ValueError as exc:
        assert "Invalid wiki run id" in str(exc)
    else:
        raise AssertionError("unsafe wiki run id should fail")


def test_report_asset_service_materializes_distribution_point_manifest(tmp_path):
    raw_asset = tmp_path / "data" / "analysis" / "distribution-point-analysis.json"
    raw_asset.parent.mkdir(parents=True)
    (tmp_path / "REPORT_ASSET_CONTRACT.md").write_text("# Report Asset Contract\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=raw_asset.parent,
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=raw_asset,
    )
    service = ReportAssetService(paths, now=lambda: "2026-05-03T00:00:00+00:00")
    analysis_payload = {
        "asset_version": "abc123",
        "generated_at": "2026-05-02T06:23:18+00:00",
        "asset": {
            "path": "data/analysis/distribution-point-analysis.json",
            "materialized_at": "2026-05-02T06:23:19+00:00",
        },
        "summary": {
            "distribution_points": 2,
            "source_basis_counts": {"governed_table": 2},
            "calculation_status_counts": {"ok": 2},
        },
        "patterns": [{"pattern": "governed_table", "count": 2}],
        "rows": [{"analysis_id": "one"}, {"analysis_id": "two"}],
    }

    manifest = service.materialize_distribution_point_analysis_manifest(analysis_payload)
    summary = service.manifest_summary(manifest)
    catalog = service.catalog()
    updated = service.update_distribution_point_analysis_status("reviewed", operator_note="Ready for peer review.")
    updated_summary = service.manifest_summary()

    assert manifest["asset_id"] == "distribution_point_analysis_default"
    assert manifest["source_dataset_version"] == "abc123"
    assert manifest["provenance"]["row_count"] == 2
    assert service.distribution_point_analysis_manifest_path().exists()
    assert summary["validation"]["valid"] is True
    assert catalog["assets"][0]["validation"]["valid"] is True
    assert updated["status"] == "reviewed"
    assert updated["operator_note"] == "Ready for peer review."
    assert updated["status_updated_at"] == "2026-05-03T00:00:00+00:00"
    assert updated["status_updated_by"] == "operator"
    assert updated_summary["status"] == "reviewed"
    assert "report_ready" in updated_summary["status_options"]
    try:
        service.update_distribution_point_analysis_status("bogus")
    except ValueError as exc:
        assert "Unsupported report asset status" in str(exc)
    else:
        raise AssertionError("invalid report asset status should fail")


def test_report_export_service_materializes_distribution_point_files(tmp_path):
    raw_asset = tmp_path / "data" / "analysis" / "distribution-point-analysis.json"
    raw_asset.parent.mkdir(parents=True)
    (tmp_path / "REPORT_ASSET_CONTRACT.md").write_text("# Report Asset Contract\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=raw_asset.parent,
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=raw_asset,
    )
    analysis_payload = {
        "asset_version": "abc123",
        "generated_at": "2026-05-02T06:23:18+00:00",
        "asset": {"path": "data/analysis/distribution-point-analysis.json"},
        "summary": {
            "distribution_points": 2,
            "quarters": 1,
            "bands": 1,
            "source_basis_counts": {"governed_table": 2},
            "calculation_status_counts": {"ok": 2},
        },
        "patterns": [{"pattern": "governed_table", "count": 2}],
        "rows": [
            {
                "analysis_id": "one",
                "ae_id": "ae1",
                "agreement_name": "Example Agreement",
                "canonical_lga_short_name": "Example",
                "quarter_start": "2026-07-01",
                "band": "1",
                "min_level": "A",
                "min_weekly_rate": 1000,
                "max_level": "B",
                "max_weekly_rate": 1100,
                "midpoint_weekly_rate": 1050,
                "max_level_point_weekly_rate": 1100,
                "calculation_status": "ok",
                "source_basis": "governed_table",
                "is_known_value": True,
                "is_projected_value": False,
            },
            {"analysis_id": "two", "midpoint_weekly_rate": 1200, "calculation_status": "ok"},
        ],
    }
    raw_asset.write_text(json.dumps(analysis_payload), encoding="utf-8")
    report_assets = ReportAssetService(paths, now=lambda: "2026-05-03T00:00:00+00:00")
    report_assets.materialize_distribution_point_analysis_manifest(analysis_payload)
    service = ReportExportService(
        paths,
        report_assets=report_assets,
        now=lambda: "2026-05-03T00:00:00+00:00",
    )

    export_manifest = service.materialize_distribution_point_exports(row_limit=1)
    paths_by_format = service.export_paths()

    assert export_manifest["row_count"] == 1
    assert export_manifest["formats"]["csv"]["exists"] is True
    assert paths_by_format["csv"].read_text(encoding="utf-8").splitlines()[0].startswith("analysis_id,ae_id")
    assert service.export_file_path("csv") == paths_by_format["csv"]
    assert service.export_file_path("manifest") == paths_by_format["manifest"]
    assert paths_by_format["svg"].read_text(encoding="utf-8").startswith("<svg")
    assert paths_by_format["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    for format_name, expected_member in {
        "xlsx": "xl/worksheets/sheet1.xml",
        "docx": "word/document.xml",
        "pptx": "ppt/slides/slide1.xml",
    }.items():
        with zipfile.ZipFile(paths_by_format[format_name]) as archive:
            assert "[Content_Types].xml" in archive.namelist()
            assert expected_member in archive.namelist()
    assert paths_by_format["manifest"].exists()
    try:
        service.export_file_path("pdf")
    except ValueError as exc:
        assert "Unsupported report export format" in str(exc)
    else:
        raise AssertionError("unsupported report export format should fail")


def test_analysis_asset_service_writes_report_manifest_on_distribution_materialize(tmp_path):
    raw_asset = tmp_path / "data" / "analysis" / "distribution-point-analysis.json"
    raw_asset.parent.mkdir(parents=True)
    (tmp_path / "REPORT_ASSET_CONTRACT.md").write_text("# Report Asset Contract\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=raw_asset.parent,
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=raw_asset,
    )
    report_assets = ReportAssetService(paths, now=lambda: "2026-05-03T00:00:00+00:00")
    service = AnalysisAssetService(
        build_uplift_rules_analysis=lambda **kwargs: {},
        build_pay_tables_analysis=lambda **kwargs: {},
        build_end_of_band_dollars_analysis=lambda **kwargs: {},
        build_review_learning_snapshot=lambda **kwargs: {},
        load_distribution_point_analysis_asset=lambda: None,
        materialize_distribution_point_analysis=lambda **kwargs: {
            "asset_version": "def456",
            "generated_at": "2026-05-03T00:00:00+00:00",
            "asset": {"path": "data/analysis/distribution-point-analysis.json"},
            "summary": {"distribution_points": 1},
            "rows": [{"analysis_id": "one"}],
        },
        rebuild_analysis_data_set=lambda data_set, **kwargs: {},
        report_assets=report_assets,
    )

    payload = service.distribution_point_analysis(force_refresh=True)

    assert payload["report_asset"]["validation"]["valid"] is True
    assert report_assets.distribution_point_analysis_manifest_path().exists()


def test_analysis_asset_service_rebuilds_pay_tables_with_distribution_asset():
    calls = []
    service = AnalysisAssetService(
        build_uplift_rules_analysis=lambda **kwargs: {"kind": "uplift", "kwargs": kwargs},
        build_pay_tables_analysis=lambda **kwargs: {"kind": "pay", "kwargs": kwargs},
        build_end_of_band_dollars_analysis=lambda **kwargs: {"kind": "eob", "kwargs": kwargs},
        build_review_learning_snapshot=lambda **kwargs: {"kind": "review", "kwargs": kwargs},
        load_distribution_point_analysis_asset=lambda: {"cached": True},
        materialize_distribution_point_analysis=lambda **kwargs: {
            "asset_version": "abc",
            "asset": {"path": "data/analysis/distribution-point-analysis.json"},
            "summary": {"rows": 1},
            "kwargs": kwargs,
        },
        rebuild_analysis_data_set=lambda data_set, **kwargs: calls.append((data_set, kwargs)) or {"changed": 1},
    )

    payload = service.rebuild("pay-tables", include_split_parents=True)

    assert calls == [("pay_tables", {"include_split_parents": True})]
    assert payload["ok"] is True
    assert payload["analysis"]["kind"] == "pay"
    assert payload["derived_assets"]["distribution_point_analysis"]["asset_version"] == "abc"


def test_analysis_asset_service_uses_cached_distribution_asset():
    service = AnalysisAssetService(
        build_uplift_rules_analysis=lambda **kwargs: {},
        build_pay_tables_analysis=lambda **kwargs: {},
        build_end_of_band_dollars_analysis=lambda **kwargs: {},
        build_review_learning_snapshot=lambda **kwargs: {},
        load_distribution_point_analysis_asset=lambda: {"cached": True},
        materialize_distribution_point_analysis=lambda **kwargs: {"cached": False},
        rebuild_analysis_data_set=lambda data_set, **kwargs: {},
    )

    assert service.distribution_point_analysis() == {"cached": True}
    assert service.distribution_point_analysis(force_refresh=True) == {"cached": False}


def test_wiki_entitlement_matrix_returns_all_cells(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "document-maps").mkdir(parents=True)
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
        wiki_dir=wiki,
    )
    service = WikiLayerService(paths)
    targets = [
        {"council": f"Council {index}", "agreement_id": f"ae-{index:03d}", "agreement_name": f"Agreement {index}"}
        for index in range(260)
    ]
    governed_rows = [
        {"entitlement_id": "ent-one", "entitlement_label": "Entitlement One", "category": "Leave"},
        {"entitlement_id": "ent-two", "entitlement_label": "Entitlement Two", "category": "Leave"},
    ]
    payload = {
        "artifact_id": "locator-large-test",
        "generated_at": "2026-05-10T00:00:00+00:00",
        "target_comparator_set": targets,
        "profiles": [
            {
                "entitlement_id": row["entitlement_id"],
                "target_rows": [
                    {
                        "council": target["council"],
                        "agreement_id": target["agreement_id"],
                        "agreement_name": target["agreement_name"],
                        "page_count": 1,
                        "state": "no_candidate_clause_found",
                        "candidate_count": 0,
                        "clause_cards": [],
                        "feature_cards": [],
                    }
                    for target in targets
                ],
            }
            for row in governed_rows
        ],
    }

    matrix = service._entitlement_test_matrix_projection(payload, tmp_path / "artifact.json", governed_rows)

    assert matrix["summary"]["test_cells"] == 520
    assert len(matrix["cells"]) == 520


def test_wiki_entitlement_cards_projection_returns_full_register_with_clause_text(tmp_path):
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=tmp_path / "scripts",
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
        wiki_dir=tmp_path / "wiki",
    )
    service = WikiLayerService(paths)
    cards = [
        {
            "entitlement_card_id": f"card-{index}",
            "council": f"Council {index}",
            "entitlement_label": "Union Training Leave",
            "simple_sentence": "10 days of union training leave.",
            "source_clauses": [
                {
                    "clause_id": f"clause-{index}",
                    "page": 8,
                    "raw_clause_text": "Workplace delegates are entitled to 10 days paid leave over two years.",
                }
            ],
        }
        for index in range(120)
    ]

    projection = service._entitlement_cards_projection(
        {
            "schema_version": "wiki.entitlement_cards.v1",
            "summary": {"entitlement_cards": len(cards)},
            "cards": cards,
            "blocked_samples": [],
        },
        tmp_path / "cards.json",
    )

    assert projection["summary"]["entitlement_cards"] == 120
    assert len(projection["cards"]) == 120
    assert "10 days paid leave" in projection["cards"][0]["source_clauses"][0]["raw_clause_text"]


def test_clause_pipeline_freshness_flags_stale_dependency_chain(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in [
        "build_entitlement_locator_experiment.py",
        "build_entitlement_cards.py",
        "build_entitlement_card_repair_loop.py",
    ]:
        (scripts / name).write_text("# builder\n", encoding="utf-8")
    paths = WorkbenchPathService(
        root=tmp_path,
        canonical_dir=tmp_path / "canonical",
        immutable_dir=tmp_path / "documents" / "immutable",
        registers_dir=tmp_path / "registers",
        scenario_overrides_dir=tmp_path / "scenario-overrides",
        cache_dir=tmp_path / "cache",
        analysis_asset_dir=tmp_path / "data" / "analysis",
        exports_dir=tmp_path / "exports",
        var_dir=tmp_path / "var",
        static_dir=tmp_path / "static",
        src_dir=tmp_path / "src",
        scripts_dir=scripts,
        tests_dir=tmp_path / "tests",
        candidate_agreements_json=tmp_path / "data" / "candidate_agreements.json",
        distribution_point_analysis_json=tmp_path / "data" / "analysis" / "distribution-point-analysis.json",
        wiki_dir=tmp_path / "wiki",
    )
    service = WikiLayerService(paths)
    locator_path = tmp_path / "locator.json"
    cards_path = tmp_path / "cards.json"
    repair_path = tmp_path / "repair.json"
    for path in [locator_path, cards_path, repair_path]:
        path.write_text("{}", encoding="utf-8")

    freshness = service._clause_pipeline_freshness(
        {
            "artifact_id": "locator-v1",
            "generated_at": "2000-01-01T00:00:00+00:00",
            "profiles": [
                {
                    "target_rows": [
                        {"feature_cards": [{"feature_id": "feature-one"}]},
                    ],
                }
            ],
        },
        locator_path,
        {
            "artifact_id": "cards-v1",
            "generated_at": "2000-01-01T00:10:00+00:00",
            "source_artifact": {
                "locator_artifact_id": "locator-v1",
                "generated_at": "2000-01-01T00:00:00+00:00",
            },
        },
        cards_path,
        {
            "artifact_id": "repair-v1",
            "generated_at": "2000-01-01T00:05:00+00:00",
            "source_artifact": {
                "locator_artifact_id": "locator-v1",
                "entitlement_cards_artifact_id": "cards-v1",
            },
        },
        repair_path,
    )

    assert freshness["status"] == "stale"
    locator, cards, repair = freshness["checks"]
    assert locator["answer_builder_coverage"]["with_answer_builder_contract"] == 0
    assert "answer_builder_contracts_missing" in locator["reasons"]
    assert "upstream_locator_needs_refresh" in cards["reasons"]
    assert "artifact_predates_entitlement_cards" in repair["reasons"]


def test_intake_service_wraps_reference_and_fetch_behaviour():
    fetch_calls = []
    service = IntakeService(
        load_canonical_councils=lambda: [
            {"name": "Active Council", "status": "active"},
            {"name": "Old Council", "status": "retired"},
        ],
        canonical_council_reference_payload=lambda: {"canonical": True},
        council_master_reference_payload=lambda: {"master": True},
        council_job_source_registry_payload=lambda: {"jobs": True},
        build_intake_quality_summary=lambda **kwargs: {"candidate_records": 2, "kwargs": kwargs},
        build_intake_candidate_rows=lambda: [{"ae_id": "AE1"}],
        build_council_audit_report=lambda name: {"council": name},
        fetch_fair_work_registry_intake=lambda **kwargs: fetch_calls.append(kwargs) or {"ok": True},
        load_intake_decisions=lambda: {"AE1": {"status": "accepted"}},
        intake_workflow_dependencies=lambda: None,
    )

    assert service.active_canonical_councils() == [{"name": "Active Council", "status": "active"}]
    assert service.canonical_council_count() == {"total": 2}
    assert service.council_job_source_registry() == {"jobs": True}
    assert service.intake_quality()["candidate_records"] == 2
    assert service.intake_quality(force_refresh=True)["kwargs"] == {"force_refresh": True}
    assert service.intake_candidates() == [{"ae_id": "AE1"}]
    assert service.council_audit("Test Council") == {"council": "Test Council"}
    assert service.fetch_registry(force_refresh=False, fetch_pdfs=True, pdf_limit=3) == {"ok": True}
    assert fetch_calls == [{"force_registry": False, "fetch_pdfs": True, "pdf_limit": 3}]


def test_agreement_workspace_service_updates_sections_and_document_evidence(tmp_path):
    pdf_path = tmp_path / "ae1.pdf"
    pdf_path.write_bytes(b"%PDF-")
    saved = []
    canonical = {
        "sections": {
            "overview": {
                "status": "not_started",
                "completed_at": None,
            }
        }
    }

    def apply_section_status(section, status, completed_at):
        section["status"] = status
        section["completed_at"] = completed_at

    service = AgreementWorkspaceService(
        clear_review_record=lambda *args, **kwargs: {"cleared": True},
        list_councils=lambda include_split_parents=False: [{"ae_id": "ae1", "split": include_split_parents}],
        get_council=lambda ae_id: {"ae_id": ae_id},
        intake_workflow_dependencies=lambda: None,
        sections={"overview"},
        valid_section_statuses={"not_started", "in_progress", "done"},
        get_canonical=lambda ae_id: canonical,
        apply_section_status=apply_section_status,
        now_iso=lambda: "2026-05-02T00:00:00+00:00",
        save_canonical=lambda ae_id, payload: saved.append((ae_id, payload)),
        uplift_workflow_dependencies=lambda: None,
        fetch_metadata_for_ae_id=lambda ae_id: {"ae_id": ae_id, "source": "registry"},
        find_pdf=lambda ae_id: pdf_path,
        extract_page_text=lambda ae_id, page_num: f"{ae_id}:{page_num}",
        render_page_png=lambda ae_id, page_num: b"png",
        agreement_dependencies=lambda: None,
        pay_table_dependencies=lambda: None,
        scenario_governance_dependencies=lambda: None,
    )

    section_result = service.update_section_status("ae1", "overview", "done")

    assert section_result["completed_at"] == "2026-05-02T00:00:00+00:00"
    assert saved == [("ae1", canonical)]
    assert service.councils(include_split_parents=True) == [{"ae_id": "ae1", "split": True}]
    assert service.council("ae1") == {"ae_id": "ae1"}
    assert service.fetch_metadata("ae1")["source"] == "registry"
    assert service.pdf_path("ae1") == pdf_path
    assert service.page_text("ae1", 2) == {"page": 2, "text": "ae1:2"}
    assert service.page_image("ae1", 2) == b"png"


def test_section_human_qa_off_rolls_back_every_downstream_process_section(monkeypatch):
    saved = []
    cleared_overrides = []
    scenario_deps = object()
    timestamp = "2026-05-02T00:00:00+00:00"
    canonical = {
        "agreement_id": "ae1",
        "sections": review_sections_module.default_sections(),
    }

    for name in review_sections_module.REVIEW_SECTIONS:
        section = canonical["sections"][name]
        section["status"] = "done"
        section["completed_at"] = "2026-05-01T00:00:00+00:00"
        section["source_ref"] = f"{name}-source"
        section["notes"] = f"{name}-notes"
        section["human_qa"] = {"enabled": True, "updated_at": "2026-05-01T00:00:00+00:00"}

    canonical["sections"]["pay_tables"]["tables"] = [{"title": "Accepted rates"}]
    canonical["sections"]["scenarios"]["data"] = {"runs": [{"id": "scenario-1"}]}
    canonical["sections"]["uplifts"]["data"] = {"governed": True}
    canonical["sections"]["clauses"]["data"]["items"] = [{"category": "allowances_reimbursements"}]

    def apply_section_status(section, status, completed_at):
        section["status"] = status
        section["completed_at"] = completed_at

    def fake_delete_overrides(ae_id, deps):
        cleared_overrides.append((ae_id, deps))
        return {"ok": True}

    monkeypatch.setattr(
        scenario_governance_module,
        "delete_uplift_rule_scenario_overrides",
        fake_delete_overrides,
    )

    service = AgreementWorkspaceService(
        clear_review_record=lambda *args, **kwargs: {"cleared": True},
        list_councils=lambda include_split_parents=False: [],
        get_council=lambda ae_id: canonical,
        intake_workflow_dependencies=lambda: None,
        sections=set(review_sections_module.REVIEW_SECTIONS),
        valid_section_statuses=review_sections_module.VALID_SECTION_STATUSES,
        get_canonical=lambda ae_id: canonical,
        apply_section_status=apply_section_status,
        now_iso=lambda: timestamp,
        save_canonical=lambda ae_id, payload: saved.append((ae_id, payload)),
        uplift_workflow_dependencies=lambda: None,
        fetch_metadata_for_ae_id=lambda ae_id: None,
        find_pdf=lambda ae_id: None,
        extract_page_text=lambda ae_id, page_num: "",
        render_page_png=lambda ae_id, page_num: b"",
        agreement_dependencies=lambda: None,
        pay_table_dependencies=lambda: None,
        scenario_governance_dependencies=lambda: scenario_deps,
    )

    result = service.update_section_human_qa(
        "ae1",
        "pay_tables",
        enabled=False,
        notes="Reviewer found the pay table is not accepted.",
        summary="Pay Tables Human QA switched off.",
    )

    assert result["downstream_cleared"] == ["scenarios", "end_of_band_dollars", "uplifts", "clauses"]
    assert saved == [("ae1", canonical)]
    assert cleared_overrides == [("ae1", scenario_deps)]

    pay_tables = canonical["sections"]["pay_tables"]
    assert pay_tables["status"] == "in_progress"
    assert pay_tables["completed_at"] is None
    assert pay_tables["tables"] == [{"title": "Accepted rates"}]
    assert pay_tables["human_qa"]["enabled"] is False
    assert pay_tables["human_qa"]["downstream_cleared"] == ["scenarios", "end_of_band_dollars", "uplifts", "clauses"]

    assert canonical["sections"]["uplift_rules"]["status"] == "done"
    assert canonical["sections"]["uplift_rules"]["human_qa"]["enabled"] is True

    for name in ("scenarios", "end_of_band_dollars", "uplifts", "clauses"):
        section = canonical["sections"][name]
        assert section["status"] == "not_started"
        assert section["completed_at"] is None
        assert section["source_ref"] == ""
        assert section["notes"] == ""
        assert section["human_qa"]["enabled"] is False
        assert section["human_qa"]["invalidated_by"] == "pay_tables"
        assert section["human_qa"]["invalidated_at"] == timestamp

    assert canonical["sections"]["scenarios"]["data"] is None
    assert canonical["sections"]["end_of_band_dollars"]["data"] is None
    assert canonical["sections"]["uplifts"]["data"] is None
    assert canonical["sections"]["clauses"]["data"]["items"] == []


def test_section_human_qa_on_requires_upstream_gates():
    canonical = {
        "agreement_id": "ae1",
        "sections": review_sections_module.default_sections(),
    }

    def apply_section_status(section, status, completed_at):
        section["status"] = status
        section["completed_at"] = completed_at

    service = AgreementWorkspaceService(
        clear_review_record=lambda *args, **kwargs: {"cleared": True},
        list_councils=lambda include_split_parents=False: [],
        get_council=lambda ae_id: canonical,
        intake_workflow_dependencies=lambda: None,
        sections=set(review_sections_module.REVIEW_SECTIONS),
        valid_section_statuses=review_sections_module.VALID_SECTION_STATUSES,
        get_canonical=lambda ae_id: canonical,
        apply_section_status=apply_section_status,
        now_iso=lambda: "2026-05-02T00:00:00+00:00",
        save_canonical=lambda ae_id, payload: None,
        uplift_workflow_dependencies=lambda: None,
        fetch_metadata_for_ae_id=lambda ae_id: None,
        find_pdf=lambda ae_id: None,
        extract_page_text=lambda ae_id, page_num: "",
        render_page_png=lambda ae_id, page_num: b"",
        agreement_dependencies=lambda: None,
        pay_table_dependencies=lambda: None,
        scenario_governance_dependencies=lambda: None,
    )

    with pytest.raises(Exception) as excinfo:
        service.update_section_human_qa(
            "ae1",
            "pay_tables",
            enabled=True,
            notes="Accept pay tables",
            summary="Pay tables accepted.",
        )

    assert excinfo.value.status_code == 409
    assert "overview must be accepted first" in excinfo.value.detail


def test_section_human_qa_on_reopens_cleared_downstream_sections():
    saved = []
    timestamp = "2026-05-02T00:00:00+00:00"
    canonical = {
        "agreement_id": "ae1",
        "sections": review_sections_module.default_sections(),
    }
    for name in ("overview", "uplift_rules"):
        section = canonical["sections"][name]
        section["status"] = "done"
        section["human_qa"] = {"enabled": True, "updated_at": "2026-05-01T00:00:00+00:00"}
    pay_tables = canonical["sections"]["pay_tables"]
    pay_tables["status"] = "in_progress"
    pay_tables["tables"] = [{"title": "Reviewed rates"}]
    scenarios = canonical["sections"]["scenarios"]
    scenarios["human_qa"] = {
        "enabled": False,
        "invalidated_by": "pay_tables",
        "invalidated_at": "2026-05-01T00:00:00+00:00",
    }

    def apply_section_status(section, status, completed_at):
        section["status"] = status
        section["completed_at"] = completed_at

    service = AgreementWorkspaceService(
        clear_review_record=lambda *args, **kwargs: {"cleared": True},
        list_councils=lambda include_split_parents=False: [],
        get_council=lambda ae_id: canonical,
        intake_workflow_dependencies=lambda: None,
        sections=set(review_sections_module.REVIEW_SECTIONS),
        valid_section_statuses=review_sections_module.VALID_SECTION_STATUSES,
        get_canonical=lambda ae_id: canonical,
        apply_section_status=apply_section_status,
        now_iso=lambda: timestamp,
        save_canonical=lambda ae_id, payload: saved.append((ae_id, payload)),
        uplift_workflow_dependencies=lambda: None,
        fetch_metadata_for_ae_id=lambda ae_id: None,
        find_pdf=lambda ae_id: None,
        extract_page_text=lambda ae_id, page_num: "",
        render_page_png=lambda ae_id, page_num: b"",
        agreement_dependencies=lambda: None,
        pay_table_dependencies=lambda: None,
        scenario_governance_dependencies=lambda: None,
    )

    result = service.update_section_human_qa(
        "ae1",
        "pay_tables",
        enabled=True,
        notes="Accept pay tables",
        summary="Pay tables accepted.",
    )

    assert result["enabled"] is True
    assert saved == [("ae1", canonical)]
    assert pay_tables["status"] == "done"
    assert pay_tables["human_qa"]["enabled"] is True
    assert scenarios["status"] == "not_started"
    assert scenarios["data"] is None
    assert scenarios["human_qa"]["enabled"] is False
    assert "invalidated_by" not in scenarios["human_qa"]
    assert "invalidated_at" not in scenarios["human_qa"]


def test_governance_event_service_delegates_to_scenario_governance(monkeypatch):
    deps = object()
    calls = []

    def fake_run(ae_id, body, passed_deps):
        calls.append(("run", ae_id, body, passed_deps))
        return {"ran": ae_id}

    def fake_promote(ae_id, body, passed_deps):
        calls.append(("promote", ae_id, body, passed_deps))
        return {"promoted": ae_id}

    def fake_rate_status(passed_deps):
        calls.append(("rate_status", passed_deps))
        return {"years": []}

    monkeypatch.setattr(scenario_governance_module, "run_uplift_rule_scenarios", fake_run)
    monkeypatch.setattr(scenario_governance_module, "promote_governed_set", fake_promote)
    monkeypatch.setattr(scenario_governance_module, "get_rate_cap_status", fake_rate_status)

    service = GovernanceEventService(scenario_governance_dependencies=lambda: deps)
    body = object()

    assert service.run_uplift_rule_scenarios("ae1", body) == {"ran": "ae1"}
    assert service.promote_governed_set("ae1", body) == {"promoted": "ae1"}
    assert service.rate_cap_status() == {"years": []}
    assert calls == [
        ("run", "ae1", body, deps),
        ("promote", "ae1", body, deps),
        ("rate_status", deps),
    ]
